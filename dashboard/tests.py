"""End to end checks of every module. Run with:  python manage.py test"""
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from assessments.models import Assignment, Choice, Quiz, QuizAttempt, Submission
from courses.models import Certificate, Course, Enrollment, Lesson, LessonProgress

User = get_user_model()
TMP_MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class LumenFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def login(self, username, password):
        self.assertTrue(self.client.login(username=username, password=password))

    # ---------------------------------------------------------------- public + auth
    def test_public_pages_and_health(self):
        for name in ("home", "course_list", "login", "register", "health"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.assertEqual(self.client.get("/courses/does-not-exist/").status_code, 404)

    def test_register_creates_student_and_logs_in(self):
        resp = self.client.post(reverse("register"), {
            "username": "newbie", "first_name": "New", "last_name": "Bie", "email": "n@x.com",
            "role": "student", "password1": "S3cretpass!", "password2": "S3cretpass!",
        })
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)
        self.assertEqual(User.objects.get(username="newbie").role, "student")

    def test_cannot_self_register_as_admin(self):
        resp = self.client.post(reverse("register"), {
            "username": "sneaky", "email": "s@x.com", "role": "admin",
            "password1": "S3cretpass!", "password2": "S3cretpass!",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username="sneaky").exists())

    def test_role_protection(self):
        self.login("sara", "learn123")
        self.assertEqual(self.client.get(reverse("panel")).status_code, 403)
        self.assertEqual(self.client.get(reverse("teach_dashboard")).status_code, 403)

    # ---------------------------------------------------------------- student journey
    def test_full_student_journey_to_certificate(self):
        self.login("ali", "learn123")
        course = Course.objects.get(title="Cloud Basics on AWS")
        self.client.post(reverse("enroll", args=[course.slug]))
        self.assertTrue(Enrollment.objects.filter(student__username="ali", course=course).exists())

        # complete all lessons
        for lesson in course.lessons.all():
            resp = self.client.get(reverse("lesson_view", args=[course.slug, lesson.id]))
            self.assertEqual(resp.status_code, 200)
            self.client.post(reverse("lesson_complete", args=[course.slug, lesson.id]))
        self.assertEqual(LessonProgress.objects.filter(student__username="ali").count(), course.lessons.count())
        self.assertFalse(Certificate.objects.exists())  # quiz still outstanding

        # fail first, then pass
        quiz = course.quizzes.first()
        wrong = {f"q_{q.id}": q.choices.filter(is_correct=False).first().id for q in quiz.questions.all()}
        resp = self.client.post(reverse("quiz_take", args=[quiz.id]), wrong)
        attempt = QuizAttempt.objects.filter(student__username="ali").latest("id")
        self.assertRedirects(resp, reverse("quiz_result", args=[attempt.id]), fetch_redirect_response=False)
        self.assertFalse(attempt.passed)
        right = {f"q_{q.id}": q.choices.get(is_correct=True).id for q in quiz.questions.all()}
        self.client.post(reverse("quiz_take", args=[quiz.id]), right)
        attempt = QuizAttempt.objects.filter(student__username="ali").latest("id")
        self.assertTrue(attempt.passed)
        self.assertEqual(attempt.score, 100)
        self.assertEqual(self.client.get(reverse("quiz_result", args=[attempt.id])).status_code, 200)

        cert = Certificate.objects.get()
        page = self.client.get(reverse("certificate_view", args=[cert.code]))
        self.assertContains(page, "Certificate of completion")
        self.client.logout()  # certificates are publicly verifiable
        self.assertEqual(self.client.get(reverse("certificate_view", args=[cert.code])).status_code, 200)

    def test_lessons_locked_until_enrolled(self):
        self.login("ali", "learn123")
        course = Course.objects.get(title="Python for Beginners")
        lesson = course.lessons.first()
        resp = self.client.get(reverse("lesson_view", args=[course.slug, lesson.id]))
        self.assertRedirects(resp, course.get_absolute_url(), fetch_redirect_response=False)

    def test_student_dashboard_renders(self):
        self.login("sara", "learn123")
        resp = self.client.get(reverse("student_dashboard"))
        self.assertContains(resp, "Python for Beginners")

    # ---------------------------------------------------------------- instructor journey
    def test_instructor_builds_course_with_uploads(self):
        self.login("maya", "teach123")
        resp = self.client.post(reverse("course_create"), {
            "title": "Networking 101", "summary": "How data moves.", "description": "Packets and more.",
            "level": "beginner", "is_published": "on",
        })
        course = Course.objects.get(title="Networking 101")
        self.assertRedirects(resp, reverse("course_manage", args=[course.slug]), fetch_redirect_response=False)

        video = SimpleUploadedFile("intro.mp4", b"\x00\x00\x00\x18ftypmp42" + b"0" * 2048, content_type="video/mp4")
        pdf = SimpleUploadedFile("slides.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        self.client.post(reverse("lesson_create", args=[course.slug]), {
            "title": "What is a packet", "order": 1, "duration_minutes": 9, "content": "Text", "video": video, "attachment": pdf,
        })
        lesson = Lesson.objects.get(title="What is a packet")
        self.assertTrue(lesson.video.name.startswith("lessons/videos/"))
        self.assertTrue(lesson.attachment.name.startswith("lessons/files/"))

        bad = SimpleUploadedFile("evil.exe", b"MZ", content_type="application/octet-stream")
        resp = self.client.post(reverse("lesson_create", args=[course.slug]), {
            "title": "Bad", "order": 2, "duration_minutes": 1, "attachment": bad,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Lesson.objects.filter(title="Bad").exists())

        # quiz builder
        self.client.post(reverse("quiz_create", args=[course.slug]), {"title": "Packet quiz", "pass_mark": 50})
        quiz = Quiz.objects.get(title="Packet quiz")
        resp = self.client.post(reverse("quiz_builder", args=[quiz.id]), {
            "text": "What carries data?", "choice_1": "Packets", "choice_2": "Colours", "correct": "1",
        })
        self.assertEqual(quiz.questions.count(), 1)
        self.assertEqual(Choice.objects.filter(question__quiz=quiz, is_correct=True).count(), 1)
        resp = self.client.post(reverse("quiz_builder", args=[quiz.id]), {
            "text": "Bad", "choice_1": "A", "choice_2": "B", "correct": "4",
        })
        self.assertContains(resp, "must be one of the options")

        # dashboards
        self.assertContains(self.client.get(reverse("teach_dashboard")), "Networking 101")
        self.assertEqual(self.client.get(reverse("course_students", args=[course.slug])).status_code, 200)

    def test_instructor_cannot_edit_someone_elses_course(self):
        self.login("omar", "teach123")
        course = Course.objects.get(title="Python for Beginners")  # maya's
        self.assertEqual(self.client.get(reverse("course_edit", args=[course.slug])).status_code, 403)

    # ---------------------------------------------------------------- assignments
    def test_assignment_submit_and_grade(self):
        course = Course.objects.get(title="Python for Beginners")
        assignment = course.assignments.first()
        self.login("sara", "learn123")  # enrolled in seed
        upload = SimpleUploadedFile("tip.py", b"print('tip')", content_type="text/plain")
        # .py is not in the allowed list: must be refused
        resp = self.client.post(reverse("assignment_detail", args=[assignment.id]), {"file": upload, "note": "hi"})
        self.assertEqual(Submission.objects.count(), 0)
        upload = SimpleUploadedFile("tip.txt", b"print('tip')", content_type="text/plain")
        self.client.post(reverse("assignment_detail", args=[assignment.id]), {"file": upload, "note": "hi"})
        sub = Submission.objects.get()
        self.assertTrue(sub.file.name.startswith("submissions/"))
        self.client.logout()

        self.login("maya", "teach123")
        self.assertContains(self.client.get(reverse("submissions_list", args=[assignment.id])), "Sara Khan")
        self.client.post(reverse("submission_grade", args=[sub.id]), {f"s{sub.id}-grade": "88", f"s{sub.id}-feedback": "Nice"})
        sub.refresh_from_db()
        self.assertEqual(sub.grade, 88)
        self.client.post(reverse("submission_grade", args=[sub.id]), {f"s{sub.id}-grade": "999"})
        sub.refresh_from_db()
        self.assertEqual(sub.grade, 88)  # over the maximum: rejected
        self.client.logout()

        self.login("sara", "learn123")
        self.assertContains(self.client.get(reverse("assignment_detail", args=[assignment.id])), "88 / 100")

    # ---------------------------------------------------------------- admin panel
    def test_admin_panel_and_role_change(self):
        self.login("admin", "admin123")
        for name in ("panel", "panel_users", "panel_courses", "panel_system"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        ali = User.objects.get(username="ali")
        self.client.post(reverse("panel_user_update", args=[ali.id]), {"action": "role", "role": "instructor"})
        ali.refresh_from_db()
        self.assertEqual(ali.role, "instructor")
        self.client.post(reverse("panel_user_update", args=[ali.id]), {"action": "toggle_active"})
        ali.refresh_from_db()
        self.assertFalse(ali.is_active)

    def test_storage_self_test(self):
        self.login("admin", "admin123")
        self.client.post(reverse("panel_s3_test"))
        resp = self.client.get(reverse("panel_system"))
        self.assertContains(resp, "Storage works")
        self.assertContains(resp, "Connected")

    def test_unpublished_course_hidden(self):
        course = Course.objects.get(title="Cloud Basics on AWS")
        course.is_published = False
        course.save()
        self.assertEqual(self.client.get(course.get_absolute_url()).status_code, 404)
        self.login("maya", "teach123")
        self.assertEqual(self.client.get(course.get_absolute_url()).status_code, 200)
