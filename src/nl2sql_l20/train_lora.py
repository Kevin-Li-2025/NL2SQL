from __future__ import annotations

import argparse
import gc
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

import torch
from datasets import Dataset, load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import Trainer, TrainingArguments

from nl2sql_l20.config import load_config, require
from nl2sql_l20.modeling import apply_liger_kernel_if_requested, load_causal_lm, load_tokenizer
from nl2sql_l20.packing import IGNORE_INDEX, pack_tokenized_records
from nl2sql_l20.perf import (
    PerformanceCallback,
    enable_torch_performance_flags,
    model_parameter_count,
    tokens_per_optimizer_step,
)
from nl2sql_l20.prompts import apply_chat_template, build_messages


@dataclass
class CausalDataCollator:
    pad_token_id: int

    def __call__(self, features: list[dict[str, list[int]]]) -> dict[str, torch.Tensor]:
        max_length = max(len(feature["input_ids"]) for feature in features)
        input_ids = []
        labels = []
        attention_mask = []

        for feature in features:
            length = len(feature["input_ids"])
            pad_length = max_length - length
            input_ids.append(feature["input_ids"] + [self.pad_token_id] * pad_length)
            labels.append(feature["labels"] + [IGNORE_INDEX] * pad_length)
            attention_mask.append([1] * length + [0] * pad_length)

        return {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
            "attention_mask": torch.tensor(attention_mask, dtype=torch.long),
        }


def encode_example(
    row: dict[str, Any],
    tokenizer: Any,
    architecture: str,
    max_seq_length: int,
) -> dict[str, list[int]]:
    prompt = apply_chat_template(
        tokenizer,
        build_messages(row, architecture),
        add_generation_prompt=True,
    )
    answer = row["sql"].strip()
    if not answer.endswith(";"):
        answer = answer + ";"
    answer = answer + (tokenizer.eos_token or "")

    prompt_ids = tokenizer(prompt, add_special_tokens=False).input_ids
    answer_ids = tokenizer(answer, add_special_tokens=False).input_ids
    input_ids = (prompt_ids + answer_ids)[:max_seq_length]
    labels = ([IGNORE_INDEX] * len(prompt_ids) + answer_ids)[:max_seq_length]

    if all(label == IGNORE_INDEX for label in labels):
        labels[-1] = input_ids[-1]

    return {"input_ids": input_ids, "labels": labels}


def load_tokenized_dataset(
    path: str,
    tokenizer: Any,
    architecture: str,
    max_seq_length: int,
    sequence_packing: bool,
    drop_remainder: bool,
) -> Any:
    dataset = load_dataset("json", data_files=path, split="train")
    tokenized = dataset.map(
        lambda row: encode_example(row, tokenizer, architecture, max_seq_length),
        remove_columns=dataset.column_names,
        desc=f"Tokenizing {path}",
    )
    if not sequence_packing:
        return tokenized

    packed = pack_tokenized_records(
        tokenized,
        max_seq_length=max_seq_length,
        pad_token_id=tokenizer.pad_token_id,
        drop_remainder=drop_remainder,
    )
    return Dataset.from_list(packed)


def build_training_args(config: dict[str, Any], has_eval: bool) -> TrainingArguments:
    training = config["training"]
    eval_strategy = "steps" if has_eval else "no"
    return TrainingArguments(
        output_dir=training["output_dir"],
        num_train_epochs=float(training.get("num_train_epochs", 1)),
        max_steps=int(training.get("max_steps", -1)),
        per_device_train_batch_size=int(training.get("per_device_train_batch_size", 1)),
        per_device_eval_batch_size=int(training.get("per_device_eval_batch_size", 1)),
        gradient_accumulation_steps=int(training.get("gradient_accumulation_steps", 1)),
        learning_rate=float(training.get("learning_rate", 2e-4)),
        warmup_ratio=float(training.get("warmup_ratio", 0.03)),
        weight_decay=float(training.get("weight_decay", 0.0)),
        lr_scheduler_type=training.get("lr_scheduler_type", "cosine"),
        optim=training.get("optim", "paged_adamw_8bit"),
        logging_steps=int(training.get("logging_steps", 10)),
        eval_strategy=eval_strategy,
        eval_steps=int(training.get("eval_steps", 250)),
        save_strategy="steps",
        save_steps=int(training.get("save_steps", 250)),
        save_total_limit=int(training.get("save_total_limit", 2)),
        bf16=bool(training.get("bf16", True)),
        fp16=bool(training.get("fp16", False)),
        tf32=bool(training.get("tf32", True)),
        gradient_checkpointing=bool(training.get("gradient_checkpointing", True)),
        gradient_checkpointing_kwargs=training.get(
            "gradient_checkpointing_kwargs",
            {"use_reentrant": False},
        ),
        dataloader_num_workers=int(training.get("dataloader_num_workers", 4)),
        dataloader_pin_memory=bool(training.get("dataloader_pin_memory", True)),
        dataloader_persistent_workers=bool(
            training.get("dataloader_persistent_workers", True)
        ),
        torch_compile=bool(training.get("torch_compile", False)),
        torch_compile_backend=training.get("torch_compile_backend", None),
        torch_compile_mode=training.get("torch_compile_mode", None),
        report_to=training.get("report_to", "none"),
        remove_unused_columns=False,
    )


