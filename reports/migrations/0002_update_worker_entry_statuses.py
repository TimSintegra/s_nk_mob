# Generated manually for the timesheet workflow.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="reportworkerentry",
            name="status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("sick", "Больничный"),
                    ("admin", "Административный"),
                    ("vacation", "Отпуск"),
                    ("study", "Ученический"),
                ],
                max_length=20,
                verbose_name="Статус",
            ),
        ),
    ]
