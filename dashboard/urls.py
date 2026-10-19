from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("health/", views.health, name="health"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("my-learning/", views.student_dashboard, name="student_dashboard"),
    path("panel/", views.panel, name="panel"),
    path("panel/users/", views.panel_users, name="panel_users"),
    path("panel/users/<int:user_id>/", views.panel_user_update, name="panel_user_update"),
    path("panel/courses/", views.panel_courses, name="panel_courses"),
    path("panel/courses/<int:course_id>/toggle/", views.panel_course_toggle, name="panel_course_toggle"),
    path("panel/system/", views.panel_system, name="panel_system"),
    path("panel/system/test-storage/", views.panel_s3_test, name="panel_s3_test"),
]
