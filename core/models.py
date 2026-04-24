from django.db import models


class Brigade(models.Model):
    name = models.CharField("Название", max_length=255, unique=True)

    class Meta:
        verbose_name = "Бригада"
        verbose_name_plural = "Бригады"

    def __str__(self):
        return self.name


class Worker(models.Model):
    full_name = models.CharField("ФИО", max_length=255)
    brigade = models.ForeignKey(
        Brigade,
        on_delete=models.PROTECT,
        related_name="workers",
        verbose_name="Бригада",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Рабочий"
        verbose_name_plural = "Рабочие"

    def __str__(self):
        return self.full_name


class WorkNode(models.Model):
    code = models.CharField("Код", max_length=100, unique=True)
    name = models.CharField("Название", max_length=700)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="children",
        verbose_name="Родитель",
        null=True,
        blank=True,
    )
    unit = models.CharField("Единица измерения", max_length=50, blank=True)
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Работа"
        verbose_name_plural = "Дерево работ"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def is_leaf(self):
        return not self.children.exists()