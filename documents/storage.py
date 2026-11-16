from django.conf import settings


def part(upload_id):
    return settings.PRIVATE_ROOT / "incoming" / f"{upload_id}.part"


def original(version_id):
    return settings.PRIVATE_ROOT / "versions" / str(version_id) / "original"


def reading_pdf(version):
    path = original(version.pk)
    return path if version.file_format == "pdf" else path.with_name("reader.pdf")
