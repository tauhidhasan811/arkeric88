"""Read and rank the structured retreat workbook without an external RAG service."""

from functools import lru_cache
from pathlib import Path
import re
from zipfile import ZipFile
from xml.etree import ElementTree


WORKBOOK_PATH = Path(__file__).resolve().parents[2] / "data" / "Retreat Master Database.xlsx"
XML_NAMESPACE = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _normalize(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _column_index(cell_reference: str) -> int:
    letters = re.match(r"[A-Z]+", cell_reference or "A")
    index = 0
    for letter in (letters.group(0) if letters else "A"):
        index = index * 26 + ord(letter) - ord("A") + 1
    return index - 1


def _cell_value(cell, shared_strings: list[str]) -> str:
    value = cell.find("m:v", XML_NAMESPACE)
    if cell.attrib.get("t") == "inlineStr":
        return "".join(
            text.text or "" for text in cell.findall(".//m:t", XML_NAMESPACE)
        )
    if value is None:
        return ""
    if cell.attrib.get("t") == "s":
        return shared_strings[int(value.text)]
    return value.text or ""


@lru_cache(maxsize=1)
def load_retreat_catalog() -> list[dict]:
    """Load the first worksheet into dictionaries using Python's standard library."""
    if not WORKBOOK_PATH.exists():
        return []

    with ZipFile(WORKBOOK_PATH) as workbook:
        shared_root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
        shared_strings = [
            "".join(text.text or "" for text in item.findall(".//m:t", XML_NAMESPACE))
            for item in shared_root.findall("m:si", XML_NAMESPACE)
        ]
        sheet_root = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))

    rows: list[list[str]] = []
    for row in sheet_root.findall(".//m:row", XML_NAMESPACE):
        values: list[str] = []
        for cell in row.findall("m:c", XML_NAMESPACE):
            column = _column_index(cell.attrib.get("r", "A1"))
            while len(values) <= column:
                values.append("")
            values[column] = _cell_value(cell, shared_strings)
        rows.append(values)

    if len(rows) < 4:
        return []
    # The source workbook includes a Primary Modalities header but its data rows
    # omit that column, so remove the empty header to preserve the financial fields.
    headers = rows[2][:26] + rows[2][27:]
    return [
        {
            headers[index].strip(): value.strip()
            for index, value in enumerate(row)
            if index < len(headers) and headers[index].strip()
        }
        for row in rows[3:]
        if len(row) > 1 and row[1].strip()
    ]


def _nightly_price(record: dict) -> float | None:
    match = re.search(r"[\d,]+", record.get("Avg Night", ""))
    return float(match.group(0).replace(",", "")) if match else None


def _geography_score(record: dict, location: str) -> int:
    target = _normalize(location)
    if not target:
        return 0
    property_name = _normalize(record.get("Property Name"))
    region = _normalize(record.get("Region"))
    country = _normalize(record.get("Country"))
    if target == region or target == country:
        return 160
    if target in region or region in target:
        return 145
    if target in property_name:
        return 135
    if target in country or country in target:
        return 120
    return 0


def find_retreat_candidates(
    city_name: str,
    preferred_region: str = "",
    facility_terms: str = "",
    nightly_budget: float | None = None,
    limit: int = 5,
) -> list[dict]:
    """Rank retreats by geography first, facilities/profile second, and budget third."""
    catalog = load_retreat_catalog()
    if not catalog:
        return []

    city_matches = [item for item in catalog if _geography_score(item, city_name) > 0]
    region_matches = [
        item for item in catalog if _geography_score(item, preferred_region) > 0
    ]
    # The chosen destination is most specific, then the requested broader region.
    pool = city_matches or region_matches
    if not pool:
        return []
    desired_tokens = set(_normalize(facility_terms).split())

    def score(record: dict) -> tuple[float, float, float]:
        geography = max(
            _geography_score(record, city_name),
            _geography_score(record, preferred_region),
        )
        searchable_fields = (
            "Core Philosophy",
            "Primary Category",
            "Emotional Tone",
            "Structure",
            "Physical Intensity",
            "Transform Focus",
            "Archetypes",
            "Primary Modalities",
            "Diagnostics",
            "Spa",
            "Nutrition",
            "Mindfulness",
            "Fitness",
        )
        haystack = _normalize(" ".join(record.get(field, "") for field in searchable_fields))
        facility_fit = float(sum(1 for token in desired_tokens if token in haystack))
        price = _nightly_price(record)
        if nightly_budget and price is not None:
            budget_fit = 20 if price <= nightly_budget else -min(20, (price - nightly_budget) / nightly_budget * 20)
        else:
            budget_fit = 0
        return geography, facility_fit, budget_fit

    return sorted(pool, key=score, reverse=True)[:limit]


def retreat_facilities(record: dict) -> list[str]:
    """Expose the workbook's useful wellness offerings as a compact list."""
    facilities = []
    modalities = record.get("Primary Modalities", "").strip()
    if modalities:
        facilities.append(modalities)
    for field in ("Diagnostics", "Spa", "Nutrition", "Mindfulness", "Fitness"):
        value = record.get(field, "").strip()
        if value and _normalize(value) not in {"no", "none", "0"}:
            facilities.append(f"{field}: {value}")
    return facilities
