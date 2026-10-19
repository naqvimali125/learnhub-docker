from django import forms

from .models import Course, Lesson


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ("title", "summary", "description", "category", "level", "thumbnail", "is_published")
        widgets = {"description": forms.Textarea(attrs={"rows": 7})}


class LessonForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = ("title", "order", "duration_minutes", "content", "video", "attachment")
        widgets = {"content": forms.Textarea(attrs={"rows": 10})}
