from django.contrib import admin

from .models import DailyReport, ReportWorkItem, ReportWorkerEntry


class ReportWorkItemInline(admin.TabularInline):
    model = ReportWorkItem
    extra = 0


class ReportWorkerEntryInline(admin.TabularInline):
    model = ReportWorkerEntry
    extra = 0


@admin.register(DailyReport)
class DailyReportAdmin(admin.ModelAdmin):
    list_display = ["date", "master", "brigade", "status", "created_at"]
    list_filter = ["date", "status", "brigade"]
    search_fields = ["master__username"]
    inlines = [ReportWorkItemInline, ReportWorkerEntryInline]


@admin.register(ReportWorkItem)
class ReportWorkItemAdmin(admin.ModelAdmin):
    list_display = ["report", "site_name", "work_node", "quantity"]


@admin.register(ReportWorkerEntry)
class ReportWorkerEntryAdmin(admin.ModelAdmin):
    list_display = ["report", "worker", "temporary_worker_name", "status", "hours"]