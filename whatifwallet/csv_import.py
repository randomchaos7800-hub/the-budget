"""CSV import for bank ledgers and the original template format."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from .engine import CashFlowCategory, Frequency
from .detect import detect_recurrences

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%b %d, %Y",
    "%B %d, %Y",
)


@dataclass
class ImportedRow:
    date: date
    name: str
    amount: float


def parse_csv(text: str) -> tuple[list[ImportedRow], list[dict], str]:
    """Return (ledger_rows, template_rows, kind)."""
    sample = text.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(sample))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")
    fields = [_norm(h) for h in reader.fieldnames]
    field_map = {_norm(h): h for h in reader.fieldnames if h}
    rows = list(reader)

    if _has(fields, ("name", "item", "template")) and _has(
        fields, ("frequency", "freq", "cadence")
    ):
        templates = [_template_row(r, field_map) for r in rows]
        templates = [t for t in templates if t]
        return [], templates, "templates"

    ledger = [_ledger_row(r, field_map) for r in rows]
    ledger = [r for r in ledger if r]
    return ledger, [], "ledger"


def _template_row(row: dict, field_map: dict[str, str]) -> dict | None:
    name = _get(row, field_map, "name", "item", "template", "description")
    amount_raw = _get(row, field_map, "amount", "amt", "value")
    if not name or amount_raw in (None, ""):
        return None
    amount = _money(amount_raw)
    kind = (_get(row, field_map, "type", "kind") or "").lower()
    if kind.startswith("exp") and amount > 0:
        amount = -amount
    if kind.startswith("inc") and amount < 0:
        amount = abs(amount)
    freq = _get(row, field_map, "frequency", "freq", "cadence") or "monthly"
    category = _get(row, field_map, "category", "cat")
    anchor = _get(row, field_map, "anchor", "anchor_date", "date", "start")
    return {
        "name": name.strip(),
        "amount": amount,
        "frequency": Frequency.parse(freq).value,
        "anchor_date": (_parse_date(anchor) or date.today()).isoformat(),
        "category": CashFlowCategory.parse(category, amount).value,
    }


def _ledger_row(row: dict, field_map: dict[str, str]) -> ImportedRow | None:
    when = _parse_date(
        _get(row, field_map, "date", "posted", "posted_date", "transaction_date", "trans_date")
    )
    name = _get(
        row,
        field_map,
        "description",
        "name",
        "memo",
        "payee",
        "merchant",
        "original_description",
    )
    if when is None or not name:
        return None
    amount = _amount_from_row(row, field_map)
    if amount is None:
        return None
    return ImportedRow(date=when, name=name.strip(), amount=amount)


def _amount_from_row(row: dict, field_map: dict[str, str]) -> float | None:
    debit = _get(row, field_map, "debit", "withdrawal", "outflow")
    credit = _get(row, field_map, "credit", "deposit", "inflow")
    if debit not in (None, "") or credit not in (None, ""):
        out = _money(debit) if debit not in (None, "") else 0.0
        inn = _money(credit) if credit not in (None, "") else 0.0
        return inn - abs(out)
    raw = _get(row, field_map, "amount", "amt", "value", "transaction_amount")
    if raw in (None, ""):
        return None
    return _money(raw)


def _money(value: str | float | int | None) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("$", "")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    if text.endswith("-") and text[:-1].replace(".", "", 1).isdigit():
        text = "-" + text[:-1]
    return float(text)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _norm(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")


def _has(fields: Iterable[str], names: Iterable[str]) -> bool:
    bag = set(fields)
    return any(n in bag for n in names)


def _get(row: dict, field_map: dict[str, str], *names: str) -> str | None:
    for name in names:
        key = field_map.get(name)
        if key is None:
            continue
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def detections_from_ledger(rows: list[ImportedRow], existing_names: set[str]) -> list[dict]:
    detected = detect_recurrences(
        [(r.date, r.name, r.amount) for r in rows], existing_names
    )
    return [
        {
            "name": d.name,
            "amount": d.amount,
            "frequency": d.frequency.value,
            "anchor_date": d.anchor_date.isoformat(),
            "category": d.category.value,
            "min_amount": d.min_amount,
            "max_amount": d.max_amount,
            "confidence": d.confidence,
            "source": "csv",
            "sample_count": d.sample_count,
            "reason": d.reason,
        }
        for d in detected
    ]
