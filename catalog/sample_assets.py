from uuid import UUID, uuid5

from django.conf import settings


SCHEME = "Demonstração"
PREFIX = "ROVUMA-DEMO-"
KEYS = ("investigacao", "biologia", "ecologia", "escrita")
NAMESPACE = UUID("da71b636-3af7-4904-be14-fb5eb20aab17")
PDF_KEYS = {uuid5(NAMESPACE, key): key for key in KEYS if key != "escrita"}


def asset(key, extension):
    return settings.BASE / "docs" / "amostras" / f"{key}.{extension}"
