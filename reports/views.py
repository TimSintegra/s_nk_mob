from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from openpyxl import Workbook

from accounts.models import Master
from core.models import WorkNode, Worker
from reports.models import DailyReport, ReportWorkItem, ReportWorkerEntry


def parse_decimal(value):
    if not value:
        return Decimal("0")
    return Decimal(value.replace(",", "."))


def short_full_name(full_name):
    parts = full_name.split()
    if len(parts) < 2:
        return full_name

    initials = [f"{part[0]}." for part in parts[1:] if part]
    return " ".join([parts[0], *initials])


def get_current_master(request):
    master_id = request.session.get("master_id")

    if not master_id:
        return None

    return Master.objects.filter(id=master_id, is_active=True).first()


def master_login_required(view_func):
    def wrapper(request, *args, **kwargs):
        master = get_current_master(request)

        if not master:
            return redirect("master_login")

        request.master = master
        return view_func(request, *args, **kwargs)

    return wrapper


def master_login(request):
    if request.method == "POST":
        phone = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "")

        master = Master.objects.filter(phone=phone, is_active=True).first()

        if master and master.check_password(password):
            request.session["master_id"] = master.id
            return redirect("dashboard")

        messages.error(request, "Неверный телефон или пароль.")

    return render(request, "reports/master_login.html")


def master_logout(request):
    request.session.flush()
    return redirect("master_login")


@master_login_required
def dashboard(request):
    master = request.master

    today_reports_count = DailyReport.objects.filter(
        master=master,
        date=date.today(),
    ).count()

    return render(
        request,
        "reports/dashboard.html",
        {
            "master": master,
            "today_reports_count": today_reports_count,
        },
    )


@master_login_required
def work_node_list(request, parent_id=None):
    parent = None

    if parent_id:
        parent = get_object_or_404(WorkNode, id=parent_id, is_active=True)
        nodes = parent.children.filter(is_active=True).order_by("code")
    else:
        nodes = WorkNode.objects.filter(parent__isnull=True, is_active=True).order_by("code")

    return render(
        request,
        "reports/work_node_list.html",
        {
            "parent": parent,
            "nodes": nodes,
        },
    )


@master_login_required
def add_work_item(request, work_node_id):
    master = request.master
    work_node = get_object_or_404(WorkNode, id=work_node_id, is_active=True)

    if work_node.children.exists():
        return redirect("work_node_children", parent_id=work_node.id)

    if request.method == "POST":
        report_date = request.POST.get("date") or date.today()
        site_name = request.POST.get("site_name", "").strip()
        title = request.POST.get("title", "").strip()
        project_section = request.POST.get("project_section", "").strip()
        quantity = request.POST.get("quantity") or "0"
        comment = request.POST.get("comment", "").strip()

        report, _ = DailyReport.objects.get_or_create(
            date=report_date,
            master=master,
            brigade=master.brigade,
            status=DailyReport.STATUS_DRAFT,
        )

        ReportWorkItem.objects.create(
            report=report,
            work_node=work_node,
            site_name=site_name,
            title=title,
            project_section=project_section,
            quantity=Decimal(quantity),
            comment=comment,
        )

        action = request.POST.get("action")

        if action == "finish":
            return redirect("report_summary", report_id=report.id)

        messages.success(request, "Работа добавлена. Выберите следующий вид работ.")
        return redirect("work_node_list")

    return render(
        request,
        "reports/add_work_item.html",
        {
            "work_node": work_node,
            "today": date.today(),
        },
    )


@master_login_required
def report_summary(request, report_id):
    master = request.master

    report = get_object_or_404(
        DailyReport,
        id=report_id,
        master=master,
    )

    workers = Worker.objects.filter(
        brigade=master.brigade,
        is_active=True,
    ).order_by("full_name")

    if request.method == "POST":
        report.worker_entries.all().delete()

        for worker in workers:
            status = request.POST.get(f"worker_{worker.id}_status")
            hours = parse_decimal(request.POST.get(f"worker_{worker.id}_hours"))

            if status or hours:
                ReportWorkerEntry.objects.create(
                    report=report,
                    worker=worker,
                    status=status,
                    hours=Decimal("0") if status else hours,
                )

        temporary_names = request.POST.getlist("temporary_worker_name")
        temporary_statuses = request.POST.getlist("temporary_worker_status")
        temporary_hours = request.POST.getlist("temporary_worker_hours")

        for name, status, hours in zip(temporary_names, temporary_statuses, temporary_hours, strict=False):
            name = name.strip()
            hours = parse_decimal(hours)

            if name and (status or hours):
                ReportWorkerEntry.objects.create(
                    report=report,
                    temporary_worker_name=name,
                    status=status,
                    hours=Decimal("0") if status else hours,
                )

        report.status = DailyReport.STATUS_DONE
        report.save(update_fields=["status", "updated_at"])

        messages.success(request, "Отчёт сохранён.")
        return redirect("report_calendar")

    return render(
        request,
        "reports/report_summary.html",
        {
            "report": report,
            "workers": workers,
            "worker_statuses": ReportWorkerEntry.STATUS_CHOICES,
        },
    )


