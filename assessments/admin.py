from django.contrib import admin

from .models import Assignment, Choice, Question, Quiz, QuizAttempt, Submission


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 0


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "quiz", "order")
    inlines = [ChoiceInline]


admin.site.register(Quiz)
admin.site.register(QuizAttempt)
admin.site.register(Assignment)
admin.site.register(Submission)
