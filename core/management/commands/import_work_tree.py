from dataclasses import dataclass
from pathlib import Path
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from openpyxl import load_workbook

from core.models import WorkNode


CODE_PATTERN = re.compile(r"([A-ZА-ЯЁ]{2}(?:\d{2}|/[A-Z]{2})(?:-\d+)*)", re.IGNORECASE)
GROUP_PATTERN = re.compile(r"^\s*\d+\.\s")

CODE_TRANSLATION = str.maketrans(
    {
        "А": "A",
        "В": "B",
        "С": "C",
        "Е": "E",
        "Н": "H",
        "К": "K",
        "М": "M",
        "О": "O",
        "Р": "P",
        "Т": "T",
        "Х": "X",
        "У": "Y",
        "І": "I",
        "Ї": "I",
        "Ё": "E",
        "а": "A",
        "в": "B",
        "с": "C",
        "е": "E",
        "н": "H",
        "к": "K",
        "м": "M",
        "о": "O",
        "р": "P",
        "т": "T",
        "х": "X",
        "у": "Y",
        "і": "I",
        "ї": "I",
        "ё": "E",
    }
)


@dataclass(frozen=True)
class SectionConfig:
    root_code: str
    root_name: str | None
    root_cell: str
    blue_row: int
    blue_starts: list[int]
    green_row: int
    green_starts: list[int]
    end_row: int


@dataclass
class BandState:
    blue: WorkNode | None = None
    green: WorkNode | None = None
    group: WorkNode | None = None
    label: WorkNode | None = None


