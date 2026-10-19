import os

from django.conf import settings
from django.core.exceptions import ValidationError


def _check(file, allowed, max_mb, label):
    ext = os.path.splitext(file.name)[1].lower().lstrip(".")
    if ext not in allowed:
        raise ValidationError(f"{label} must be one of: {', '.join(sorted(allowed))}.")
    if file.size > max_mb * 1024 * 1024:
        raise ValidationError(f"{label} is larger than {max_mb} MB.")


def validate_video(file):
    _check(file, {"mp4", "webm", "mov", "m4v"}, settings.MAX_VIDEO_MB, "Video")


def validate_document(file):
    _check(file, {"pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "txt", "zip", "csv", "png", "jpg", "jpeg"},
           settings.MAX_FILE_MB, "File")
