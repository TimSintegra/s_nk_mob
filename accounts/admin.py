from django.contrib import admin

from .models import Master


@admin.register(Master)
class MasterAdmin(admin.ModelAdmin):
    list_display = ["full_name", "phone", "brigade", "workers_count", "is_active"]
    list_filter = ["brigade", "is_active"]
    search_fields = ["full_name", "phone"]
    filter_horizontal = ["workers"]

    @admin.display(description="Рабочих")
    def workers_count(self, obj):
        return obj.workers.count()