class Command(BaseCommand):
    help = "Import work tree from the structured Excel workbook"

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)
        parser.add_argument("--clear", action="store_true")

    def handle(self, *args, **options):
        file_path = Path(options["file_path"])
        if not file_path.exists():
            raise CommandError(f"Файл не найден: {file_path}")

        workbook = load_workbook(file_path, data_only=True)
        if not workbook.worksheets:
            raise CommandError("В книге нет листов.")

        if options["clear"]:
            deactivated_count = WorkNode.objects.update(is_active=False)
        else:
            deactivated_count = 0

        created_count = 0
        updated_count = 0
        imported_keys = set()

        with transaction.atomic():
            for sheet in workbook.worksheets:
                section = self.detect_section(sheet)
                if section is None:
                    self.stdout.write(self.style.WARNING(
                        f"Пропущен лист '{sheet.title}': не удалось определить заголовок"
                    ))
                    continue

                self.stdout.write(f"  Лист '{sheet.title}' → {section.root_code} "
                                  f"(синих={len(section.blue_starts)} "
                                  f"зелёных={len(section.green_starts)} "
                                  f"строк={section.end_row})")

                s_created, s_updated, s_keys = self.import_section(sheet, section)
                created_count += s_created
                updated_count += s_updated
                imported_keys.update(s_keys)

        self.stdout.write(self.style.SUCCESS("Импорт завершён."))
        self.stdout.write(f"Создано: {created_count}")
        self.stdout.write(f"Обновлено: {updated_count}")
        self.stdout.write(f"Уникальных узлов: {len(imported_keys)}")
        if options["clear"]:
            self.stdout.write(f"Скрыто устаревших узлов: {deactivated_count}")

    def detect_section(self, sheet):
        """Автоопределение структуры раздела из листа Excel.

        Ожидаемая раскладка листа:
          Строка 1 (розовая)  — корень раздела, напр. "EL00 ЭЛЕКТРОМОНТАЖНЫЕ РАБОТЫ"
          Строка 2 (синяя)    — подразделы первого уровня
          Строка 3 (зелёная)  — подразделы второго уровня
          Строки 4+ (белые)   — конкретные работы
        """
        # --- корень: ячейка A1 ---
        root_cell = sheet.cell(row=1, column=1)
        root_text = str(root_cell.value).strip() if root_cell.value is not None else ""

        if not root_text:
            root_text = sheet.title.strip()
        if not root_text:
            return None

        root_text = self.normalize_text(root_text)
        extracted = self.extract_code_and_name(root_text)
        root_code = extracted[0] if extracted else root_text

        # --- синие колонки из строки 2 ---
        blue_starts = sorted(set(
            cell.column for cell in sheet[2]
            if cell.value and isinstance(cell.value, str) and cell.value.strip()
        ))

        # --- зелёные колонки из строки 3 ---
        green_starts = sorted(set(
            cell.column for cell in sheet[3]
            if cell.value and isinstance(cell.value, str) and cell.value.strip()
        ))

        # Если какой-то ряд пуст — подменяем умолчанием
        if not blue_starts:
            blue_starts = [1]
        if not green_starts:
            green_starts = blue_starts[:]  # если зелёных нет, используем синие

        return SectionConfig(
            root_code=root_code,
            root_name=None,
            root_cell="A1",
            blue_row=2,
            blue_starts=blue_starts,
            green_row=3,
            green_starts=green_starts,
            end_row=sheet.max_row,
        )

    def import_section(self, sheet, section):
        band_states = self.build_band_states(section)
        created_count = 0
        updated_count = 0
        imported_keys = set()

        root_source_key = f"{section.root_code}:{section.root_cell}"
        root_cell_value = sheet[section.root_cell].value
        if section.root_name:
            root_name = section.root_name
        else:
            extracted_root = self.extract_code_and_name(self.normalize_text(root_cell_value)) if isinstance(root_cell_value, str) else None
            root_name = extracted_root[1] if extracted_root else self.extract_cell_name(root_cell_value)
        root_node, created = self.upsert_node(
            source_key=root_source_key,
            code=section.root_code,
            name=root_name or section.root_code,
            parent=None,
        )
        created_count += int(created)
        updated_count += int(not created)
        imported_keys.add(root_source_key)

        blue_created, blue_updated = self.assign_blue_node(root_node, section, band_states, imported_keys, sheet)
        created_count += blue_created
        updated_count += blue_updated

        green_created, green_updated = self.assign_green_nodes(root_node, section, band_states, imported_keys, sheet)
        created_count += green_created
        updated_count += green_updated

        for row_index in range(section.green_row + 1, section.end_row + 1):
            row = sheet[row_index]
            for cell in row:
                if not isinstance(cell.value, str):
                    continue

                text = self.normalize_text(cell.value)
                if not text:
                    continue

                band_start = self.resolve_band_start(cell.column, section.green_starts)
                if band_start is None:
                    continue

                state = band_states[band_start]
                source_key = f"{section.root_code}:{cell.coordinate}"
                imported_keys.add(source_key)

                extracted = self.extract_code_and_name(text)
                if extracted:
                    code, name = extracted
                    if GROUP_PATTERN.match(text):
                        parent = state.green or state.blue or root_node
                        node, created = self.upsert_node(
                            source_key=source_key,
                            code=code,
                            name=name,
                            parent=parent,
                        )
                        state.group = node
                        state.label = None
                    else:
                        parent = state.label or state.group or state.green or state.blue or root_node
                        node, created = self.upsert_node(
                            source_key=source_key,
                            code=code,
                            name=name,
                            parent=parent,
                        )
                    created_count += int(created)
                    updated_count += int(not created)
                    continue

                parent = state.group or state.green or state.blue or root_node
                node, created = self.upsert_node(
                    source_key=source_key,
                    code="",
                    name=text,
                    parent=parent,
                )
                state.label = node
                created_count += int(created)
                updated_count += int(not created)

        return created_count, updated_count, imported_keys

    def assign_blue_node(self, root_node, section, band_states, imported_keys, sheet):
        created_count = 0
        updated_count = 0
        for cell in sheet[section.blue_row]:
            if not isinstance(cell.value, str):
                continue

            text = self.normalize_text(cell.value)
            if not text:
                continue

            blue_start = self.resolve_band_start(cell.column, section.blue_starts)
            if blue_start is None:
                continue

            source_key = f"{section.root_code}:{cell.coordinate}"
            imported_keys.add(source_key)

            extracted = self.extract_code_and_name(text)
            code = extracted[0] if extracted else ""
            name = extracted[1] if extracted else text

            node, created = self.upsert_node(
                source_key=source_key,
                code=code,
                name=name,
                parent=root_node,
            )

            for green_start in self.green_starts_for_blue(section, blue_start):
                state = band_states[green_start]
                state.blue = node
                state.green = None
                state.group = None
                state.label = None

            created_count += int(created)
            updated_count += int(not created)

        return created_count, updated_count

    def assign_green_nodes(self, root_node, section, band_states, imported_keys, sheet):
        created_count = 0
        updated_count = 0

        for cell in sheet[section.green_row]:
            if not isinstance(cell.value, str):
                continue

            text = self.normalize_text(cell.value)
            if not text:
                continue

            green_start = self.resolve_band_start(cell.column, section.green_starts)
            if green_start is None:
                continue

            state = band_states[green_start]
            parent = state.blue or root_node
            source_key = f"{section.root_code}:{cell.coordinate}"
            imported_keys.add(source_key)

            extracted = self.extract_code_and_name(text)
            code = extracted[0] if extracted else ""
            name = extracted[1] if extracted else text

            node, created = self.upsert_node(
                source_key=source_key,
                code=code,
                name=name,
                parent=parent,
            )

            state.green = node
            state.group = None
            state.label = None

            created_count += int(created)
            updated_count += int(not created)

        return created_count, updated_count

    def build_band_states(self, section):
        return {start: BandState() for start in section.green_starts}

    def green_starts_for_blue(self, section, blue_start):
        blue_starts = sorted(section.blue_starts)
        start_index = blue_starts.index(blue_start)
        if start_index + 1 < len(blue_starts):
            end = blue_starts[start_index + 1] - 1
        else:
            end = max(section.green_starts, default=0) + 50
        return [gs for gs in section.green_starts if blue_start <= gs <= end]

    def resolve_band_start(self, column, starts):
        active_start = None
        for start in sorted(starts):
            if start <= column:
                active_start = start
            else:
                break
        return active_start

    def upsert_node(self, source_key, code, name, parent):
        node, created = WorkNode.objects.update_or_create(
            source_key=source_key,
            defaults={
                "code": code,
                "name": name,
                "parent": parent,
                "unit": "",
                "is_active": True,
            },
        )
        return node, created

    def normalize_text(self, value):
        text = value.replace("\r", " ").replace("\n", " ").replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"^[\s\.\-–—:]+", "", text)
        return text.strip()

    def extract_cell_name(self, value):
        if not isinstance(value, str):
            return ""
        return self.normalize_text(value)

    def normalize_code(self, code):
        return code.translate(CODE_TRANSLATION).upper()

    def extract_code_and_name(self, value):
        match = CODE_PATTERN.search(value)
        if not match:
            return None

        code = self.normalize_code(match.group(1))
        name = self.normalize_text(value[match.end():])
        return code, name or code
