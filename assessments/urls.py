from django.urls import path

from . import views

urlpatterns = [
    # quizzes: instructor
    path("teach/<slug:slug>/quizzes/new/", views.quiz_create, name="quiz_create"),
    path("teach/quizzes/<int:quiz_id>/", views.quiz_builder, name="quiz_builder"),
    path("teach/quizzes/<int:quiz_id>/delete/", views.quiz_delete, name="quiz_delete"),
    path("teach/quizzes/<int:quiz_id>/questions/<int:question_id>/delete/", views.question_delete, name="question_delete"),
    # quizzes: student
    path("quizzes/<int:quiz_id>/", views.quiz_take, name="quiz_take"),
    path("quizzes/result/<int:attempt_id>/", views.quiz_result, name="quiz_result"),
    # assignments: instructor
    path("teach/<slug:slug>/assignments/new/", views.assignment_create, name="assignment_create"),
    path("teach/assignments/<int:assignment_id>/edit/", views.assignment_edit, name="assignment_edit"),
    path("teach/assignments/<int:assignment_id>/delete/", views.assignment_delete, name="assignment_delete"),
    path("teach/assignments/<int:assignment_id>/submissions/", views.submissions_list, name="submissions_list"),
    path("teach/submissions/<int:submission_id>/grade/", views.submission_grade, name="submission_grade"),
    # assignments: student
    path("assignments/<int:assignment_id>/", views.assignment_detail, name="assignment_detail"),
]
