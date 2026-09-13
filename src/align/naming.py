"""Pure naming conversions shared by daily, outage, and query alignment."""

from __future__ import annotations

import re

CHINESE_NUMERALS = {
    1: "一",
    2: "二",
    3: "三",
    4: "四",
    5: "五",
    6: "六",
    7: "七",
    8: "八",
    9: "九",
    10: "十",
    11: "十一",
    12: "十二",
}


def normalize_name(value: str) -> str:
    """Normalize punctuation and spacing without guessing the underlying unit."""
    return re.sub(r"\s+", "", value.strip().replace("＃", "#").replace("～", "~"))


def chinese_number(value: int) -> str:
    try:
        return CHINESE_NUMERALS[value]
    except KeyError as error:
        raise ValueError(f"只支援 1 至 12 的機組編號：{value}") from error


def extract_hash_number(value: str) -> int | None:
    match = re.search(r"#([0-9]{1,2})", normalize_name(value))
    return int(match.group(1)) if match else None


def outage_unit_candidates(source_name: str) -> tuple[str, ...]:
    """Generate ordered master-name candidates for one d006008 source name."""
    source = normalize_name(source_name).removesuffix("機")
    candidates = [source, f"{source}機"]
    number = extract_hash_number(source)
    if number is not None:
        numeral = chinese_number(number) if number in CHINESE_NUMERALS else str(number)
        rules: tuple[tuple[str, str], ...] = (
            ("林口", f"林{numeral}機"),
            ("台中", f"中{numeral}機"),
            ("協和", f"協{numeral}機"),
            ("大林", f"大{numeral}機"),
            ("青山", f"青山{numeral}機"),
            ("大潭", f"大潭複{numeral}機"),
            ("通霄", f"通霄複{numeral}機"),
            ("南部", f"南部複{numeral}機"),
            ("興達CC", f"興達複{numeral}機"),
            ("觀一", f"大觀一廠#{number}機"),
            ("觀二", f"大觀二廠#{number}機"),
        )
        for prefix, candidate in rules:
            if source.startswith(f"{prefix}#"):
                candidates.append(candidate)
        if source.startswith("台中GT#") or source.startswith("台中GAS#"):
            candidates.append(f"GT#{number}")
        if source.startswith("大潭#") and number == 7:
            candidates.insert(0, "#GT7")

    return tuple(dict.fromkeys(candidates))
