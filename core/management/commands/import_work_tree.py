from pathlib import Path

from django.core.management.base import BaseCommand
from openpyxl import load_workbook

from core.models import WorkNode


class Command(BaseCommand):
    help = "Import work tree from Excel file"

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)
        parser.add_argument("--clear", action="store_true")

    def handle(self, *args, **options):
        file_path = Path(options["file_path"])

        if not file_path.exists():
            self.stderr.write(f"Файл не найден: {file_path}")
            return

        if options["clear"]:
            WorkNode.objects.all().delete()
            self.stdout.write("Старое дерево работ удалено.")

        workbook = load_workbook(file_path, data_only=True)
        sheet = workbook["Лист1"]

        rows = []

        for row in sheet.iter_rows(min_row=2, values_only=True):
            code = row[2]
            name = row[7]
            unit = row[8]

            if not code:
                continue

            code = str(code).strip()
            name = str(name).strip() if name else ""
            unit = str(unit).strip() if unit else ""

            if not code:
                continue

            rows.append(
                {
                    "code": code,
                    "name": name,
                    "unit": unit,
                }
            )

        known_names = {item["code"]: item["name"] for item in rows if item["name"]}
        known_units = {item["code"]: item["unit"] for item in rows if item["unit"]}

        all_codes = set()

        for item in rows:
            for parent_code in self.get_code_chain(item["code"]):
                all_codes.add(parent_code)

        created_count = 0
        updated_count = 0
        technical_count = 0

        for code in sorted(all_codes):
            name = known_names.get(code, "")
            unit = known_units.get(code, "")

            if not name:
                name = "Без названия"
                technical_count += 1

            _, created = WorkNode.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "unit": unit,
                    "is_active": True,
                },
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        for code in sorted(all_codes):
            node = WorkNode.objects.get(code=code)
            parent_code = self.get_parent_code(code)

            if not parent_code:
                node.parent = None
            else:
                node.parent = WorkNode.objects.get(code=parent_code)

            node.save(update_fields=["parent"])

        self.stdout.write(self.style.SUCCESS("Импорт завершён."))
        self.stdout.write(f"Создано: {created_count}")
        self.stdout.write(f"Обновлено: {updated_count}")
        self.stdout.write(f"Технических веток без названия: {technical_count}")

    def get_parent_code(self, code):
        parts = code.split("-")

        if len(parts) <= 1:
            return None

        return "-".join(parts[:-1])

    def get_code_chain(self, code):
        parts = code.split("-")
        chain = []

        for index in range(1, len(parts) + 1):
            chain.append("-".join(parts[:index]))

        return chain