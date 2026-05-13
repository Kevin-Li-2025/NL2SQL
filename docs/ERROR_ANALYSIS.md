# Error Analysis

This document tracks concrete failure modes from checked-in benchmark outputs. The goal is
to keep the project defensible: strong Spider results are useful, but BIRD needs separate
schema/value grounding evidence before claiming broad NL2SQL robustness.

## Current Evaluated Runs

| Run | Benchmark | Examples | Normalized EM | Execution Acc | Exec Errors | Schema Hallucinations |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `direct_spider_qwen25_coder_7b_l20_mfu` | Spider dev | 1,034 | 48.94% | 75.73% | 55 | 49 |
| `rich_context_spider_qwen25_coder_7b_l20_mfu` | Spider dev | 1,034 | 50.48% | 78.72% | 50 | 40 |
| `MCR-SQL-L20` | Spider dev | 1,034 | 51.06% | 80.37% | 20 | 18 |
| `direct_spider_qwen25_coder_7b_l20_mfu` | BIRD Mini-Dev | 500 | 0.80% | 21.60% | 100 | 62 |

## What Improved On Spider

MCR uses 8 candidate generations per example and selects through execution consistency.
On Spider dev, compared with single-path `rich_context`, it:

- improves execution accuracy by 1.65 points, from 78.72% to 80.37%;
- reduces execution errors from 50 to 20;
- reduces schema hallucinations from 40 to 18.

This is a real repo-internal improvement, but it is not yet a fair comparison against
larger agentic systems such as DIN-SQL, DAIL-SQL, C3, MAC-SQL, CHESS, or CHASE-SQL. Those
systems differ in base models, retrieval, self-consistency, decomposition, repair loops,
and sometimes external tools.

## Main Failure Modes

### Schema Linking Errors

Symptoms:

- predicted tables do not exist in the schema;
- predicted qualified columns such as `T1.foo` do not exist under the linked table;
- valid-looking SQL fails with `no such column`.

Current evidence:

- Spider direct: 49 schema hallucinations.
- Spider rich-context: 40 schema hallucinations.
- Spider MCR: 18 schema hallucinations.
- BIRD Mini-Dev direct: 62 schema hallucinations.

Next fix:

- add a schema-constrained decoder/repair pass that validates table and qualified column
  references before final scoring;
- improve table-column linking with value evidence and foreign-key neighborhood expansion;
- report the number of hallucinations corrected by the repair step.

### Value Grounding Errors

Symptoms:

- SQL shape is plausible, but filters use the wrong literal;
- entity names from the question are not matched to database cell values;
- BIRD evidence is ignored by the direct prompt.

Current evidence:

- BIRD Mini-Dev direct has only 21.60% execution accuracy despite full-schema prompts.
- This run is a weak out-of-domain baseline: the adapter is trained on Spider and the
  direct architecture does not use BIRD evidence or value retrieval.

Next fix:

- run `rich_context` and `MCR-SQL-L20` on BIRD Mini-Dev;
- add ablations for value hints on/off;
- log linked values per example so value failures can be reviewed without re-running
  inference.

### SQL Syntax And Runtime Errors

Symptoms:

- SQLite parser errors such as `near "FROM": syntax error`;
- invalid nested `SELECT` placement;
- runtime failures such as `no such column`.

Current evidence:

- BIRD Mini-Dev direct: 100 execution errors out of 500 examples.
- Spider MCR cuts Spider execution errors to 20 out of 1,034 examples.

Next fix:

- add a lightweight SQL parse/execute repair pass after generation;
- use execution feedback as a candidate feature in MCR;
- keep the SQLite timeout enabled so one pathological query cannot block the benchmark.

### Aggregation, Group By, And Nested Query Failures

Symptoms:

- wrong aggregation column;
- missing `GROUP BY` column;
- incorrect `HAVING` condition;
- nested query generated when a join is sufficient, or vice versa.

Current evidence:

- Local metrics do not yet classify these errors automatically.
- A structured per-example tagger should be added before claiming improvements on complex
  SQL reasoning.

Next fix:

- tag false-execution examples by SQL pattern: aggregation, group by, order/limit, nested
  query, set operation, join path, and value predicate;
- publish a small manually reviewed sample for Spider and BIRD.

## Reporting Rule

Every headline number should include:

- benchmark split and example count;
- whether the official evaluator was used or only the local SQLite evaluator;
- input context: full schema, gold schema subset, value hints, evidence, and retrieval;
- inference cost: number of candidate generations per example;
- whether the base model and training data are identical across compared architectures.
