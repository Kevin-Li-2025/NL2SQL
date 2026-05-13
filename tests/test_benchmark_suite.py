from nl2sql_l20.benchmark_suite import as_list, should_skip_for_architecture


def test_as_list_accepts_comma_separated_values() -> None:
    assert as_list("rich_context,decompose") == ["rich_context", "decompose"]


def test_should_skip_for_architecture() -> None:
    benchmark = {"only_architectures": ["rich_context"]}
    assert should_skip_for_architecture(benchmark, "direct") is True
    assert should_skip_for_architecture(benchmark, "rich_context") is False
