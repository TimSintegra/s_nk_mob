"""
Import work tree from structured Excel workbook "Структура ЕР.xlsx".

Each sheet is an independent root tree. Hierarchy is determined by
code depth (number of dashes), NOT by row number.

Code levels:
  d0 = root or category (e.g. "MOHTA", "EL00")
  d1 = subcategory (e.g. "EL00-08", "CS00-01")
  d2 = group (e.g. "EL00-08-02", "CS00-02-05")
  d3+ = leaf element (e.g. "EL00-08-02-60", "CS00-01-01-13")

Units (метр, шт) are attributes on elements, not tree nodes.

Parent resolution uses per-band state tracking:
  - Each column band has a state tracking the most recent node at each level
  - When a new d1 appears, it becomes the subcategory for its band
  - When a new d2 appears under that d1, it becomes the group
  - When a d3 appears, it becomes a child of the current group (or subcategory)
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from openpyxl import load_workbook

from core.models import WorkNode


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CODE_PATTERN = re.compile(
    r"([A-ZА-ЯЁ]{2}[/A-ZА-ЯЁ]{0,3}(?:\d{2})?(?:-\d+)*)",
    re.IGNORECASE,
)

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


def code_depth(code: str) -> int:
    """Number of dashes = hierarchy depth level."""
    return code.count("-")


def extract_code(text: str) -> tuple[str, str]:
    """Extract code and remaining name from text.
    Returns (code, name) or ("", text) if no code found.
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


def clean(text: str) -> str:
    """Normalize whitespace, strip leading punctuation."""
    if not text:
        return ""
    t = str(text).replace("\r", " ").replace("\n", " ").replace("\xa0", " ")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^[\s.\-–—:]+", "", t)
    return t.strip()


# ---------------------------------------------------------------------------
# Band state — tracks context within a column range
# ---------------------------------------------------------------------------

