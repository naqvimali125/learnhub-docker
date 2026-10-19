import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connection
from django.db.models import Avg, Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required
from assessments.models import Assignment, QuizAttempt, Submission
from courses.models import Certificate, Course, Enrollment, Lesson, LessonProgress
from courses.services import completion_status

User = get_user_model()


def home(request):
    featured = (
        Course.objects.filter(is_published=True)
        .select_related("category", "instructor")
        .annotate(n_lessons=Count("lessons", distinct=True), n_students=Count("enrollments", distinct=True))
        .order_by("-n_students", "-created_at")[:6]
    )
    stats = {
        "courses": Course.objects.filter(is_published=True).count(),
        "lessons": Lesson.objects.filter(course__is_published=True).count(),
        "learners": User.objects.filter(role="student").count(),
    }
    return render(request, "home.html", {"featured": featured, "stats": stats})


@login_required
def dashboard(request):
    user = request.user
    if user.is_lms_admin:
        return redirect("panel")
    if user.is_instructor:
        return redirect("teach_dashboard")
    return redirect("student_dashboard")


@login_required
def student_dashboard(request):
    if not request.user.is_student:
        return redirect("dashboard")
    enrollments = Enrollment.objects.filter(student=request.user).select_related("course__instructor", "course__category")
    cards = []
    for e in enrollments:
        status = completion_status(request.user, e.course)
        cards.append({
            "enrollment": e,
            "course": e.course,
            "progress": e.progress_percent(),
            "status": status,
            "certificate": getattr(e, "certificate", None) if hasattr(e, "certificate") else None,
        })
    my_courses = [e.course_id for e in enrollments]
    today = timezone.localdate()
    submitted_ids = set(Submission.objects.filter(student=request.user).values_list("assignment_id", flat=True))
    pending = [
        a for a in Assignment.objects.filter(course_id__in=my_courses).select_related("course")
        if a.id not in submitted_ids
    ]
    pending.sort(key=lambda a: (a.due_date is None, a.due_date or today))
    graded = Submission.objects.filter(student=request.user, grade__isnull=False).select_related("assignment__course")[:5]
    attempts = QuizAttempt.objects.filter(student=request.user).select_related("quiz__course")[:5]
    avg = QuizAttempt.objects.filter(student=request.user).aggregate(a=Avg("score"))["a"]
    stats = {
        "enrolled": len(cards),
        "completed": sum(1 for c in cards if c["certificate"]),
        "lessons_done": LessonProgress.objects.filter(student=request.user).count(),
        "avg_quiz": round(avg) if avg is not None else None,
    }
    return render(request, "dashboard/student.html", {
        "cards": cards, "pending": pending[:5], "graded": graded, "attempts": attempts, "stats": stats,
        "certificates": Certificate.objects.filter(enrollment__student=request.user).select_related("enrollment__course"),
    })


# --------------------------------------------------------------------------- admin panel
@admin_required
def panel(request):
    roles = {r["role"]: r["n"] for r in User.objects.values("role").annotate(n=Count("id"))}
    top_courses = (
        Course.objects.annotate(n=Count("enrollments"))
        .select_related("instructor").order_by("-n")[:5]
    )
    top_max = max([c.n for c in top_courses] or [1]) or 1
    context = {
        "totals": {
            "users": User.objects.count(),
            "courses": Course.objects.count(),
            "published": Course.objects.filter(is_published=True).count(),
            "enrollments": Enrollment.objects.count(),
            "certificates": Certificate.objects.count(),
            "attempts": QuizAttempt.objects.count(),
            "submissions": Submission.objects.count(),
        },
        "roles": [
            ("Students", roles.get("student", 0)),
            ("Instructors", roles.get("instructor", 0)),
            ("Admins", roles.get("admin", 0)),
        ],
        "top_courses": [(c, c.n, round(c.n * 100 / top_max)) for c in top_courses],
        "recent_users": User.objects.order_by("-date_joined")[:6],
    }
    return render(request, "dashboard/panel.html", context)


