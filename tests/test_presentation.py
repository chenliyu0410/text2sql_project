from serving.presentation import ALLOWED_CHART_KINDS, build_chart_spec, enrich_query_data


def test_line_chart_values_are_directly_traceable_to_rows() -> None:
    columns = ["日期", "備轉容量率_pct"]
    rows = [["2026-07-01", 8.1], ["2026-07-02", 7.2]]
    chart = build_chart_spec(columns, rows)
    assert chart and chart["kind"] == "line"
    assert chart["data"][0]["x"] == [row[0] for row in rows]
    assert chart["data"][0]["y"] == [row[1] for row in rows]


def test_two_numeric_columns_produce_constrained_scatter() -> None:
    chart = build_chart_spec(
        ["機組欄位", "對應裝置容量_萬瓩", "峰值"],
        [["甲", 10.0, 8.0], ["乙", 20.0, 18.0]],
    )
    assert chart and chart["kind"] == "scatter"
    assert chart["kind"] in ALLOWED_CHART_KINDS
    assert chart["data"][0]["text"] == ["甲", "乙"]
    assert not any(callable(value) for value in chart["data"][0].values())


def test_scalar_or_empty_result_does_not_force_a_chart() -> None:
    assert build_chart_spec(["最大值"], [[12.3]]) is None
    enriched = enrich_query_data(
        {"columns": ["日期"], "rows": [], "disclosures": [], "record_count": 0}
    )
    assert enriched["chart_spec"] is None
    assert enriched["statistics"]["record_count"] == 0