def build_callbacks(config: dict[str, Any], parameter_count: int) -> list[Any]:
    performance = config.get("performance", {})
    mfu = performance.get("mfu", {})
    if not mfu.get("enabled", True):
        return []

    output_dir = require(config, "training.output_dir")
    log_path = mfu.get("log_path") or f"{output_dir}/perf.jsonl"
    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    return [
        PerformanceCallback(
            tokens_per_step=tokens_per_optimizer_step(config, world_size=world_size),
            parameter_count=parameter_count,
            peak_tflops=float(mfu.get("gpu_peak_tflops", 119.5)),
            target_mfu=float(mfu.get("target", 0.60)),
            log_path=log_path,
            warmup_steps=int(mfu.get("warmup_steps", 5)),
            print_steps=int(mfu.get("print_steps", 10)),
            dense_flop_multiplier=float(mfu.get("dense_flop_multiplier", 6.0)),
            lora_flop_multiplier=float(mfu.get("lora_flop_multiplier", 4.0)),
        )
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a QLoRA NL2SQL adapter.")
    parser.add_argument("--config", required=True, help="Experiment YAML config.")
    parser.add_argument(
        "--benchmark-suite",
        default=None,
        help="Optional benchmark suite YAML to run automatically after training.",
    )
    args = parser.parse_args()

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    config = load_config(args.config)
    architecture = require(config, "experiment.architecture")
    max_seq_length = int(require(config, "training.max_seq_length"))
    model_config = require(config, "model")
    enable_torch_performance_flags(config)

    tokenizer = load_tokenizer(
        model_config["base_model"],
        trust_remote_code=bool(model_config.get("trust_remote_code", True)),
    )
    model = load_causal_lm(model_config)
    parameter_count = model_parameter_count(model)
    model = apply_liger_kernel_if_requested(model, model_config)

    if model_config.get("load_in_4bit", False):
        model = prepare_model_for_kbit_training(model)

    if config["training"].get("gradient_checkpointing", True):
        model.gradient_checkpointing_enable()
        model.config.use_cache = False

    lora = config["lora"]
    peft_config = LoraConfig(
        r=int(lora["r"]),
        lora_alpha=int(lora["alpha"]),
        lora_dropout=float(lora.get("dropout", 0.0)),
        target_modules=list(lora["target_modules"]),
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()

    train_dataset = load_tokenized_dataset(
        require(config, "data.train_file"),
        tokenizer,
        architecture,
        max_seq_length,
        sequence_packing=bool(config["training"].get("sequence_packing", False)),
        drop_remainder=bool(config["training"].get("drop_remainder", False)),
    )
    eval_file = config.get("data", {}).get("eval_file")
    eval_dataset = (
        load_tokenized_dataset(
            eval_file,
            tokenizer,
            architecture,
            max_seq_length,
            sequence_packing=bool(config["training"].get("eval_sequence_packing", False)),
            drop_remainder=False,
        )
        if eval_file
        else None
    )

    trainer = Trainer(
        model=model,
        args=build_training_args(config, has_eval=eval_dataset is not None),
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=CausalDataCollator(pad_token_id=tokenizer.pad_token_id),
        tokenizer=tokenizer,
        callbacks=build_callbacks(config, parameter_count),
    )
    trainer.train()
    trainer.save_model(config["training"]["output_dir"])
    tokenizer.save_pretrained(config["training"]["output_dir"])

    if args.benchmark_suite:
        adapter_path = config["training"]["output_dir"]
        del trainer
        del model
        del tokenizer
        del train_dataset
        del eval_dataset
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        subprocess.run(
            [
                sys.executable,
                "-m",
                "nl2sql_l20.benchmark_suite",
                "--experiment-config",
                args.config,
                "--suite",
                args.benchmark_suite,
                "--adapter",
                adapter_path,
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