@admin_required
def panel_users(request):
    users = User.objects.all().order_by("-date_joined")
    role = request.GET.get("role", "")
    q = request.GET.get("q", "").strip()
    if role:
        users = users.filter(role=role)
    if q:
        users = users.filter(username__icontains=q) | users.filter(email__icontains=q)
    return render(request, "dashboard/users.html", {
        "users": users[:200], "role": role, "q": q, "roles": User.Role.choices,
    })


@admin_required
@require_POST
def panel_user_update(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if target.pk == request.user.pk:
        messages.error(request, "You cannot change your own role or status.")
        return redirect("panel_users")
    action = request.POST.get("action")
    if action == "role" and request.POST.get("role") in dict(User.Role.choices):
        target.role = request.POST["role"]
        target.save()
        messages.success(request, f"{target.username} is now {target.get_role_display()}.")
    elif action == "toggle_active":
        target.is_active = not target.is_active
        target.save()
        messages.success(request, f"{target.username} {'enabled' if target.is_active else 'disabled'}.")
    return redirect("panel_users")


@admin_required
def panel_courses(request):
    courses = Course.objects.select_related("instructor", "category").annotate(n=Count("enrollments"))
    return render(request, "dashboard/courses.html", {"courses": courses})


@admin_required
@require_POST
def panel_course_toggle(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    course.is_published = not course.is_published
    course.save(update_fields=["is_published"])
    messages.success(request, f"{course.title} is now {'published' if course.is_published else 'hidden'}.")
    return redirect("panel_courses")


@admin_required
def panel_system(request):
    """Shows which database and storage the app is really using, with live tests."""
    db = settings.DATABASES["default"]
    info = {
        "db_engine": "PostgreSQL (Amazon RDS)" if "postgresql" in db["ENGINE"] else "SQLite (local file)",
        "db_host": db.get("HOST") or "local file",
        "db_name": str(db["NAME"]),
        "storage_backend": "Amazon S3" if settings.USE_S3 else "Local disk (/media)",
        "bucket": settings.AWS_STORAGE_BUCKET_NAME if settings.USE_S3 else "not used",
        "region": settings.AWS_S3_REGION_NAME if settings.USE_S3 else "not used",
        "debug": settings.DEBUG,
    }
    db_result = None
    try:
        started = time.perf_counter()
        with connection.cursor() as cursor:
            cursor.execute("SELECT version()" if connection.vendor == "postgresql" else "SELECT sqlite_version()")
            version = cursor.fetchone()[0]
        db_result = {"ok": True, "detail": version, "ms": round((time.perf_counter() - started) * 1000)}
    except Exception as exc:  # shown to the admin on purpose
        db_result = {"ok": False, "detail": str(exc), "ms": 0}

    s3_result = request.session.pop("s3_test", None)
    counts = {
        "lesson_videos": Lesson.objects.exclude(video="").count(),
        "lesson_files": Lesson.objects.exclude(attachment="").count(),
        "submissions": Submission.objects.count(),
        "thumbnails": Course.objects.exclude(thumbnail="").count(),
    }
    return render(request, "dashboard/system.html", {"info": info, "db_result": db_result, "s3_result": s3_result, "counts": counts})


@admin_required
@require_POST
def panel_s3_test(request):
    """Write, read and delete a small file through the configured storage backend."""
    name = f"healthcheck/test-{int(time.time())}.txt"
    payload = f"Lumen storage test at {timezone.now().isoformat()}".encode()
    try:
        saved = default_storage.save(name, ContentFile(payload))
        with default_storage.open(saved, "rb") as fh:
            same = fh.read() == payload
        url = default_storage.url(saved)
        default_storage.delete(saved)
        result = {"ok": same, "detail": f"Wrote, read back and deleted {saved}.", "url": url.split("?")[0]}
    except Exception as exc:
        result = {"ok": False, "detail": f"{type(exc).__name__}: {exc}", "url": ""}
    request.session["s3_test"] = result
    return redirect("panel_system")


def health(request):
    """Used by the Beanstalk load balancer and for quick checks. No login."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return HttpResponse("ok", content_type="text/plain")
    except Exception:
        return HttpResponse("database unavailable", status=503, content_type="text/plain")


def error_404(request, exception):
    return render(request, "404.html", status=404)


def error_500(request):
    return render(request, "500.html", status=500)
