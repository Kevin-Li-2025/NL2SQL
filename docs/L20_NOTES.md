# L20 Training Notes

Default config targets one NVIDIA L20.

Recommended starting point:

- `Qwen/Qwen2.5-Coder-7B-Instruct`
- 4-bit NF4 QLoRA
- max sequence length `8192`
- per-device batch size `1`
- gradient accumulation `16`
- LoRA rank `32`
- bf16 enabled

For the utilization target, use [L20_MFU.md](L20_MFU.md). The high-throughput config is
`configs/experiment_rich_context_spider_l20_mfu.yaml`.

If memory is tight:

- lower `max_seq_length` to `4096`
- lower LoRA rank from `32` to `16`
- keep gradient checkpointing enabled

If training is stable and memory remains available:

- try `max_seq_length: 12288`
- add more BIRD examples
- raise LoRA rank to `64`
