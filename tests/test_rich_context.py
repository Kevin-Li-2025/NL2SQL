import sqlite3

from nl2sql_l20.schema import Column, DatabaseSchema, serialize_m_schema
from nl2sql_l20.value_hints import collect_value_hints


def test_m_schema_marks_linked_columns_and_values() -> None:
    schema = DatabaseSchema(
        db_id="shop",
        tables=["customers"],
        columns=[Column(table="customers", name="name", dtype="text", primary_key=False)],
        foreign_keys=[],
    )
    text = serialize_m_schema(
        schema,
        linked={"tables": ["customers"], "columns": ["customers.name"]},
        value_hints={"customers.name": ["Alice"]},
    )
    assert "<TABLE name=\"customers\" relevant=true>" in text
    assert "flags=question_linked" in text
    assert "examples=Alice" in text


def test_collect_value_hints_matches_sqlite_values(tmp_path) -> None:
    db_path = tmp_path / "shop.sqlite"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE customers (name TEXT)")
        connection.execute("INSERT INTO customers VALUES ('Alice Chen')")
        connection.commit()
    finally:
        connection.close()

    schema = DatabaseSchema(
        db_id="shop",
        tables=["customers"],
        columns=[Column(table="customers", name="name", dtype="text", primary_key=False)],
        foreign_keys=[],
    )
    hints = collect_value_hints(db_path, schema, "Show orders for Alice")
    assert hints["customers.name"] == ["Alice Chen"]
