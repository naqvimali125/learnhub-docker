from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, Max
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import teacher_required
from courses.models import Enrollment
from courses.permissions import can_manage_course
from courses.services import evaluate_completion

from .forms import AssignmentForm, GradeForm, QuestionForm, QuizForm, SubmissionForm
from .models import Assignment, Choice, Question, Quiz, QuizAttempt, Submission


def _teacher_quiz(request, quiz_id):
    quiz = get_object_or_404(Quiz.objects.select_related("course"), pk=quiz_id)
    if not can_manage_course(request.user, quiz.course):
        raise PermissionDenied
    return quiz


def _teacher_assignment(request, assignment_id):
    assignment = get_object_or_404(Assignment.objects.select_related("course"), pk=assignment_id)
    if not can_manage_course(request.user, assignment.course):
        raise PermissionDenied
    return assignment


def _require_enrolled(request, course):
    if request.user.is_student and not Enrollment.objects.filter(student=request.user, course=course).exists():
        messages.info(request, "Enroll in the course to open this.")
        return redirect(course)
    if not request.user.is_student and not can_manage_course(request.user, course):
        raise PermissionDenied
    return None


# ---------------------------------------------------------------- quiz: teacher side
@teacher_required
def quiz_create(request, slug):
    from courses.models import Course
    course = get_object_or_404(Course, slug=slug)
    if not can_manage_course(request.user, course):
        raise PermissionDenied
    form = QuizForm(request.POST or None, initial={"pass_mark": 60})
    if request.method == "POST" and form.is_valid():
        quiz = form.save(commit=False)
        quiz.course = course
        quiz.save()
        messages.success(request, "Quiz created. Now add its questions.")
        return redirect("quiz_builder", quiz_id=quiz.id)
    return render(request, "assessments/quiz_form.html", {"form": form, "course": course, "title": "New quiz"})


@teacher_required
def quiz_builder(request, quiz_id):
    quiz = _teacher_quiz(request, quiz_id)
    form = QuestionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        question = Question.objects.create(
            quiz=quiz, text=form.cleaned_data["text"], order=quiz.questions.count() + 1
        )
        Choice.objects.bulk_create(
            [Choice(question=question, text=text, is_correct=ok) for text, ok in form.options()]
        )
        messages.success(request, "Question added.")
        return redirect("quiz_builder", quiz_id=quiz.id)
    stats = quiz.attempts.aggregate(n=Count("id"), avg=Avg("score"))
    context = {
        "quiz": quiz,
        "course": quiz.course,
        "questions": quiz.questions.prefetch_related("choices"),
        "form": form,
        "attempt_count": stats["n"],
        "avg_score": round(stats["avg"]) if stats["avg"] is not None else None,
    }
    return render(request, "assessments/quiz_builder.html", context)


@teacher_required
def question_delete(request, quiz_id, question_id):
    quiz = _teacher_quiz(request, quiz_id)
    if request.method == "POST":
        get_object_or_404(Question, pk=question_id, quiz=quiz).delete()
        messages.success(request, "Question deleted.")
    return redirect("quiz_builder", quiz_id=quiz.id)


@teacher_required
def quiz_delete(request, quiz_id):
    quiz = _teacher_quiz(request, quiz_id)
    course = quiz.course
    if request.method == "POST":
        quiz.delete()
        messages.success(request, "Quiz deleted.")
        return redirect("course_manage", slug=course.slug)
    return render(request, "partials/confirm_delete.html", {
        "object_name": quiz.title, "kind": "quiz",
        "warning": "All student attempts for this quiz will be deleted too.",
        "cancel_url": course.get_absolute_url(),
    })


# ---------------------------------------------------------------- quiz: student side
@login_required
def quiz_take(request, quiz_id):
    quiz = get_object_or_404(Quiz.objects.select_related("course"), pk=quiz_id)
    blocked = _require_enrolled(request, quiz.course)
    if blocked:
        return blocked
    questions = list(quiz.questions.prefetch_related("choices"))
    if not questions:
        messages.info(request, "This quiz has no questions yet.")
        return redirect(quiz.course)

    if request.method == "POST":
        if not request.user.is_student:
            messages.info(request, "Preview only: instructor attempts are not recorded.")
            return redirect("quiz_take", quiz_id=quiz.id)
        answers, correct = {}, 0
        for q in questions:
            raw = request.POST.get(f"q_{q.id}")
            if raw and raw.isdigit():
                answers[str(q.id)] = int(raw)
            chosen = next((c for c in q.choices.all() if str(c.id) == raw), None)
            if chosen and chosen.is_correct:
                correct += 1
        score = round(correct * 100 / len(questions))
        attempt = QuizAttempt.objects.create(
            quiz=quiz, student=request.user, score=score, correct_count=correct,
            total=len(questions), passed=score >= quiz.pass_mark, answers=answers,
        )
        certificate = evaluate_completion(request.user, quiz.course)
        if certificate:
            messages.success(request, "Course complete. Your certificate is ready.")
        return redirect("quiz_result", attempt_id=attempt.id)

    attempts = []
    best = None
    if request.user.is_student:
        attempts = list(quiz.attempts.filter(student=request.user)[:5])
        best = quiz.attempts.filter(student=request.user).aggregate(b=Max("score"))["b"]
    return render(request, "assessments/quiz_take.html", {
        "quiz": quiz, "course": quiz.course, "questions": questions, "attempts": attempts, "best": best,
    })


