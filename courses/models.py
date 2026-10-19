import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from .validators import validate_document, validate_video


def _unique_slug(model, text, instance_pk=None):
    base = slugify(text)[:60] or "item"
    slug, n = base, 2
    while model.objects.filter(slug=slug).exclude(pk=instance_pk).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(unique=True, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(Category, self.name, self.pk)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Course(models.Model):
    LEVELS = [("beginner", "Beginner"), ("intermediate", "Intermediate"), ("advanced", "Advanced")]

    title = models.CharField(max_length=140)
    slug = models.SlugField(unique=True, blank=True)
    summary = models.CharField(max_length=240, help_text="One or two sentences shown on the course card.")
    description = models.TextField()
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="courses")
    instructor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="courses_taught")
    level = models.CharField(max_length=14, choices=LEVELS, default="beginner")
    thumbnail = models.ImageField(upload_to="thumbnails/", blank=True)
    is_published = models.BooleanField(default=False, help_text="Only published courses are visible to students.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(Course, self.title, self.pk)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("course_detail", args=[self.slug])

    @property
    def cover_class(self):
        return f"cover-{(self.pk or 0) % 6}"

    @property
    def initials(self):
        words = [w for w in self.title.split() if w[0].isalnum()]
        return "".join(w[0] for w in words[:2]).upper()


class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=160)
    order = models.PositiveIntegerField(default=1)
    duration_minutes = models.PositiveIntegerField(default=10)
    content = models.TextField(blank=True, help_text="Lesson text. Blank lines start a new paragraph.")
    video = models.FileField(upload_to="lessons/videos/", blank=True, validators=[validate_video])
    attachment = models.FileField(upload_to="lessons/files/", blank=True, validators=[validate_document],
                                  help_text="Slides, PDF, notes or any handout.")

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.course.title}: {self.title}"


class Enrollment(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("student", "course")
        ordering = ["-enrolled_at"]

    def __str__(self):
        return f"{self.student} in {self.course}"

    def progress_percent(self):
        total = self.course.lessons.count()
        if not total:
            return 0
        done = LessonProgress.objects.filter(student=self.student, lesson__course=self.course).count()
        return round(done * 100 / total)


class LessonProgress(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lesson_progress")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="progress")
    completed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("student", "lesson")


def _certificate_code():
    return uuid.uuid4().hex[:12].upper()


class Certificate(models.Model):
    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name="certificate")
    code = models.CharField(max_length=20, unique=True, default=_certificate_code)
    issued_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.code