@master_login_required
def timesheet(request):
    master = request.master
    today = date.today()
    selected_month = request.GET.get("month") or today.strftime("%Y-%m")

    try:
        year, month = [int(part) for part in selected_month.split("-", 1)]
        days_count = monthrange(year, month)[1]
    except (TypeError, ValueError):
        year = today.year
        month = today.month
        selected_month = today.strftime("%Y-%m")
        days_count = monthrange(year, month)[1]

    month_start = date(year, month, 1)
    month_end = date(year, month, days_count)
    days = list(range(1, days_count + 1))

    main_rows = {}
    extra_rows = {}
    assigned_workers = Worker.objects.filter(
        brigade=master.brigade,
        is_active=True,
    ).order_by("full_name")

    for worker in assigned_workers:
        main_rows[("worker", worker.id)] = {
            "name": worker.full_name,
            "short_name": short_full_name(worker.full_name),
            "cells": [""] * days_count,
            "sort_name": worker.full_name.lower(),
        }

    entries = ReportWorkerEntry.objects.filter(
        report__master=master,
        report__date__gte=month_start,
        report__date__lte=month_end,
    ).select_related("report", "worker")

    for entry in entries:
        rows = main_rows

        if entry.worker and entry.worker.brigade_id == master.brigade_id:
            key = ("worker", entry.worker_id)
            if key not in rows:
                rows[key] = {
                    "name": entry.worker.full_name,
                    "short_name": short_full_name(entry.worker.full_name),
                    "cells": [""] * days_count,
                    "sort_name": entry.worker.full_name.lower(),
                }
        elif entry.worker:
            rows = extra_rows
            key = ("worker", entry.worker_id)
            if key not in rows:
                rows[key] = {
                    "name": entry.worker.full_name,
                    "short_name": short_full_name(entry.worker.full_name),
                    "cells": [""] * days_count,
                    "sort_name": entry.worker.full_name.lower(),
                }
        else:
            rows = extra_rows
            name = entry.temporary_worker_name.strip()
            if not name:
                continue
            key = ("temporary", name.lower())
            if key not in rows:
                rows[key] = {
                    "name": name,
                    "short_name": short_full_name(name),
                    "cells": [""] * days_count,
                    "sort_name": name.lower(),
                }

        value = entry.timesheet_value
        if not value:
            continue

        day_index = entry.report.date.day - 1
        current_value = rows[key]["cells"][day_index]
        rows[key]["cells"][day_index] = (
            f"{current_value}, {value}" if current_value and value not in current_value.split(", ") else value
        )

    return render(
        request,
        "reports/timesheet.html",
        {
            "days": days,
            "extra_rows": sorted(extra_rows.values(), key=lambda item: item["sort_name"]),
            "master": master,
            "month_title": month_start.strftime("%m.%Y"),
            "rows": sorted(main_rows.values(), key=lambda item: item["sort_name"]),
            "selected_month": selected_month,
        },
    )


@master_login_required
def report_calendar(request):
    master = request.master
    selected_date = request.GET.get("date") or date.today().isoformat()

    reports = DailyReport.objects.filter(
        master=master,
        date=selected_date,
    ).order_by("-created_at")

    return render(
        request,
        "reports/report_calendar.html",
        {
            "selected_date": selected_date,
            "reports": reports,
        },
    )


@master_login_required
def export_report_excel(request, report_id):
    master = request.master

    report = get_object_or_404(
        DailyReport,
        id=report_id,
        master=master,
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Отчёт"

    ws.append(["Дата", report.date.strftime("%d.%m.%Y")])
    ws.append(["Мастер", master.full_name])
    ws.append(["Телефон", master.phone])
    ws.append(["Бригада", report.brigade.name])
    ws.append([])

    ws.append([
        "Объект",
        "Титул",
        "Раздел проекта",
        "Код работы",
        "Вид работ",
        "Объём",
        "Ед. изм.",
    ])

    for work in report.work_items.all():
        ws.append([
            work.site_name,
            work.title,
            work.project_section,
            work.work_node.code,
            work.work_node.name,
            work.quantity,
            work.work_node.unit,
        ])

    ws.append([])
    ws.append(["Рабочие"])
    ws.append(["ФИО", "Статус", "Часы"])

    for entry in report.worker_entries.all():
        ws.append([
            entry.worker.full_name if entry.worker else entry.temporary_worker_name,
            entry.get_status_display(),
            entry.hours,
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="report-{report.id}.xlsx"'
    wb.save(response)

    return response
