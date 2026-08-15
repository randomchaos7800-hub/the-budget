"""Propose BaselineTemplates from imported ledger lines.

Never auto-applies. User confirms. Certainty over convenience.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from .engine import CashFlowCategory, Frequency

_NOISE = re.compile(
    r"\b(\d{4,}|#\d+|x{2,}\d+|\*+\d+|pos|ach|debit|credit|card|purchase|payment)\b",
    re.I,
)
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_SPACES = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    text = name.lower()
    text = _NOISE.sub(" ", text)
    text = _NON_ALNUM.sub(" ", text)
    text = _SPACES.sub(" ", text).strip()
    return text[:40] or name.strip().lower()


def guess_category(name: str, amount: float) -> CashFlowCategory:
    if amount >= 0:
        return CashFlowCategory.INCOME
    blob = name.lower()
    mapping = [
        (CashFlowCategory.HOUSING, ("rent", "mortgage", "landlord", "apartment", "hoa")),
        (CashFlowCategory.TRANSPORTATION, ("toyota", "car ", "auto", "uber", "lyft", "gas", "shell", "chevron")),
        (CashFlowCategory.UTILITIES, ("electric", "power", "water", "gas company", "internet", "comcast", "xfinity")),
        (CashFlowCategory.FOOD, ("grocery", "safeway", "walmart", "kroger", "costco", "restaurant")),
        (CashFlowCategory.HEALTHCARE, ("cigna", "hospital", "clinic", "pharmacy", "cvs", "walgreens")),
        (CashFlowCategory.INSURANCE, ("insurance", "geico", "progressive", "state farm")),
        (CashFlowCategory.DEBT, ("loan", "westlake", "capital one", "discover", "navient")),
        (CashFlowCategory.SUBSCRIPTIONS, ("netflix", "spotify", "hulu", "disney", "apple.com", "github", "openai")),
    ]
    for category, needles in mapping:
        if any(n in blob for n in needles):
            return category
    return CashFlowCategory.OTHER


@dataclass
class DetectedRecurrence:
    name: str
    amount: float
    frequency: Frequency
    anchor_date: date
    category: CashFlowCategory
    min_amount: float | None
    max_amount: float | None
    confidence: float
    sample_count: int
    reason: str


def detect_recurrences(
    rows: list[tuple[date, str, float]],
    existing_names: set[str] | None = None,
) -> list[DetectedRecurrence]:
    groups: dict[str, list[tuple[date, str, float]]] = defaultdict(list)
    for when, name, amount in rows:
        groups[normalize_name(name)].append((when, name, amount))

    existing = {n.lower() for n in (existing_names or set())}
    found: list[DetectedRecurrence] = []
    for _key, items in groups.items():
        items = sorted(items, key=lambda x: x[0])
        if len(items) < 2:
            continue
        display = max((name for _, name, _ in items), key=len)
        if display.lower() in existing:
            continue
        amounts = [amt for _, _, amt in items]
        dates = [when for when, _, _ in items]
        deltas = [(b - a).days for a, b in zip(dates, dates[1:]) if (b - a).days > 0]
        if not deltas:
            continue
        median_delta = statistics.median(deltas)
        freq, freq_score = _frequency_from_deltas(dates, deltas, median_delta)
        if freq is None:
            continue
        median_amt = statistics.median(amounts)
        spread = max(amounts) - min(amounts)
        variable = spread > max(25.0, abs(median_amt) * 0.25)
        regularity = 1.0 - min(1.0, (statistics.pstdev(deltas) / max(median_delta, 1)) if len(deltas) > 1 else 0.2)
        count_score = min(1.0, len(items) / 6.0)
        confidence = round(0.45 * freq_score + 0.35 * regularity + 0.20 * count_score, 3)
        if confidence < 0.45:
            continue
        found.append(
            DetectedRecurrence(
                name=display.title() if display.islower() else display,
                amount=round(median_amt, 2),
                frequency=freq,
                anchor_date=dates[-1],
                category=guess_category(display, median_amt),
                min_amount=round(min(amounts), 2) if variable else None,
                max_amount=round(max(amounts), 2) if variable else None,
                confidence=confidence,
                sample_count=len(items),
                reason=(
                    f"{len(items)} hits, median every {median_delta:.0f} days "
                    f"→ {freq.label}"
                ),
            )
        )
    found.sort(key=lambda x: (-x.confidence, x.name))
    return found


def _frequency_from_deltas(
    dates: list[date], deltas: list[int], median_delta: float
) -> tuple[Frequency | None, float]:
    days = {d.day for d in dates}
    if days == {1, 15} and len(dates) >= 3:
        return Frequency.SEMI_MONTHLY, 0.95
    last_days = 0
    for d in dates:
        nxt = date(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1)
        if d.day == (nxt - timedelta(days=1)).day:
            last_days += 1
    if last_days >= max(2, len(dates) - 1) and 27 <= median_delta <= 32:
        return Frequency.LAST_DAY_OF_MONTH, 0.9
    candidates = [
        (Frequency.WEEKLY, 7, 2),
        (Frequency.BIWEEKLY, 14, 3),
        (Frequency.MONTHLY, 30.4, 4),
        (Frequency.YEARLY, 365, 20),
    ]
    best: tuple[Frequency, float] | None = None
    for freq, target, slack in candidates:
        err = abs(median_delta - target)
        if err <= slack:
            score = max(0.0, 1.0 - err / (slack + 0.1))
            if best is None or score > best[1]:
                best = (freq, score)
    if best is None:
        return None, 0.0
    return best
