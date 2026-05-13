# Ablation Plan

The next credible step is to separate architecture gains from extra context, retrieval,
and inference budget. This document defines the control runs to add before making stronger
claims.

## Required Matrix

| Ablation | Benchmark | Adapter | Prompt Context | Candidate Generations | Purpose |
| --- | --- | --- | --- | ---: | --- |
| direct | Spider dev | direct Spider LoRA | full schema | 1 | base single-path control |
| schema-aware | Spider dev | schema-aware Spider LoRA | linked schema + FK expansion | 1 | test schema linking without rich values |
| rich-context no values | Spider dev, BIRD Mini-Dev | rich-context LoRA | M-Schema + evidence, no value hints | 1 | isolate value retrieval |
| rich-context full | Spider dev, BIRD Mini-Dev | rich-context LoRA | M-Schema + evidence + value hints | 1 | measure richer prompt context |
| MCR no value-aware selector | Spider dev, BIRD Mini-Dev | rich-context LoRA | multi-prompt rich context | 8 | test multi-path generation alone |
| MCR full selector | Spider dev, BIRD Mini-Dev | rich-context LoRA | multi-prompt rich context + value-aware ranking | 8-30 | test final selector |

## Specific Controls

### No Value Hints

Disable matched database values while keeping schema text and evidence unchanged.

Expected question:

- Does the gain come from SQL structure prompting or from entity/value lookup?

Required report fields:

- execution accuracy delta;
- value-predicate error count;
- candidate generation count.

### No Foreign-Key Expansion

Run schema-aware prompting with question-linked tables/columns only, without expanding to
neighboring foreign-key tables.

Expected question:

- Does FK expansion improve join path recovery or add schema noise?

Required report fields:

- schema hallucination rate;
- join-path failure sample count;
- execution accuracy delta.

### No MCR Selector

Generate the same candidates but choose the first candidate or the highest normalized
log-probability candidate if available.

Expected question:

- Does MCR help because it samples more SQL, or because the selector chooses better SQL?

Required report fields:

- candidate count;
- execution accuracy;
- executable rate;
- schema hallucination rate.

### No Repair

If SQL repair is added later, keep a no-repair run.

Expected question:

- Are improvements coming from the model/prompt or from post-generation correction?

Required report fields:

- pre-repair metrics;
- post-repair metrics;
- number of examples changed by repair.

## Reporting Format

Each ablation should be checked in under:

```text
evals/ablations/<experiment_name>/<benchmark_name>/
  predictions.jsonl
  results.json
  command.txt
```

`command.txt` should contain the exact command, adapter path, config path, and git commit
used for the run.

## Priority Order

1. BIRD Mini-Dev `rich_context`.
2. BIRD Mini-Dev `MCR-SQL-L20`.
3. Spider dev `schema_aware`.
4. Value hints on/off for BIRD Mini-Dev.
5. FK expansion on/off for Spider and BIRD.
