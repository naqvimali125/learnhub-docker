from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Category, Certificate, Course, Enrollment, Lesson, LessonProgress
from .permissions import can_manage_course, can_view_content
from .services import completion_status, evaluate_completion


def course_list(request):
    courses = (
        Course.objects.filter(is_published=True)
        .select_related("category", "instructor")
        .annotate(n_lessons=Count("lessons", distinct=True), n_students=Count("enrollments", distinct=True))
    )
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "")
    level = request.GET.get("level", "")
    if q:
        courses = courses.filter(Q(title__icontains=q) | Q(summary__icontains=q) | Q(description__icontains=q))
    if category:
        courses = courses.filter(category__slug=category)
    if level:
        courses = courses.filter(level=level)
    context = {
        "courses": courses,
        "categories": Category.objects.all(),
        "levels": Course.LEVELS,
        "q": q,
        "selected_category": category,
        "selected_level": level,
    }
    return render(request, "courses/list.html", context)


def course_detail(request, slug):
    course = get_object_or_404(Course.objects.select_related("category", "instructor"), slug=slug)
    manager = can_manage_course(request.user, course)
    if not course.is_published and not manager:
        raise Http404
    enrollment = None
    if request.user.is_authenticated:
        enrollment = Enrollment.objects.filter(student=request.user, course=course).first()
    done_ids = set()
    if enrollment:
        done_ids = set(
            LessonProgress.objects.filter(student=request.user, lesson__course=course).values_list("lesson_id", flat=True)
        )
    context = {
        "course": course,
        "lessons": course.lessons.all(),
        "quizzes": course.quizzes.annotate(n_questions=Count("questions")),
        "assignments": course.assignments.all(),
        "enrollment": enrollment,
        "done_ids": done_ids,
        "manager": manager,
        "n_students": course.enrollments.count(),
        "total_minutes": sum(l.duration_minutes for l in course.lessons.all()),
    }
    if enrollment:
        context["status"] = completion_status(request.user, course)
        context["progress"] = enrollment.progress_percent()
    return render(request, "courses/detail.html", context)


@login_required
@require_POST
def enroll(request, slug):
    course = get_object_or_404(Course, slug=slug, is_published=True)
    if not request.user.is_student:
        messages.info(request, "Only student accounts can enroll. Instructors can preview their own courses.")
        return redirect(course)
    _, created = Enrollment.objects.get_or_create(student=request.user, course=course)
    if created:
        messages.success(request, f"You are enrolled in {course.title}.")
    return redirect("course_learn", slug=course.slug)


@login_required
@require_POST
def unenroll(request, slug):
    course = get_object_or_404(Course, slug=slug)
    Enrollment.objects.filter(student=request.user, course=course).delete()
    messages.info(request, f"You left {course.title}.")
    return redirect("course_list")


@login_required
def course_learn(request, slug):
    """Send the learner to the first lesson they have not finished."""
    course = get_object_or_404(Course, slug=slug)
    if not can_view_content(request.user, course):
        messages.info(request, "Enroll in the course to start learning.")
        return redirect(course)
    lessons = list(course.lessons.all())
    if not lessons:
        messages.info(request, "This course has no lessons yet.")
        return redirect(course)
    done = set(LessonProgress.objects.filter(student=request.user, lesson__course=course).values_list("lesson_id", flat=True))
    target = next((l for l in lessons if l.id not in done), lessons[0])
    return redirect("lesson_view", slug=course.slug, lesson_id=target.id)


@login_required
def lesson_view(request, slug, lesson_id):
    course = get_object_or_404(Course, slug=slug)
    if not can_view_content(request.user, course):
        messages.info(request, "Enroll in the course to open its lessons.")
        return redirect(course)
    lessons = list(course.lessons.all())
    lesson = get_object_or_404(Lesson, pk=lesson_id, course=course)
    done_ids = set(
        LessonProgress.objects.filter(student=request.user, lesson__course=course).values_list("lesson_id", flat=True)
    )
    index = lessons.index(lesson)
    enrolled = Enrollment.objects.filter(student=request.user, course=course).exists()
    context = {
        "course": course,
        "lesson": lesson,
        "lessons": lessons,
        "done_ids": done_ids,
        "is_done": lesson.id in done_ids,
        "prev_lesson": lessons[index - 1] if index > 0 else None,
        "next_lesson": lessons[index + 1] if index < len(lessons) - 1 else None,
        "enrolled": enrolled,
        "progress": round(len(done_ids) * 100 / len(lessons)) if lessons else 0,
    }
    return render(request, "courses/lesson.html", context)


@login_required
@require_POST
def lesson_complete(request, slug, lesson_id):
    course = get_object_or_404(Course, slug=slug)
    lesson = get_object_or_404(Lesson, pk=lesson_id, course=course)
    if not Enrollment.objects.filter(student=request.user, course=course).exists():
        messages.info(request, "Only enrolled students can track progress.")
        return redirect("lesson_view", slug=slug, lesson_id=lesson.id)
    LessonProgress.objects.get_or_create(student=request.user, lesson=lesson)
    certificate = evaluate_completion(request.user, course)
    if certificate:
        messages.success(request, "Course complete. Your certificate is ready.")
        return redirect("certificate_view", code=certificate.code)
    lessons = list(course.lessons.all())
    index = lessons.index(lesson)
    if index < len(lessons) - 1:
        messages.success(request, "Lesson marked as complete.")
        return redirect("lesson_view", slug=slug, lesson_id=lessons[index + 1].id)
    messages.success(request, "That was the last lesson. Check the course page for anything still required.")
    return redirect(course)


@login_required
@require_POST
def lesson_incomplete(request, slug, lesson_id):
    course = get_object_or_404(Course, slug=slug)
    LessonProgress.objects.filter(student=request.user, lesson_id=lesson_id, lesson__course=course).delete()
    return redirect("lesson_view", slug=slug, lesson_id=lesson_id)


def certificate_view(request, code):
    """Public page so anyone can verify a certificate code. Also prints nicely."""
    certificate = get_object_or_404(
        Certificate.objects.select_related("enrollment__student", "enrollment__course__instructor"), code=code
    )
    return render(request, "courses/certificate.html", {"certificate": certificate})