@dataclass
class BandState:
    """Current context for a column band.

    Each band starts at a specific column (from row 2 category cells).
    As we scan rows, the state updates with the most recent node at each level.

    Variants are tracked per-group (not per-band), because each group
    can have its own set of variants (e.g. "1-жильный" under EL00-08-02
    vs "1-4 жил" under II00-03-01).
    """
    category: Optional[WorkNode] = None
    subcategory: Optional[WorkNode] = None   # d1
    group: Optional[WorkNode] = None         # d2
    group_variant: dict = field(default_factory=dict)  # group_node → variant_node
    unit: str = ""

    @property
    def variant(self):
        """Current variant = the variant for the current group."""
        if self.group and self.group in self.group_variant:
            return self.group_variant[self.group]
        return None

    def set_variant(self, variant):
        """Set variant for the current group."""
        if self.group:
            self.group_variant[self.group] = variant

    def clear_variant_for(self, group):
        """Remove variant when a new group replaces this one."""
        self.group_variant.pop(group, None)


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

            # Post-processing: rebuild tree by code prefix matching
            moved = self.rebuild_tree_by_codes()
            if moved:
                self.stdout.write(f"\nRebuilt {moved} parent links by code prefix")

            # Post-processing: clear units from parent nodes
            cleared = self.clear_units_from_parents()
            if cleared:
                self.stdout.write(f"Cleared units from {cleared} parent nodes")

        self.stdout.write(self.style.SUCCESS(f"\nDone. Created: {total_c}, Updated: {total_u}"))

    # ------------------------------------------------------------------
    # Sheet import
    # ------------------------------------------------------------------

    def import_sheet(self, sheet, verbose=False):
        grid = self._read_grid(sheet)

        # Root from A1
        root_text = grid.get((1, 1), "")
        if not root_text:
            self.stdout.write(self.style.WARNING(f"  Skipped: no A1"))
            return 0, 0

        root_code, root_name = extract_code(root_text)
        if not root_code:
            root_code = self._sheet_code(sheet.title)
        if not root_name:
            root_name = root_text

        root_node, _ = self._upsert(
            f"{sheet.title}:A1", root_code, root_name, None,
        )
        self.stdout.write(f"  Root: {root_code} | {root_name[:50]}")

        # Band starts from row 2 (categories define column ranges)
        band_starts = self._band_starts_from_row2(grid)
        self.stdout.write(f"  Bands: {band_starts}")

        # Initialize band states
        states = {s: BandState() for s in band_starts}

        # Process row 2 — set category for each band
        self._process_row2(grid, sheet.title, root_node, band_starts, states, verbose)

        # Process rows 3+ — all coded cells, units, variants
        created = updated = 0
        max_row = max((r for r, _ in grid), default=1)

        for row_num in range(3, max_row + 1):
            for col in sorted(c for r, c in grid if r == row_num):
                text = grid[(row_num, col)]
                if not text:
                    continue

                band = self._resolve_band(col, band_starts)
                state = states.get(band)
                parent = self._pick_parent(state, root_node)

                # Unit → update state, skip node creation
                if is_unit(text):
                    if state:
                        state.unit = text.strip()
                    if verbose:
                        self.stdout.write(f"    [R{row_num}C{col:2d}] UNIT: {text[:30]}")
                    continue

                # Extract code
                code, name = extract_code(text)

                if code:
                    depth = code_depth(code)
                    unit = ""
                    if depth >= 3 and state:
                        unit = state.unit

                    node, was_new = self._upsert(
                        f"{sheet.title}:R{row_num}C{col}",
                        code, name, parent, unit,
                    )
                    created += int(was_new)
                    updated += int(not was_new)

                    # Update band state based on depth
                    if state:
                        if depth == 1:
                            state.subcategory = node
                            state.group = None
                            state.group_variant.clear()
                            state.unit = ""
                        elif depth == 2:
                            state.group = node
                            state.group_variant.pop(node, None)

                    if verbose:
                        self.stdout.write(
                            f"    [R{row_num}C{col:2d}] d{depth} "
                            f"{code:20s} {name[:35]}"
                            + (f" [{unit}]" if unit else "")
                        )
                else:
                    # Codeless text → variant or label
                    node, was_new = self._upsert(
                        f"{sheet.title}:R{row_num}C{col}",
                        "", name, parent,
                    )
                    created += int(was_new)
                    updated += int(not was_new)

                    if state:
                        state.set_variant(node)

                    if verbose:
                        self.stdout.write(
                            f"    [R{row_num}C{col:2d}] LABEL: {name[:45]}"
                        )

        self.stdout.write(f"  Created: {created}, Updated: {updated}")
        return created, updated

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
    # Bands
    # ------------------------------------------------------------------

    def _band_starts_from_row2(self, grid):
        """Band start columns = non-empty columns in row 2."""
        return sorted({col for (r, col), _ in grid.items() if r == 2})

    def _resolve_band(self, col, band_starts):
        best = None
        for s in band_starts:
            if s <= col:
                best = s
            else:
                break
        return best

    def _pick_parent(self, state, root):
        if state and state.variant:
            return state.variant
        if state and state.group:
            return state.group
        if state and state.subcategory:
            return state.subcategory
        if state and state.category:
            return state.category
        return root

    # ------------------------------------------------------------------
    # Row 2 processing
    # ------------------------------------------------------------------

    def _process_row2(self, grid, sheet_name, root, band_starts, states, verbose):
        """Row 2 cells → category nodes."""
        for (row, col), text in sorted(grid.items()):
            if row != 2:
                continue

            code, name = extract_code(text)
            band = self._resolve_band(col, band_starts)
            state = states.get(band)

            node, _ = self._upsert(
                f"{sheet_name}:R{row}C{col}", code, name, root,
            )

            if state:
                state.category = node
                state.subcategory = None
                state.group = None
                state.group_variant.clear()
                state.unit = ""

            if verbose:
                self.stdout.write(f"    [R2 C{col:2d}] CAT: {name[:50]}")

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

    def rebuild_tree_by_codes(self):
        """Re-parent nodes by longest matching code prefix.

        If B.code starts with A.code + "-", A is parent of B.
        """
        nodes = list(
            WorkNode.objects.filter(is_active=True)
            .exclude(code="")
            .order_by("code")
            .values_list("id", "code", "parent_id")
        )

        code_map = {}
        for nid, code, pid in nodes:
            code_map[code.replace(" ", "")] = (nid, pid)

        moved = 0
        for nid, code, cur_pid in nodes:
            norm = code.replace(" ", "")
            best_parent = None
            best_len = 0

            for ccode, (cid, _) in code_map.items():
                if cid == nid:
                    continue
                if norm.startswith(ccode + "-") and len(ccode) > best_len:
                    best_parent = cid
                    best_len = len(ccode)

            if best_parent and best_parent != cur_pid:
                WorkNode.objects.filter(id=nid).update(parent_id=best_parent)
                moved += 1

        return moved

    def clear_units_from_parents(self):
        """Remove units from nodes that have active children."""
        parent_ids = WorkNode.objects.filter(
            is_active=True,
            children__is_active=True,
        ).values_list("id", flat=True).distinct()

        return WorkNode.objects.filter(
            id__in=list(parent_ids),
        ).exclude(unit="").update(unit="")
