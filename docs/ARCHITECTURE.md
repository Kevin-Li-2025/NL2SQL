# Architecture

This repo compares NL2SQL architectures while holding the base model fixed.

## Direct

`direct` is the control condition. It serializes the full schema and asks for SQL.

Good for:

- sanity checks
- reproducing common text-to-SQL SFT baselines
- measuring how much the base model already knows

Weaknesses:

- schema noise grows quickly on large databases
- column selection is fragile
- no explicit use of evidence or value hints

## Schema-Aware

`schema_aware` changes the input architecture, not the base model.

It adds:

- evidence field when the benchmark provides one
- linked table and column hints
- foreign-key expansion
- the full schema as fallback context

This makes the model's generation problem smaller without changing the underlying model
weights or benchmark split.

## Rich Context

`rich_context` is the first serious architecture. It uses an M-Schema style serialization,
question-linked schema hints, foreign keys, benchmark evidence, and database value hints.

Good for:

- BIRD-style databases where values and domain evidence matter
- reducing hallucinated table and column names
- keeping the full schema available while highlighting likely relevant fields

## MCR Pipeline

`MCR-SQL-L20` is the SOTA-oriented architecture:

- retrieve metadata and values
- generate candidates through `rich_context`, `decompose`, `query_plan`, and `skeleton`
- execute candidates safely
- select by execution consistency
- later replace heuristic selection with pairwise selector and merge/repair adapters

See [SOTA_ARCHITECTURE.md](SOTA_ARCHITECTURE.md).

## Design Rule

Every architecture should produce the same output type: one SQL query only. That keeps
benchmark comparison fair and avoids exact-match loss from extra explanations.
