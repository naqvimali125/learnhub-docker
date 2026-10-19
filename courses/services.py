from django.utils import timezone

from .models import Certificate, Enrollment, LessonProgress


def completion_status(student, course):
    """Return what a student has finished and what is still needed for the certificate."""
    from assessments.models import QuizAttempt

    lessons_total = course.lessons.count()
    lessons_done = LessonProgress.objects.filter(student=student, lesson__course=course).count()
    quiz_ids = list(course.quizzes.values_list("id", flat=True))
    passed_ids = set(
        QuizAttempt.objects.filter(student=student, quiz_id__in=quiz_ids, passed=True).values_list("quiz_id", flat=True)
    )
    eligible = lessons_total > 0 and lessons_done >= lessons_total and len(passed_ids) >= len(quiz_ids)
    return {
        "lessons_total": lessons_total,
        "lessons_done": lessons_done,
        "quizzes_total": len(quiz_ids),
        "quizzes_passed": len(passed_ids),
        "eligible": eligible,
    }


def evaluate_completion(student, course):
    """Issue a certificate when every lesson is done and every quiz is passed.

    Returns the new Certificate if one was just issued, otherwise None.
    """
    enrollment = Enrollment.objects.filter(student=student, course=course).first()
    if not enrollment or hasattr(enrollment, "certificate"):
        return None
    if not completion_status(student, course)["eligible"]:
        return None
    enrollment.completed_at = timezone.now()
    enrollment.save(update_fields=["completed_at"])
    return Certificate.objects.create(enrollment=enrollment)
