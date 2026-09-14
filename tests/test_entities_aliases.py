from datetime import date

from text2sql.aliases import resolve_peak_column, resolve_plant
from text2sql.entities import DateRange, extract_entities


def test_extracts_chinese_roc_and_relative_dates() -> None:
    reference = date(2026, 9, 13)
    cases = {
        "2026年五月二日台中2號機": (DateRange("2026-05-02", "2026-05-02"), "2026-05-02"),
        "114年5月1日尖峰負載": (DateRange("2025-05-01", "2025-05-01"), "2025-05-01"),
        "去年六月一日台中5號機": (DateRange("2025-06-01", "2025-06-01"), "2025-06-01"),
        "2026年2月備轉容量": (DateRange("2026-02-01", "2026-02-28"), None),
        "今年上半年": (DateRange("2026-01-01", "2026-06-30"), None),
    }
    for question, expected in cases.items():
        entities = extract_entities(question, reference_date=reference)
        assert (entities.date_range, entities.explicit_date) == expected


def test_extracts_top_n_and_longest_fuel_alias() -> None:
    entities = extract_entities("天然氣出力最大的五名")
    assert entities.top_n == 5
    assert entities.fuel == "天然氣"


def test_aliases_resolve_exact_shorthand_and_ambiguity() -> None:
    columns = {"台中#2", "興達#3", "興達 (#1-#5)", "德基"}
    assert resolve_peak_column("台中2號機", columns).value == "台中#2"
    assert resolve_peak_column("查德基", columns).value == "德基"
    ambiguous = resolve_peak_column("興達3機", columns)
    assert ambiguous.ambiguous
    assert set(ambiguous.candidates) == {"興達#3", "興達 (#1-#5)"}

    plant = resolve_plant("中火設備", {"台中發電廠", "林口發電廠"})
    assert plant.value == "台中發電廠"
