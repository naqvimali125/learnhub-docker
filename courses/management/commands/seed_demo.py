"""Create demo accounts, three courses with lessons, quizzes and assignments.

    python manage.py seed_demo

Safe to run more than once: it skips data that already exists.
Each lesson gets a small notes file, so with USE_S3=True you will see real
objects appear in your bucket straight away.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from assessments.models import Assignment, Choice, Question, Quiz
from courses.models import Category, Course, Enrollment, Lesson, LessonProgress

User = get_user_model()

COURSES = [
    {
        "title": "Python for Beginners",
        "category": "Programming",
        "level": "beginner",
        "summary": "Write your first programs and learn the ideas every developer uses daily.",
        "description": "A gentle, practical start. You will learn variables, control flow, functions and "
                       "collections by building small programs after every lesson.",
        "lessons": [
            ("Setting up and running Python", 8, "Install Python, open a terminal and run your first script.\n\nWe print a greeting and read a name from the keyboard."),
            ("Variables and data types", 12, "Numbers, text and booleans.\n\nA variable is a name that points to a value. Python works out the type for you."),
            ("Making decisions with if", 10, "Use if, elif and else to run different code depending on a condition.\n\nComparison operators return True or False."),
            ("Loops and lists", 15, "A for loop repeats work for every item in a list.\n\nLists keep items in order and can grow or shrink."),
            ("Writing functions", 14, "A function packages code you want to reuse.\n\nUse def, give it parameters and return a result."),
        ],
        "quiz": ("Python basics check", 60, [
            ("Which keyword defines a function in Python?", ["func", "def", "function", "lambda"], 2),
            ("What does len([4, 5, 6]) return?", ["2", "3", "4", "6"], 2),
            ("Which type is the value 3.14?", ["int", "str", "float", "bool"], 3),
            ("How do you start a loop over items in a list?", ["for item in items:", "loop items:", "each item of items:"], 1),
        ]),
        "assignment": ("Build a tip calculator", "Write a Python script that asks for a bill amount and a tip percentage, "
                       "then prints the tip and the total. Upload your .py file or a short PDF write-up.", 100),
    },
    {
        "title": "Database Design with SQL",
        "category": "Data",
        "level": "intermediate",
        "summary": "Model real data, write clean SQL and understand why normalisation matters.",
        "description": "Move from spreadsheets to relational databases. Design tables, connect them with keys "
                       "and query them with joins and aggregates.",
        "lessons": [
            ("Tables, rows and keys", 12, "A table stores one kind of thing. A primary key identifies each row uniquely."),
            ("SELECT, WHERE and ORDER BY", 14, "Read data with SELECT.\n\nFilter with WHERE and sort with ORDER BY."),
            ("Joining tables", 16, "A foreign key links a row to a row in another table.\n\nJOIN combines them in a query."),
            ("Normalisation in practice", 18, "Remove repeated data by splitting tables.\n\nFirst, second and third normal form give you a checklist."),
        ],
        "quiz": ("SQL fundamentals", 70, [
            ("Which clause filters rows?", ["ORDER BY", "WHERE", "GROUP BY", "LIMIT"], 2),
            ("A foreign key...", ["identifies a row in its own table", "points to a primary key in another table", "sorts a table"], 2),
            ("Which JOIN keeps only matching rows?", ["INNER JOIN", "LEFT JOIN", "CROSS JOIN"], 1),
        ]),
        "assignment": ("Design a library database", "Draw an ER diagram for a library with books, members and loans. "
                       "Show keys and relationships, then upload it as a PDF or image.", 50),
    },
    {
        "title": "Cloud Basics on AWS",
        "category": "Cloud",
        "level": "beginner",
        "summary": "Understand EC2, RDS and S3 by deploying a small web application.",
        "description": "A guided tour of the core AWS services. You will see how a web server, a managed "
                       "database and object storage fit together.",
        "lessons": [
            ("What the cloud gives you", 9, "On-demand servers, storage and databases.\n\nYou pay for what you use and can start small."),
            ("EC2: your own virtual server", 15, "Pick an image, an instance size and a security group.\n\nConnect over SSH and install your application."),
            ("RDS: a managed database", 13, "AWS runs backups, patching and failover for PostgreSQL.\n\nYour app connects with a normal database URL."),
            ("S3: object storage", 12, "Buckets hold objects such as videos and PDFs.\n\nAccess is controlled with IAM roles, not passwords."),
        ],
        "quiz": ("AWS core services", 60, [
            ("Which service stores uploaded files as objects?", ["EC2", "RDS", "S3", "IAM"], 3),
            ("Which service runs a managed PostgreSQL database?", ["RDS", "S3", "Lambda"], 1),
            ("What lets an EC2 server call S3 without stored passwords?", ["An IAM role", "A public bucket", "A shared key file"], 1),
        ]),
        "assignment": ("Draw the architecture", "Sketch how a browser, EC2, RDS and S3 connect for the Lumen app. "
                       "Label the security groups. Upload an image or PDF.", 100),
    },
]


class Command(BaseCommand):
    help = "Create demo users, courses, quizzes and assignments."

    def handle(self, *args, **options):
        admin = self._user("admin", "Site", "Admin", "admin123", "admin", superuser=True)
        maya = self._user("maya", "Maya", "Rahman", "teach123", "instructor")
        omar = self._user("omar", "Omar", "Siddiqui", "teach123", "instructor")
        student = self._user("sara", "Sara", "Khan", "learn123", "student")
        self._user("ali", "Ali", "Ahmed", "learn123", "student")

        for index, spec in enumerate(COURSES):
            category, _ = Category.objects.get_or_create(name=spec["category"])
            teacher = maya if index != 1 else omar
            course, created = Course.objects.get_or_create(
                title=spec["title"],
                defaults={
                    "summary": spec["summary"], "description": spec["description"], "category": category,
                    "instructor": teacher, "level": spec["level"], "is_published": True,
                },
            )
            if not created:
                self.stdout.write(f"Course exists: {course.title}")
                continue
            for order, (title, minutes, body) in enumerate(spec["lessons"], start=1):
                lesson = Lesson.objects.create(course=course, title=title, order=order, duration_minutes=minutes, content=body)
                notes = f"{course.title}\nLesson {order}: {title}\n\n{body}\n"
                lesson.attachment.save(f"{course.slug}-lesson-{order}-notes.txt", ContentFile(notes.encode()), save=True)
            q_title, pass_mark, questions = spec["quiz"]
            quiz = Quiz.objects.create(course=course, title=q_title, pass_mark=pass_mark,
                                       description="Answer every question, then see what you missed.")
            for n, (text, options, correct) in enumerate(questions, start=1):
                question = Question.objects.create(quiz=quiz, text=text, order=n)
                for i, option in enumerate(options, start=1):
                    Choice.objects.create(question=question, text=option, is_correct=(i == correct))
            a_title, a_desc, points = spec["assignment"]
            Assignment.objects.create(course=course, title=a_title, description=a_desc, max_points=points,
                                      due_date=timezone.localdate() + timedelta(days=14))
            self.stdout.write(self.style.SUCCESS(f"Created course: {course.title}"))

        # Give the demo student some progress so dashboards are not empty.
        first = Course.objects.filter(title="Python for Beginners").first()
        if first:
            Enrollment.objects.get_or_create(student=student, course=first)
            for lesson in first.lessons.all()[:2]:
                LessonProgress.objects.get_or_create(student=student, lesson=lesson)

        self.stdout.write(self.style.SUCCESS(
            "\nDemo logins:\n  admin / admin123 (admin)\n  maya / teach123 (instructor)\n"
            "  omar / teach123 (instructor)\n  sara / learn123 (student)\n  ali / learn123 (student)"
        ))

    def _user(self, username, first, last, password, role, superuser=False):
        user, created = User.objects.get_or_create(username=username, defaults={
            "first_name": first, "last_name": last, "email": f"{username}@lumen.example", "role": role,
        })
        if created:
            user.set_password(password)
            if superuser:
                user.is_staff = True
                user.is_superuser = True
            user.save()
        return user
