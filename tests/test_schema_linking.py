from nl2sql_l20.schema import Column, DatabaseSchema
from nl2sql_l20.schema_linking import link_schema


def test_schema_linking_matches_table_and_column_tokens() -> None:
    schema = DatabaseSchema(
        db_id="shop",
        tables=["customers", "orders"],
        columns=[
            Column(table="customers", name="customer_id"),
            Column(table="customers", name="name"),
            Column(table="orders", name="order_id"),
        ],
        foreign_keys=[],
    )
    links = link_schema("Show customer names", schema)
    assert "customers" in links["tables"]
    assert "customers.name" in links["columns"]
