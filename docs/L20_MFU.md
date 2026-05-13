# L20 MFU Target

Target: keep one NVIDIA L20 busy and push dense-model MFU above `0.60`.

This repo measures MFU during training, so the target is observable rather than inferred
from `nvidia-smi`.

## High-Throughput Config

Use:

```bash
pip install -e ".[train,perf,dev]"
bash scripts/probe_l20_mfu.sh
```

Full run:

```bash
bash scripts/train_rich_context_l20_mfu.sh
```

The MFU config is:

```text
configs/experiment_rich_context_spider_l20_mfu.yaml
```

It enables:

- fixed-length sequence packing
- `max_seq_length: 8192`
- `per_device_train_batch_size: 2`
- `gradient_accumulation_steps: 8`
- FlashAttention 2
- Liger Qwen2 kernels
- TF32 matmul paths
- pinned dataloader memory
- `paged_adamw_8bit`

## Output

During training:

```text
outputs/.../perf.jsonl
outputs/.../perf.summary.json
```

Each row includes:

- `tokens_per_second`
- `dense_mfu`
- `lora_estimated_mfu`
- `target_mfu`

`dense_mfu` uses:

```text
tokens_per_second * parameter_count * 6 / gpu_peak_flops
```

The default L20 dense BF16/FP16 peak is set to `119.5 TFLOPS`. If your provider reports a
different dense peak, change `performance.mfu.gpu_peak_tflops`.

## If MFU Is Below 60%

Tune in this order:

1. Make sure `sequence_packing: true`; without packing, NL2SQL examples waste too much
   compute on short sequences.
2. Confirm FlashAttention 2 is active. If it is missing, install `flash-attn` on the CUDA
   machine.
3. Confirm Liger is active. It patches Qwen2/Qwen2.5 RMSNorm, RoPE, SwiGLU, and fused loss.
4. Raise `per_device_train_batch_size` from `2` to `3` if memory allows.
5. If memory blocks larger microbatches, lower `max_seq_length` to `6144` and try
   `per_device_train_batch_size: 3` or `4`.
6. Reduce eval/save frequency; eval and checkpointing interrupt the steady-state window.
7. Use `torch_compile: true` only after the FlashAttention/Liger path is stable; it can
   improve throughput but may be brittle with PEFT and bitsandbytes.

## Practical Caveat

QLoRA is memory efficient but not always MFU efficient because 4-bit dequantization,
adapter-only gradients, and Python-side trainer overhead can depress dense MFU. If the
L20 cannot reach `dense_mfu >= 0.60` with QLoRA, the next experiment should be a BF16
LoRA or full-parameter run with ZeRO/FSDP-style memory management, not a smaller batch.
