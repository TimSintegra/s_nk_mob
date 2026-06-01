from django.contrib import admin

from .models import Brigade, WorkNode, Worker


@admin.register(Brigade)
class BrigadeAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ["full_name", "brigade", "is_active"]
    list_filter = ["brigade", "is_active"]
    search_fields = ["full_name", "phone"]


@admin.register(WorkNode)
class WorkNodeAdmin(admin.ModelAdmin):
    list_display = ["code", "source_key", "name", "parent", "unit", "is_active"]
    list_filter = ["is_active", "parent"]
    search_fields = ["code", "source_key", "name"]
