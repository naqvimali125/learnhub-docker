from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class RegisterForm(UserCreationForm):
    ROLE_CHOICES = [("student", "Student: I want to learn"), ("instructor", "Instructor: I want to teach")]

    role = forms.ChoiceField(choices=ROLE_CHOICES, initial="student")

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "role")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = self.cleaned_data["role"]
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "bio", "avatar")
        widgets = {"bio": forms.Textarea(attrs={"rows": 4})}
