from django.contrib import admin

from .models import Category, Certificate, Course, Enrollment, Lesson, LessonProgress


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0
    fields = ("order", "title", "duration_minutes")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "instructor", "category", "level", "is_published", "created_at")
    list_filter = ("is_published", "level", "category")
    search_fields = ("title", "summary")
    inlines = [LessonInline]


admin.site.register(Category)
admin.site.register(Enrollment)
admin.site.register(LessonProgress)
admin.site.register(Certificate)
