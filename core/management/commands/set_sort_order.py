from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import WorkNode


ROOT_ORDER = [
    "CS00",
    "II00",
    "EL00",
    "EL/II",
    "DW00",
    "ET00",
    "HU00",
]


class Command(BaseCommand):
    help = "Set sort_order for root WorkNodes based on predefined order"

    def handle(self, *args, **options):
        roots = WorkNode.objects.filter(parent__isnull=True, is_active=True)
        updated_count = 0

        with transaction.atomic():
            for i, code_prefix in enumerate(ROOT_ORDER, start=1):
                nodes = roots.filter(code=code_prefix)
                if not nodes.exists():
                    nodes = roots.filter(code__startswith=code_prefix)

                for node in nodes:
                    old_order = node.sort_order
                    node.sort_order = i
                    node.save(update_fields=["sort_order"])
                    updated_count += 1
                    self.stdout.write(
                        f"  {node.code or node.name[:40]:30s} "
                        f"sort_order {old_order} → {i}"
                    )

            # Any remaining root nodes get a high sort_order
            remaining = roots.exclude(sort_order__gte=1).filter(sort_order=0)
            for i, node in enumerate(remaining, start=len(ROOT_ORDER) + 1):
                node.sort_order = i
                node.save(update_fields=["sort_order"])
                updated_count += 1
                self.stdout.write(
                    f"  {node.code or node.name[:40]:30s}"
                    f"sort_order {node.sort_order} → {i} (остальные)"
                )

        self.stdout.write(self.style.SUCCESS(f"Обновлено узлов: {updated_count}"))
