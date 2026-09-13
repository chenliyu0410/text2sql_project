"""Resolve user-facing plant and unit aliases without guessing ambiguities."""

from __future__ import annotations

import re
from dataclasses import dataclass

from align.naming import chinese_number


@dataclass(frozen=True)
class AliasResolution:
    value: str | None
    candidates: tuple[str, ...]
    ambiguous: bool = False


PLANT_ALIASES = {
    "中火": "台中發電廠",
    "台中電廠": "台中發電廠",
    "興達電廠": "興達發電廠",
    "林口電廠": "林口發電廠",
    "大潭電廠": "大潭發電廠",
}


def resolve_plant(question: str, plants: set[str]) -> AliasResolution:
    for alias, formal in PLANT_ALIASES.items():
        if alias in question and formal in plants:
            return AliasResolution(formal, (formal,))
    matches = tuple(sorted(plant for plant in plants if plant.removesuffix("發電廠") in question))
    return (
        AliasResolution(matches[0], matches)
        if len(matches) == 1
        else AliasResolution(None, matches, len(matches) > 1)
    )


def resolve_peak_column(question: str, columns: set[str]) -> AliasResolution:
    exact = tuple(
        sorted((column for column in columns if column in question), key=len, reverse=True)
    )
    if exact:
        longest = exact[0]
        ties = tuple(column for column in exact if len(column) == len(longest))
        return AliasResolution(longest if len(ties) == 1 else None, ties, len(ties) > 1)

    match = re.search(r"(台中|林口|大林|興達)\s*#?(\d{1,2})\s*(?:號|機)?", question)
    if match:
        plant, number = match.groups()
        candidate = f"{plant}#{int(number)}"
        if plant == "興達" and int(number) == 3:
            candidates = tuple(column for column in ("興達#3", "興達 (#1-#5)") if column in columns)
            return AliasResolution(None, candidates, True)
        if candidate in columns:
            return AliasResolution(candidate, (candidate,))

    chinese = re.search(r"(台中|林口)\s*([一二三四五六七八九十]+)號", question)
    if chinese:
        for number in range(1, 13):
            if chinese.group(2) == chinese_number(number):
                candidate = f"{chinese.group(1)}#{number}"
                if candidate in columns:
                    return AliasResolution(candidate, (candidate,))
    return AliasResolution(None, ())
