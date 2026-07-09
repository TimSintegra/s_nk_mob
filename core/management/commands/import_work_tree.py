"""
Import work tree from structured Excel workbook "Структура ЕР.xlsx".

Uses the HIERARCHY NUMBERING system (1., 2.1, 2.1.1, etc.) to determine
parent-child relationships. This is the single source of truth for the tree.

Each cell that starts with a number like "2.1.1 CS00-01 ..." is a node.
The number prefix defines the parent: "2.1.1" → parent is "2.1".

Units (метр, шт) are attributes on elements, not tree nodes.
"""

import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from openpyxl import load_workbook

from core.models import WorkNode


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Matches hierarchy number prefix: "1.", "2.1", "2.1.1", "2.1.1.1.3", etc.
HIERARCHY_PREFIX = re.compile(r"^\s*(\d+(?:\.\d+)*)\.\s*")

# Matches codes like CS00-01, EL00-08-02-60, DW00-10-01-01-03
CODE_PATTERN = re.compile(
    r"([A-ZА-ЯЁ]{2}[/A-ZА-ЯЁ]{0,3}(?:\d{2})?(?:-\d+)*)",
    re.IGNORECASE,
)

# Unit keywords — only REAL units of measurement
UNIT_KEYWORDS = re.compile(
    r"^(?:шт(?:ук[аи]?)?|"
    r"метры?|метр|"
    r"тонны?|тонна|тонн|"
    r"м[234]|"
    r"кг|"
    r"килограмм[ыа]?|"
    r"100м(?:2)?|"
    r"10м[23]|"
    r"модуль|комплект|"
    r"т[\*\.]км|"
    r"усл\.\s*метр|"
    r"лоток|"
    r"комплект)$",
    re.IGNORECASE,
)

