from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.master_login, name="master_login"),
    path("logout/", views.master_logout, name="master_logout"),

    path("", views.dashboard, name="dashboard"),
    path("work/", views.work_node_list, name="work_node_list"),
    path("work/<int:parent_id>/", views.work_node_list, name="work_node_children"),
    path("work/<int:work_node_id>/add/", views.add_work_item, name="add_work_item"),
    path("timesheet/", views.timesheet, name="timesheet"),
    path("report/<int:report_id>/summary/", views.report_summary, name="report_summary"),
    path("reports/", views.report_calendar, name="report_calendar"),
    path("reports/<int:report_id>/excel/", views.export_report_excel, name="export_report_excel"),
    path("workers/search/", views.search_workers, name="search_workers"),
    path("work-item/<int:work_item_id>/delete/", views.delete_work_item, name="delete_work_item"),
]
