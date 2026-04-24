from django.db import models
from django.contrib.auth.hashers import check_password, make_password

from core.models import Brigade


class Master(models.Model):
    full_name = models.CharField("ФИО", max_length=255)
    phone = models.CharField("Телефон", max_length=50, unique=True)
    password = models.CharField("Пароль", max_length=255)
    brigade = models.ForeignKey(
        Brigade,
        on_delete=models.PROTECT,
        related_name="masters",
        verbose_name="Бригада",
    )
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Мастер"
        verbose_name_plural = "Мастера"

    def __str__(self):
        return self.full_name

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def save(self, *args, **kwargs):
        if self.password and not self.password.startswith("pbkdf2_"):
            self.set_password(self.password)
        super().save(*args, **kwargs)