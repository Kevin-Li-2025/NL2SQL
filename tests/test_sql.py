from nl2sql_l20.sql import extract_sql, normalize_sql


def test_extract_sql_from_markdown_fence() -> None:
    text = "```sql\nSELECT name FROM singer;\n```\nExplanation: done"
    assert extract_sql(text) == "SELECT name FROM singer;"


def test_normalize_sql_collapses_spacing_and_case() -> None:
    assert normalize_sql(" SELECT  Name  FROM Singer ; ") == "select name from singer"