@login_required
def quiz_result(request, attempt_id):
    attempt = get_object_or_404(QuizAttempt.objects.select_related("quiz__course"), pk=attempt_id)
    if attempt.student_id != request.user.id and not can_manage_course(request.user, attempt.quiz.course):
        raise PermissionDenied
    review = []
    for q in attempt.quiz.questions.prefetch_related("choices"):
        picked = attempt.answers.get(str(q.id))
        choices = [{"text": c.text, "correct": c.is_correct, "picked": c.id == picked} for c in q.choices.all()]
        review.append({
            "question": q,
            "choices": choices,
            "right": any(c["correct"] and c["picked"] for c in choices),
            "skipped": picked is None,
        })
    return render(request, "assessments/quiz_result.html", {
        "attempt": attempt, "quiz": attempt.quiz, "course": attempt.quiz.course, "review": review,
    })


# ---------------------------------------------------------------- assignments: teacher side
@teacher_required
def assignment_create(request, slug):
    from courses.models import Course
    course = get_object_or_404(Course, slug=slug)
    if not can_manage_course(request.user, course):
        raise PermissionDenied
    form = AssignmentForm(request.POST or None, initial={"max_points": 100})
    if request.method == "POST" and form.is_valid():
        assignment = form.save(commit=False)
        assignment.course = course
        assignment.save()
        messages.success(request, "Assignment created.")
        return redirect("course_manage", slug=course.slug)
    return render(request, "assessments/assignment_form.html", {"form": form, "course": course, "title": "New assignment"})


@teacher_required
def assignment_edit(request, assignment_id):
    assignment = _teacher_assignment(request, assignment_id)
    form = AssignmentForm(request.POST or None, instance=assignment)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Assignment saved.")
        return redirect("course_manage", slug=assignment.course.slug)
    return render(request, "assessments/assignment_form.html", {
        "form": form, "course": assignment.course, "title": "Edit assignment",
    })


@teacher_required
def assignment_delete(request, assignment_id):
    assignment = _teacher_assignment(request, assignment_id)
    course = assignment.course
    if request.method == "POST":
        assignment.delete()
        messages.success(request, "Assignment deleted.")
        return redirect("course_manage", slug=course.slug)
    return render(request, "partials/confirm_delete.html", {
        "object_name": assignment.title, "kind": "assignment",
        "warning": "All submissions for this assignment will be deleted too.",
        "cancel_url": course.get_absolute_url(),
    })


@teacher_required
def submissions_list(request, assignment_id):
    assignment = _teacher_assignment(request, assignment_id)
    submissions = assignment.submissions.select_related("student")
    rows = [{"submission": s, "form": GradeForm(
        initial={"grade": s.grade, "feedback": s.feedback}, max_points=assignment.max_points, prefix=f"s{s.id}"
    )} for s in submissions]
    return render(request, "assessments/submissions.html", {
        "assignment": assignment, "course": assignment.course, "rows": rows,
        "waiting": sum(1 for s in submissions if s.grade is None),
    })


@teacher_required
def submission_grade(request, submission_id):
    submission = get_object_or_404(Submission.objects.select_related("assignment__course"), pk=submission_id)
    assignment = submission.assignment
    if not can_manage_course(request.user, assignment.course):
        raise PermissionDenied
    if request.method == "POST":
        form = GradeForm(request.POST, max_points=assignment.max_points, prefix=f"s{submission.id}")
        if form.is_valid():
            submission.grade = form.cleaned_data["grade"]
            submission.feedback = form.cleaned_data["feedback"]
            submission.graded_at = timezone.now()
            submission.save(update_fields=["grade", "feedback", "graded_at"])
            messages.success(request, f"Saved grade for {submission.student.display_name}.")
        else:
            messages.error(request, "; ".join(e for errs in form.errors.values() for e in errs))
    return redirect("submissions_list", assignment_id=assignment.id)


# ---------------------------------------------------------------- assignments: student side
@login_required
def assignment_detail(request, assignment_id):
    assignment = get_object_or_404(Assignment.objects.select_related("course"), pk=assignment_id)
    blocked = _require_enrolled(request, assignment.course)
    if blocked:
        return blocked
    submission = None
    form = None
    if request.user.is_student:
        submission = Submission.objects.filter(assignment=assignment, student=request.user).first()
        locked = submission is not None and submission.grade is not None
        if not locked:
            form = SubmissionForm(request.POST or None, request.FILES or None, instance=submission)
            if request.method == "POST" and form.is_valid():
                sub = form.save(commit=False)
                sub.assignment = assignment
                sub.student = request.user
                sub.submitted_at = timezone.now()
                sub.save()
                messages.success(request, "Submission uploaded.")
                return redirect("assignment_detail", assignment_id=assignment.id)
    return render(request, "assessments/assignment_detail.html", {
        "assignment": assignment, "course": assignment.course, "submission": submission, "form": form,
    })
