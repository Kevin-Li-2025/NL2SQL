from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import torch
from transformers import TrainerCallback, TrainerControl, TrainerState, TrainingArguments


def enable_torch_performance_flags(config: dict[str, Any]) -> None:
    performance = config.get("performance", {})
    if performance.get("enable_tf32", True):
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
    matmul_precision = performance.get("float32_matmul_precision")
    if matmul_precision:
        torch.set_float32_matmul_precision(str(matmul_precision))


def model_parameter_count(model: Any) -> int:
    return sum(parameter.numel() for parameter in model.parameters())


def tokens_per_optimizer_step(config: dict[str, Any], world_size: int = 1) -> int:
    training = config["training"]
    return (
        int(training["max_seq_length"])
        * int(training.get("per_device_train_batch_size", 1))
        * int(training.get("gradient_accumulation_steps", 1))
        * int(world_size)
    )


class PerformanceCallback(TrainerCallback):
    def __init__(
        self,
        tokens_per_step: int,
        parameter_count: int,
        peak_tflops: float,
        target_mfu: float,
        log_path: str | Path,
        warmup_steps: int = 5,
        print_steps: int = 10,
        dense_flop_multiplier: float = 6.0,
        lora_flop_multiplier: float = 4.0,
    ) -> None:
        self.tokens_per_step = tokens_per_step
        self.parameter_count = parameter_count
        self.peak_flops = peak_tflops * 1e12
        self.target_mfu = target_mfu
        self.log_path = Path(log_path)
        self.warmup_steps = warmup_steps
        self.print_steps = print_steps
        self.dense_flop_multiplier = dense_flop_multiplier
        self.lora_flop_multiplier = lora_flop_multiplier
        self.last_time: float | None = None
        self.records: list[dict[str, float | int]] = []

    def on_train_begin(
        self,
        args: TrainingArguments,
        state: TrainerState,
        control: TrainerControl,
        **kwargs: Any,
    ) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.last_time = time.perf_counter()
        with self.log_path.open("w", encoding="utf-8") as handle:
            handle.write("")

    def on_step_end(
        self,
        args: TrainingArguments,
        state: TrainerState,
        control: TrainerControl,
        **kwargs: Any,
    ) -> None:
        now = time.perf_counter()
        if self.last_time is None:
            self.last_time = now
            return

        elapsed = now - self.last_time
        self.last_time = now
        if elapsed <= 0:
            return

        tokens_per_second = self.tokens_per_step / elapsed
        dense_mfu = (
            tokens_per_second
            * self.parameter_count
            * self.dense_flop_multiplier
            / self.peak_flops
        )
        lora_mfu = (
            tokens_per_second
            * self.parameter_count
            * self.lora_flop_multiplier
            / self.peak_flops
        )
        record = {
            "step": int(state.global_step),
            "elapsed_seconds": elapsed,
            "tokens_per_second": tokens_per_second,
            "dense_mfu": dense_mfu,
            "lora_estimated_mfu": lora_mfu,
            "target_mfu": self.target_mfu,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")

        if state.global_step > self.warmup_steps:
            self.records.append(record)
        if self.print_steps and state.global_step % self.print_steps == 0:
            print(
                "[perf] "
                f"step={state.global_step} "
                f"tok/s={tokens_per_second:.1f} "
                f"dense_mfu={dense_mfu:.3f} "
                f"lora_mfu={lora_mfu:.3f}",
                flush=True,
            )

    def on_train_end(
        self,
        args: TrainingArguments,
        state: TrainerState,
        control: TrainerControl,
        **kwargs: Any,
    ) -> None:
        if not self.records:
            return
        tail = self.records[-min(20, len(self.records)) :]
        avg_tokens = sum(float(row["tokens_per_second"]) for row in tail) / len(tail)
        avg_dense_mfu = sum(float(row["dense_mfu"]) for row in tail) / len(tail)
        avg_lora_mfu = sum(float(row["lora_estimated_mfu"]) for row in tail) / len(tail)
        summary = {
            "step": int(state.global_step),
            "avg_tail_tokens_per_second": avg_tokens,
            "avg_tail_dense_mfu": avg_dense_mfu,
            "avg_tail_lora_estimated_mfu": avg_lora_mfu,
            "target_mfu": self.target_mfu,
            "target_met": avg_dense_mfu >= self.target_mfu,
        }
        summary_path = self.log_path.with_suffix(".summary.json")
        with summary_path.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(
            "[perf] "
            f"tail_avg_tok/s={avg_tokens:.1f} "
            f"tail_avg_dense_mfu={avg_dense_mfu:.3f} "
            f"target={self.target_mfu:.3f}",
            flush=True,
        )
