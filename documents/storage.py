from django.conf import settings

from catalog.sample_assets import PDF_KEYS, asset


def part(upload_id):
    return settings.PRIVATE_ROOT / "incoming" / f"{upload_id}.part"


def original(version_id):
    return settings.PRIVATE_ROOT / "versions" / str(version_id) / "original"


def original_file(version):
    key = PDF_KEYS.get(version.pk)
    if key and version.document.edition.work.is_demo:
        return asset(key, "pdf")
    return original(version.pk)


def reading_pdf(version):
    path = original_file(version)
    return path if version.file_format == "pdf" else path.with_name("reader.pdf")