CODE_TRANSLATION = str.maketrans({
    "А": "A", "В": "B", "С": "C", "Е": "E", "Н": "H",
    "К": "K", "М": "M", "О": "O", "Р": "P", "Т": "T",
    "Х": "X", "У": "Y", "І": "I", "Ї": "I", "Ё": "E",
    "а": "A", "в": "B", "с": "C", "е": "E", "н": "H",
    "к": "K", "м": "M", "о": "O", "р": "P", "т": "T",
    "х": "X", "у": "Y", "і": "I", "ї": "I", "ё": "E",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_code(code: str) -> str:
    return code.translate(CODE_TRANSLATION).upper()


def clean(text: str) -> str:
    """Normalize whitespace, strip leading punctuation."""
    if not text:
        return ""
    t = str(text).replace("\r", " ").replace("\n", " ").replace("\xa0", " ")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^[\s.\-–—:]+", "", t)
    return t.strip()


def extract_number_and_rest(text: str) -> tuple[str, str]:
    """Extract hierarchy number prefix and the rest of the text.

    "2.1.1 CS00-01 Монтаж лотков" → ("2.1.1", "CS00-01 Монтаж лотков")
    "2.1 Монтаж лотков" → ("2.1", "Монтаж лотков")
    "метр" → ("", "метр")
    """
    m = HIERARCHY_PREFIX.match(text)
    if m:
        number = m.group(1)
        rest = text[m.end():].strip()
        return number, rest
    return "", text.strip()


def extract_code(text: str) -> tuple[str, str]:
    """Extract code and remaining name from text.

    "CS00-01 Монтаж лотков" → ("CS00-01", "Монтаж лотков")
    "Монтаж лотков" → ("", "Монтаж лотков")
    """
    m = CODE_PATTERN.search(text)
    if not m:
        return "", text.strip()
    code = normalize_code(m.group(1))
    name = text[m.end():].strip()
    return code, name or code


def is_unit(text: str) -> bool:
    if not text or len(text) > 30:
        return False
    if CODE_PATTERN.search(text):
        return False
    return bool(UNIT_KEYWORDS.match(text.strip()))


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Import work tree from structured Excel workbook"

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)
        parser.add_argument("--clear", action="store_true",
                            help="Deactivate all existing nodes before import")
        parser.add_argument("--verbose", action="store_true",
                            help="Print detailed info for each node")

    def handle(self, *args, **options):
        file_path = Path(options["file_path"])
        if not file_path.exists():
            raise CommandError(f"File not found: {file_path}")

        workbook = load_workbook(file_path, data_only=True)
        if not workbook.worksheets:
            raise CommandError("No sheets in workbook.")

        verbose = options["verbose"]

        if options["clear"]:
            deactivated = WorkNode.objects.update(is_active=False)
            self.stdout.write(f"Deactivated: {deactivated}")

        total_c = total_u = 0

        with transaction.atomic():
            for sheet in workbook.worksheets:
                self.stdout.write(f"\n{'=' * 60}")
                self.stdout.write(f"Sheet: {sheet.title}")

                c, u = self.import_sheet(sheet, verbose)
                total_c += c
                total_u += u

            # Post-processing: clear units from parent nodes
            cleared = self.clear_units_from_parents()
            if cleared:
                self.stdout.write(f"Cleared units from {cleared} parent nodes")

        self.stdout.write(
            self.style.SUCCESS(f"\nDone. Created: {total_c}, Updated: {total_u}")
        )

    # ------------------------------------------------------------------
    # Sheet import
    # ------------------------------------------------------------------

    def import_sheet(self, sheet, verbose=False):
        grid = self._read_grid(sheet)

        # Root from A1
        root_text = grid.get((1, 1), "")
        if not root_text:
            self.stdout.write(self.style.WARNING("  Skipped: no A1"))
            return 0, 0

        # Parse root: may have number "1." or just code
        root_number, root_rest = extract_number_and_rest(root_text)
        root_code, root_name = extract_code(root_rest)
        if not root_code:
            root_code = self._sheet_code(sheet.title)
        if not root_name:
            root_name = root_rest or root_text

        root_node, _ = self._upsert(
            f"{sheet.title}:A1", root_code, root_name, None,
        )
        # Map: "1" → root_node (strip the trailing dot from "1.")
        number_map = {}
        if root_number:
            number_map[root_number] = root_node

        self.stdout.write(f"  Root: {root_code} | {root_name[:50]}")

        # Band starts from row 2 (for unit tracking)
        band_starts = self._band_starts_from_row2(grid)
        band_units = {s: "" for s in band_starts}  # current unit per band

        created = updated = 0
        max_row = max((r for r, _ in grid), default=1)

        for row_num in range(2, max_row + 1):
            for col in sorted(c for r, c in grid if r == row_num):
                text = grid[(row_num, col)]
                if not text:
                    continue

                # Skip root (already handled)
                if row_num == 1 and col == 1:
                    continue

                band = self._resolve_band(col, band_starts)

                # Unit cell → update band unit, skip
                if is_unit(text):
                    if band is not None:
                        band_units[band] = text.strip()
                    if verbose:
                        self.stdout.write(
                            f"    [R{row_num}C{col:2d}] UNIT: {text[:30]}"
                        )
                    continue

                # Parse number prefix and content
                number, rest = extract_number_and_rest(text)

                if number:
                    # Numbered cell → tree node
                    # Find parent by looking up prefix (everything before last dot)
                    parent = self._find_parent(number, number_map, root_node)

                    # Extract code and name from the rest
                    code, name = extract_code(rest)
                    if not code:
                        code = ""
                    if not name:
                        name = rest

                    # Determine unit: only for leaf nodes (cells deeper than
                    # their children). We apply unit for all numbered cells
                    # and clear_units_from_parents() will clean up later.
                    unit = band_units.get(band, "") if band is not None else ""

                    node, was_new = self._upsert(
                        f"{sheet.title}:R{row_num}C{col}",
                        code, name, parent, unit,
                    )
                    created += int(was_new)
                    updated += int(not was_new)

                    # Register in number map
                    number_map[number] = node

                    depth = number.count(".")
                    if verbose:
                        self.stdout.write(
                            f"    [R{row_num}C{col:2d}] {number:15s} "
                            f"{'  ' * depth}{code or '—':20s} {name[:30]}"
                            + (f" [{unit}]" if unit else "")
                        )
                else:
                    # No number → could be a codeless label or unnumbered cell
                    # These are rare; create as child of last numbered node
                    # in this band, or skip
                    if verbose:
                        self.stdout.write(
                            f"    [R{row_num}C{col:2d}] SKIP (no number): "
                            f"{text[:40]}"
                        )

        self.stdout.write(f"  Created: {created}, Updated: {updated}")
        return created, updated

    # ------------------------------------------------------------------
    # Parent finding
    # ------------------------------------------------------------------

    def _find_parent(self, number: str, number_map: dict, root_node) -> WorkNode:
        """Find the parent node for a given hierarchy number.

        "2.1.1" → parent prefix is "2.1"
        "2.1" → parent prefix is "2"
        "2" → parent is root
        """
        parts = number.split(".")
        if len(parts) <= 1:
            # Direct child of root: "2" → parent is root
            return root_node

        # Parent prefix = all parts except the last one
        parent_prefix = ".".join(parts[:-1])

        if parent_prefix in number_map:
            return number_map[parent_prefix]

        # Fallback: try shorter prefixes
        for i in range(len(parts) - 1, 0, -1):
            short_prefix = ".".join(parts[:i])
            if short_prefix in number_map:
                return number_map[short_prefix]

        return root_node

    # ------------------------------------------------------------------
    # Grid
    # ------------------------------------------------------------------

    def _read_grid(self, sheet):
        grid = {}
        for row in sheet.iter_rows():
            for cell in row:
                if cell.value is not None:
                    val = clean(str(cell.value))
                    if val:
                        grid[(cell.row, cell.column)] = val
        return grid

    # ------------------------------------------------------------------
    # Bands (for unit tracking only)
    # ------------------------------------------------------------------

    def _band_starts_from_row2(self, grid):
        return sorted({col for (r, col), _ in grid.items() if r == 2})

    def _resolve_band(self, col, band_starts):
        best = None
        for s in band_starts:
            if s <= col:
                best = s
            else:
                break
        return best

    # ------------------------------------------------------------------
    # DB
    # ------------------------------------------------------------------

    def _upsert(self, source_key, code, name, parent, unit=""):
        return WorkNode.objects.update_or_create(
            source_key=source_key,
            defaults={
                "code": code,
                "name": name,
                "parent": parent,
                "unit": unit,
                "is_active": True,
            },
        )

    def _sheet_code(self, title):
        m = CODE_PATTERN.match(title)
        if m:
            return normalize_code(m.group(1))
        return title[:10]

    # ------------------------------------------------------------------
    # Post-processing
    # ------------------------------------------------------------------

    def clear_units_from_parents(self):
        """Remove units from nodes that have active children."""
        parent_ids = WorkNode.objects.filter(
            is_active=True,
            children__is_active=True,
        ).values_list("id", flat=True).distinct()

        return WorkNode.objects.filter(
            id__in=list(parent_ids),
        ).exclude(unit="").update(unit="")
