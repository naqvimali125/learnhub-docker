from .models import Enrollment


def can_manage_course(user, course):
    return user.is_authenticated and (user.is_lms_admin or course.instructor_id == user.id)


def is_enrolled(user, course):
    return user.is_authenticated and Enrollment.objects.filter(student=user, course=course).exists()


def can_view_content(user, course):
    return can_manage_course(user, course) or is_enrolled(user, course)
