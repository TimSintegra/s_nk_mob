from django.contrib import admin

from .models import Master


@admin.register(Master)
class MasterAdmin(admin.ModelAdmin):
    list_display = ["full_name", "phone", "brigade", "is_active"]
    list_filter = ["brigade", "is_active"]
    search_fields = ["full_name", "phone"]