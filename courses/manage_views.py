from django.contrib import messages
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.core.exceptions import PermissionDenied

from accounts.decorators import teacher_required
from assessments.models import QuizAttempt, Submission

from .forms import CourseForm, LessonForm
from .models import Course, Enrollment, Lesson, LessonProgress
from .permissions import can_manage_course


def _own_course(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not can_manage_course(request.user, course):
        raise PermissionDenied
    return course


@teacher_required
def teach_dashboard(request):
    courses = Course.objects.all() if request.user.is_lms_admin else Course.objects.filter(instructor=request.user)
    courses = courses.select_related("category").annotate(
        n_students=Count("enrollments", distinct=True), n_lessons=Count("lessons", distinct=True)
    )
    to_grade = Submission.objects.filter(
        assignment__course__in=courses, grade__isnull=True
    ).count()
    context = {
        "courses": courses,
        "total_students": Enrollment.objects.filter(course__in=courses).values("student").distinct().count(),
        "to_grade": to_grade,
        "published": sum(1 for c in courses if c.is_published),
    }
    return render(request, "courses/teach_dashboard.html", context)


@teacher_required
def course_create(request):
    form = CourseForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        course = form.save(commit=False)
        course.instructor = request.user
        course.save()
        messages.success(request, "Course created. Add your first lesson.")
        return redirect("course_manage", slug=course.slug)
    return render(request, "courses/course_form.html", {"form": form, "title": "New course"})


@teacher_required
def course_edit(request, slug):
    course = _own_course(request, slug)
    form = CourseForm(request.POST or None, request.FILES or None, instance=course)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Course saved.")
        return redirect("course_manage", slug=course.slug)
    return render(request, "courses/course_form.html", {"form": form, "title": "Edit course", "course": course})


@teacher_required
def course_delete(request, slug):
    course = _own_course(request, slug)
    if request.method == "POST":
        course.delete()
        messages.success(request, "Course deleted.")
        return redirect("teach_dashboard")
    return render(request, "partials/confirm_delete.html", {
        "object_name": course.title, "kind": "course",
        "warning": "Its lessons, quizzes, assignments and enrollments will be deleted too.",
        "cancel_url": course.get_absolute_url(),
    })


@teacher_required
def course_manage(request, slug):
    course = _own_course(request, slug)
    context = {
        "course": course,
        "lessons": course.lessons.all(),
        "quizzes": course.quizzes.annotate(n_questions=Count("questions")),
        "assignments": course.assignments.annotate(n_submissions=Count("submissions")),
        "n_students": course.enrollments.count(),
    }
    return render(request, "courses/course_manage.html", context)


@teacher_required
def lesson_create(request, slug):
    course = _own_course(request, slug)
    next_order = (course.lessons.count() or 0) + 1
    form = LessonForm(request.POST or None, request.FILES or None, initial={"order": next_order})
    if request.method == "POST" and form.is_valid():
        lesson = form.save(commit=False)
        lesson.course = course
        lesson.save()
        messages.success(request, "Lesson added.")
        return redirect("course_manage", slug=course.slug)
    return render(request, "courses/lesson_form.html", {"form": form, "course": course, "title": "New lesson"})


@teacher_required
def lesson_edit(request, slug, lesson_id):
    course = _own_course(request, slug)
    lesson = get_object_or_404(Lesson, pk=lesson_id, course=course)
    form = LessonForm(request.POST or None, request.FILES or None, instance=lesson)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Lesson saved.")
        return redirect("course_manage", slug=course.slug)
    return render(request, "courses/lesson_form.html", {"form": form, "course": course, "title": "Edit lesson", "lesson": lesson})


@teacher_required
def lesson_delete(request, slug, lesson_id):
    course = _own_course(request, slug)
    lesson = get_object_or_404(Lesson, pk=lesson_id, course=course)
    if request.method == "POST":
        lesson.delete()
        messages.success(request, "Lesson deleted.")
        return redirect("course_manage", slug=course.slug)
    return render(request, "partials/confirm_delete.html", {
        "object_name": lesson.title, "kind": "lesson",
        "warning": "Student progress on this lesson will be removed.",
        "cancel_url": course.get_absolute_url(),
    })


@teacher_required
def course_students(request, slug):
    course = _own_course(request, slug)
    lessons_total = course.lessons.count()
    quiz_total = course.quizzes.count()
    rows = []
    for enrollment in course.enrollments.select_related("student"):
        student = enrollment.student
        done = LessonProgress.objects.filter(student=student, lesson__course=course).count()
        attempts = QuizAttempt.objects.filter(student=student, quiz__course=course)
        passed = attempts.filter(passed=True).values("quiz").distinct().count()
        avg = attempts.aggregate(a=Avg("score"))["a"]
        submitted = Submission.objects.filter(student=student, assignment__course=course).count()
        graded = Submission.objects.filter(student=student, assignment__course=course, grade__isnull=False)
        rows.append({
            "enrollment": enrollment,
            "student": student,
            "progress": round(done * 100 / lessons_total) if lessons_total else 0,
            "quizzes_passed": passed,
            "avg_score": round(avg) if avg is not None else None,
            "submitted": submitted,
            "graded": graded.count(),
            "certified": hasattr(enrollment, "certificate"),
        })
    stats = {
        "students": len(rows),
        "avg_progress": round(sum(r["progress"] for r in rows) / len(rows)) if rows else 0,
        "certified": sum(1 for r in rows if r["certified"]),
        "quiz_total": quiz_total,
    }
    return render(request, "courses/course_students.html", {"course": course, "rows": rows, "stats": stats})
