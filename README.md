# NL2SQL L20

Single-GPU text-to-SQL research stack for LoRA fine-tuning, execution-guided
candidate generation, and value-aware selection with `Qwen2.5-Coder-7B-Instruct`.

This repository contains reproducible experiment code and saved evaluation
artifacts. It is not a hosted product, and the reported results are local
Spider/BIRD evaluations rather than public leaderboard submissions.

## Headline Results

Final experiment snapshot: 2026-05-15.

| Track | Protocol | Result | Evidence |
| --- | --- | ---: | --- |
| Spider dev | Retrospective VAV subset, n=4 | 82.20% official EX | [official output](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_vav_cost_curve/n04/spider_official/evaluation_stdout.txt) |
| Spider dev | Fresh EGS run, n=32 | 82.00% official EX | [official output](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/spider_dev_egs_n32/spider_official/evaluation_stdout.txt) |
| BIRD Mini-Dev | Fresh VAV run, n=20, temperature 0.9 | 47.80% EX | [results](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_vav_n20_t09/results.json) |
| BIRD Mini-Dev | Retrospective seven-pool union, n=80 | 48.40% EX | [cost curve](evals/sota/rich_context_spider_qwen25_coder_7b_l20_mfu/bird_mini_dev_vav_n140_union_t075_t10_t09_t085_t092_t09b_t09c_cost_curve_vav/summary.json) |
| L20 training probe | Schema-aware Spider LoRA | 73.22% dense MFU, 48.81% LoRA-estimated MFU, 1,914.90 tokens/s | [performance summary](outputs/schema_aware_spider_qwen25_coder_7b_l20_mfu/perf.summary.json) |

The strongest BIRD number is a retrospective selection result over saved candidate
pools. The strongest fresh BIRD run is 47.80% EX. The distinction matters: offline
pool selection is useful verifier research, but it is not equivalent to a new
single-run generation result.

## What the Repository Implements

- Spider and BIRD-style JSONL preparation;
- LoRA training for direct, schema-aware, rich-context, and repair variants;
- direct decoding, multi-candidate reranking, execution-guided selection, and
  value-aware voting;
- local execution metrics and Spider official evaluation exports;
- retrospective candidate-pool and cost-curve analysis;
- CPU-safe artifact and package checks.

The main research question is how far careful context construction and
inference-time selection can push a 7B open model under a single-L20 budget. It
does not claim a new foundation model or benchmark state of the art.

## Metrics and Boundaries

- `EX` is execution accuracy.
- Local `EM` is normalized exact match; Spider `Official EM` is the upstream
  structure-level metric and is not directly interchangeable with local EM.
- BIRD Mini-Dev contains 500 examples; Spider dev contains 1,034 examples.
- BIRD results are out-of-domain transfer from Spider-trained adapters.
- Dense MFU and LoRA-estimated MFU use different FLOP accounting. Report both
  labels rather than treating them as the same measurement.
- Saved retrospective sweeps reuse generated candidates and must remain labeled
  separately from fresh runs.

See the [technical report](docs/technical_report.md) for the complete protocol,
ablations, and result tables.

## Quick Validation

The CPU-safe path checks package behavior and saved-result tooling without loading
the model:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m pytest tests/
```

For full model runs, install the project on a CUDA system and inspect the available
commands:

```bash
nl2sql-benchmark --help
nl2sql-train --help
nl2sql-infer --help
```

Dataset and checkpoint paths are intentionally not hidden behind automatic
downloads. Prepare them explicitly and preserve each run's config, environment,
and output directory with the result artifact.

## Result Interpretation

The result progression is driven mainly by schema-rich prompting and
inference-time candidate selection. The saved ablations also contain negative
results: candidate repair, temperature 0.92, repeated 0.9 pools, and
value-grounded prompts did not improve the strongest fresh BIRD run.

These failures are retained because they constrain the claim. The repository
supports a resource-efficient text-to-SQL search study, not a general claim that
more candidates or more verifier stages always improve accuracy.

## Repository Map

| Path | Purpose |
| --- | --- |
| `src/` | Data preparation, training, generation, and evaluation code |
| `configs/` | Training and inference configurations |
| `tests/` | CPU-safe tests |
| `evals/after_train/` | Direct and intermediate evaluation artifacts |
| `evals/sota/` | Candidate-selection runs, official exports, and cost curves |
| `outputs/` | Training summaries and saved run metadata |
| `docs/technical_report.md` | Full methodology and result analysis |

## Reproducibility Checklist

When adding a result, record:

1. model and adapter checkpoint;
2. dataset split and example count;
3. prompt and candidate-selection configuration;
4. seed, temperature, and candidate budget;
5. GPU, software versions, tokens/s, and MFU definition;
6. whether the result is fresh generation or retrospective selection;
7. the raw prediction and evaluation artifact paths.

## Limitations

- The work uses one base model and primarily one GPU class.
- BIRD evaluation is a local Mini-Dev transfer study, not an official submission.
- Candidate-pool sweeps can overfit selection choices to the evaluation set.
- Execution accuracy does not measure SQL readability, security, or production
  database safety.
- End-to-end latency and monetary cost depend strongly on candidate count and
  should accompany deployment-oriented comparisons.

## License

MIT. See [LICENSE](LICENSE).
