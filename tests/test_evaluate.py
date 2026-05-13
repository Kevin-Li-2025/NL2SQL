from nl2sql_l20.evaluate import evaluate_rows, schema_violations


GOLD_ROW = {
    "id": "toy-000001",
    "db_id": "shop",
    "sql": "SELECT name FROM customers;",
    "schema_text": "CREATE TABLE customers (\n  name text,\n  age number\n);",
    "db_path": "",
}


def test_schema_violations_detects_hallucinated_table() -> None:
    violations = schema_violations("SELECT name FROM users;", GOLD_ROW)
    assert violations["tables"] == ["users"]


def test_schema_violations_resolves_table_aliases() -> None:
    violations = schema_violations("SELECT c.name FROM customers AS c;", GOLD_ROW)
    assert violations["qualified_columns"] == []


def test_evaluate_rows_reports_schema_hallucination_rate() -> None:
    result = evaluate_rows(
        [GOLD_ROW],
        [{"id": "toy-000001", "prediction": "SELECT name FROM users;"}],
        execute=False,
    )
    assert result["schema_hallucination_rate"] == 1.0
    assert result["predicted_sql_present_rate"] == 1.0
