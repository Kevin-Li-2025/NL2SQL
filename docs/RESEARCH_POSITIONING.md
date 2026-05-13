# Research Positioning

This repo should not claim to be a Text-to-SQL SOTA system. The defensible claim is
narrower and stronger:

> A reproducible NL2SQL benchmark framework for comparing schema/context/multi-candidate
> inference architectures on one NVIDIA L20 GPU with the same Qwen2.5-Coder-7B base
> model, with checked-in Spider official evaluator output, MFU logs, BIRD transfer
> results, and inference cost artifacts.

## Current Position

| Dimension | Status |
| --- | --- |
| Spider 1.0 | Strong enough to show that the pipeline works. Best checked-in official dev execution accuracy is 82.20% from a retrospective n=4 VAV subset. |
| BIRD Mini-Dev | Not strong yet. Best current execution accuracy is 39.20%, which is useful transfer evidence but not a strong BIRD system. |
| Hardware story | Strong. The project keeps the comparison to one L20 and records MFU/cost instead of hiding compute. |
| Research story | Good framework and ablation base; not enough for a SOTA paper until BIRD and learned selector/repair ablations improve. |

## Claim Boundary

Use:

> This repo builds a reproducible single-L20 NL2SQL research-engineering benchmark. With
> the same Qwen2.5-Coder-7B base model, rich context plus multi-candidate selection reaches
> 82.20% Spider dev execution accuracy under the official Spider evaluator, while BIRD
> Mini-Dev transfer remains the main bottleneck at 39.20%.

Avoid:

> This is a SOTA Text-to-SQL system.

Avoid:

> BIRD is solved.

## Why The Spider Result Is Useful

The Spider result is not leaderboard SOTA, but it is useful because the evidence chain is
clean:

- same base model;
- direct, schema-aware, rich-context, MCR, and VAV comparisons;
- local SQLite execution and upstream Spider evaluator stdout;
- candidate-budget curve showing that n=4/n=8 can match n=30;
- a negative EGS n=32 selector ablation showing that more execution-guided hand rules
  reduce hallucination but do not automatically improve execution accuracy;
- cost artifacts and training MFU logs.

That makes Spider the benchmark for proving that the architecture and evaluation harness
work.

## Why BIRD Is The Research Gap

BIRD Mini-Dev exposes failures that Spider does not stress enough:

- value grounding against dirty or database-specific values;
- schema linking when names are less obvious;
- external evidence and domain phrasing;
- candidate selection under out-of-domain transfer;
- repair of executable but semantically wrong SQL.

The current best BIRD Mini-Dev result, 39.20% execution accuracy, should be framed as an
out-of-domain transfer baseline with clear room for improvement. The next target is 45%+
Mini-Dev execution accuracy without training on Mini-Dev labels.

## Next Experiments

1. Finish Candidate-Repair-SQL-L20 and compare Spider/BIRD against VAV and MCR.
2. Run BIRD Mini-Dev VAV n=12 and EGS n=16 after repair to test value-aware selection on
   the harder transfer set.
3. Train a learned selector from Spider train candidate pools so fewer candidates can
   match or beat the retrospective n=4/n=8 curve.
4. Add BIRD-specific value grounding ablations: no value hints, lexical hints, execution
   sampled values, and evidence-aware hints.
