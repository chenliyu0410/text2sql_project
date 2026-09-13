from align.naming import chinese_number, normalize_name, outage_unit_candidates


def test_normalize_name_handles_full_width_punctuation_and_spaces() -> None:
    assert normalize_name(" 台中 ＃ 3 ") == "台中#3"


def test_outage_candidates_cover_the_four_naming_systems() -> None:
    assert "中十機" in outage_unit_candidates("台中#10")
    assert "大潭複六機" in outage_unit_candidates("大潭#6")
    assert outage_unit_candidates("大潭#7")[0] == "#GT7"
    assert "興達複三機" in outage_unit_candidates("興達CC#3")
    assert "大觀一廠#2機" in outage_unit_candidates("觀一#2")
    assert "青山二機" in outage_unit_candidates("青山#2")


def test_chinese_number_rejects_out_of_scope_value() -> None:
    assert chinese_number(12) == "十二"
