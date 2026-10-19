from django import forms

from .models import Assignment, Quiz, Submission


class QuizForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields = ("title", "description", "pass_mark")

    def clean_pass_mark(self):
        value = self.cleaned_data["pass_mark"]
        if not 1 <= value <= 100:
            raise forms.ValidationError("Pass mark must be between 1 and 100.")
        return value


class QuestionForm(forms.Form):
    """One question with up to four answer options. Options 1 and 2 are required."""

    text = forms.CharField(label="Question", widget=forms.Textarea(attrs={"rows": 2}))
    choice_1 = forms.CharField(label="Option 1", max_length=300)
    choice_2 = forms.CharField(label="Option 2", max_length=300)
    choice_3 = forms.CharField(label="Option 3 (optional)", max_length=300, required=False)
    choice_4 = forms.CharField(label="Option 4 (optional)", max_length=300, required=False)
    correct = forms.ChoiceField(
        label="Correct answer",
        choices=[("1", "Option 1"), ("2", "Option 2"), ("3", "Option 3"), ("4", "Option 4")],
        initial="1",
    )

    def clean(self):
        data = super().clean()
        correct = data.get("correct")
        if correct and not (data.get(f"choice_{correct}") or "").strip():
            self.add_error("correct", "The correct answer must be one of the options you filled in.")
        return data

    def options(self):
        """List of (text, is_correct) for every filled option."""
        out = []
        for n in range(1, 5):
            text = (self.cleaned_data.get(f"choice_{n}") or "").strip()
            if text:
                out.append((text, str(n) == self.cleaned_data["correct"]))
        return out


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ("title", "description", "due_date", "max_points")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }


class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ("file", "note")
        widgets = {"note": forms.Textarea(attrs={"rows": 3})}
        labels = {"file": "Your file", "note": "Note to your instructor (optional)"}


class GradeForm(forms.Form):
    grade = forms.IntegerField(min_value=0)
    feedback = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, max_points=100, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_points = max_points
        self.fields["grade"].label = f"Grade out of {max_points}"

    def clean_grade(self):
        grade = self.cleaned_data["grade"]
        if grade > self.max_points:
            raise forms.ValidationError(f"Grade cannot be higher than {self.max_points}.")
        return grade
