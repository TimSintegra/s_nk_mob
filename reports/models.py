from accounts.models import Master
from django.db import models

from core.models import Brigade, WorkNode, Worker


class DailyReport(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_DONE = "done"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Черновик"),
        (STATUS_DONE, "Завершён"),
    ]

    date = models.DateField("Дата")
    master = models.ForeignKey(
        Master,
        on_delete=models.PROTECT,
        related_name="daily_reports",
        verbose_name="Мастер",
    )
    brigade = models.ForeignKey(
        Brigade,
        on_delete=models.PROTECT,
        related_name="daily_reports",
        verbose_name="Бригада",
    )
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Дневной отчёт"
        verbose_name_plural = "Дневные отчёты"
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.date} — {self.master}"


class ReportWorkItem(models.Model):
    report = models.ForeignKey(
        DailyReport,
        on_delete=models.CASCADE,
        related_name="work_items",
        verbose_name="Отчёт",
    )
    work_node = models.ForeignKey(
        WorkNode,
        on_delete=models.PROTECT,
        related_name="report_items",
        verbose_name="Работа",
    )
    site_name = models.CharField("Объект", max_length=255)
    title = models.CharField("Титул", max_length=255, blank=True)
    project_section = models.CharField("Раздел проекта", max_length=255, blank=True)
    quantity = models.DecimalField("Объём", max_digits=10, decimal_places=2)
    comment = models.TextField("Комментарий", blank=True)

    class Meta:
        verbose_name = "Работа в отчёте"
        verbose_name_plural = "Работы в отчёте"

    def __str__(self):
        return f"{self.site_name} — {self.work_node}"


class ReportWorkerEntry(models.Model):
    STATUS_PRESENT = "present"
    STATUS_ABSENT = "absent"
    STATUS_SICK = "sick"
    STATUS_VACATION = "vacation"

    STATUS_CHOICES = [
        (STATUS_PRESENT, "Работал"),
        (STATUS_ABSENT, "Не пришёл"),
        (STATUS_SICK, "Болеет"),
        (STATUS_VACATION, "Отпуск"),
    ]

    report = models.ForeignKey(
        DailyReport,
        on_delete=models.CASCADE,
        related_name="worker_entries",
        verbose_name="Отчёт",
    )
    worker = models.ForeignKey(
        Worker,
        on_delete=models.PROTECT,
        related_name="report_entries",
        verbose_name="Рабочий",
        null=True,
        blank=True,
    )
    temporary_worker_name = models.CharField("Добавленный рабочий", max_length=255, blank=True)
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES)
    hours = models.DecimalField("Часы", max_digits=5, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Рабочий в отчёте"
        verbose_name_plural = "Рабочие в отчёте"

    def __str__(self):
        if self.worker:
            return self.worker.full_name
        return self.temporary_worker_name