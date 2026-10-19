from django.urls import path

from . import manage_views, views

urlpatterns = [
    path("courses/", views.course_list, name="course_list"),
    path("courses/<slug:slug>/", views.course_detail, name="course_detail"),
    path("courses/<slug:slug>/enroll/", views.enroll, name="enroll"),
    path("courses/<slug:slug>/leave/", views.unenroll, name="unenroll"),
    path("courses/<slug:slug>/learn/", views.course_learn, name="course_learn"),
    path("courses/<slug:slug>/lessons/<int:lesson_id>/", views.lesson_view, name="lesson_view"),
    path("courses/<slug:slug>/lessons/<int:lesson_id>/complete/", views.lesson_complete, name="lesson_complete"),
    path("courses/<slug:slug>/lessons/<int:lesson_id>/undo/", views.lesson_incomplete, name="lesson_incomplete"),
    path("certificates/<str:code>/", views.certificate_view, name="certificate_view"),

    # Instructor area
    path("teach/", manage_views.teach_dashboard, name="teach_dashboard"),
    path("teach/new/", manage_views.course_create, name="course_create"),
    path("teach/<slug:slug>/", manage_views.course_manage, name="course_manage"),
    path("teach/<slug:slug>/edit/", manage_views.course_edit, name="course_edit"),
    path("teach/<slug:slug>/delete/", manage_views.course_delete, name="course_delete"),
    path("teach/<slug:slug>/students/", manage_views.course_students, name="course_students"),
    path("teach/<slug:slug>/lessons/new/", manage_views.lesson_create, name="lesson_create"),
    path("teach/<slug:slug>/lessons/<int:lesson_id>/edit/", manage_views.lesson_edit, name="lesson_edit"),
    path("teach/<slug:slug>/lessons/<int:lesson_id>/delete/", manage_views.lesson_delete, name="lesson_delete"),
]
