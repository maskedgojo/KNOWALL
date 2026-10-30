"""Heuristic extraction for synthetic occupancy letters/rental agreements."""
import re

LABELS = {
    "resident_name": ("resident name", "tenant name", "owner name"),
    "tower": ("tower", "block"),
    "flat_number": ("flat number", "flat no", "flat"),
    "category": ("resident category", "occupant category"),
    "society": ("society", "residential complex"),
}


def extract_fields(text: str) -> dict:
    found = {}
    for line in text.splitlines():
        for field, labels in LABELS.items():
            for label in labels:
                match = re.match(r"^\s*" + re.escape(label) + r"\s*[:\-]\s*(.+?)\s*$", line, re.IGNORECASE)
                if match and field not in found:
                    found[field] = match.group(1).strip()
                    break
    return found


def _normalized(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def compare_fields(fields: dict, *, name: str, tower: str, flat: str, category: str) -> tuple[dict, list[str]]:
    expected = {"resident_name": name, "tower": tower, "flat_number": flat, "category": category}
    compared = {}
    warnings = []
    for key, wanted in expected.items():
        extracted = fields.get(key)
        state = "MISSING" if not extracted else "MATCH" if _normalized(extracted) == _normalized(wanted) else "MISMATCH"
        compared[key] = {"entered": wanted, "extracted": extracted, "status": state}
        if state != "MATCH":
            warnings.append(f"{key}: {state.lower().replace('_', ' ')}; manual review required")
    if not fields:
        warnings.append("No recognizable residence fields; inspect original document manually")
    return compared, warnings
