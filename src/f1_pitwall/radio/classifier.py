"""Deterministic baseline classification for radio transcripts."""

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class RadioCategory(StrEnum):
    """Strategy-relevant radio categories."""

    TYRES = "TYRES"
    TRAFFIC = "TRAFFIC"
    STRATEGY = "STRATEGY"
    WEATHER = "WEATHER"
    RELIABILITY = "RELIABILITY"
    OTHER = "OTHER"


class RadioSignal(BaseModel):
    """Auditable keyword classification result."""

    model_config = ConfigDict(frozen=True)

    text: str
    categories: tuple[RadioCategory, ...]
    matched_terms: tuple[str, ...]


_TERMS: dict[RadioCategory, tuple[str, ...]] = {
    RadioCategory.TYRES: (
        "tyre",
        "tyres",
        "tire",
        "tires",
        "graining",
        "deg",
        "degradation",
        "sliding",
    ),
    RadioCategory.TRAFFIC: ("traffic", "gap", "drs", "blue flag", "car ahead"),
    RadioCategory.STRATEGY: ("box", "pit", "stay out", "undercut", "overcut", "plan"),
    RadioCategory.WEATHER: ("rain", "wet", "weather", "drops", "inter", "inters", "intermediate"),
    RadioCategory.RELIABILITY: ("engine", "brake", "brakes", "power", "gearbox", "temperature"),
}


def classify_radio(text: str) -> RadioSignal:
    """Classify transcript text without an external model or network call."""
    normalized = " ".join(text.casefold().split())
    categories: list[RadioCategory] = []
    matches: list[str] = []
    for category, terms in _TERMS.items():
        matched = [term for term in terms if re.search(r"\b" + re.escape(term) + r"\b", normalized)]
        if matched:
            categories.append(category)
            matches.extend(matched)
    if not categories:
        categories.append(RadioCategory.OTHER)
    return RadioSignal(
        text=text,
        categories=tuple(categories),
        matched_terms=tuple(dict.fromkeys(matches)),
    )
