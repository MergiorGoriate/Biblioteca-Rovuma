import uuid

from django.conf import settings
from django.db import models

from catalog.models import Edition


class Document(models.Model):
    edition = models.OneToOneField(Edition, related_name="document", on_delete=models.PROTECT)


class Version(models.Model):
    class State(models.TextChoices):
        PROCESSING = "processing", "Em processamento"
        REVIEW = "review", "Pendente de revisão"
        PUBLISHED = "published", "Publicado"
        ARCHIVED = "archived", "Arquivado"

    class Mode(models.TextChoices):
        READ = "read", "Só leitura"
        DOWNLOAD = "download", "Leitura e descarregamento"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, related_name="versions", on_delete=models.PROTECT)
    original_name = models.CharField(max_length=180)
    file_format = models.CharField(max_length=5)
    access_mode = models.CharField(max_length=10, choices=Mode.choices)
    authorization = models.TextField()
    sha256 = models.CharField(max_length=64, blank=True)
    pages = models.PositiveIntegerField(default=0)
    state = models.CharField(max_length=12, choices=State.choices, default=State.PROCESSING, db_index=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("document",), condition=models.Q(state="published"), name="one_live_version"),
            models.CheckConstraint(condition=~models.Q(state="published") | (models.Q(pages__gt=0) & ~models.Q(authorization="") & ~models.Q(sha256="")), name="published_version_verified"),
        ]


class Job(models.Model):
    class State(models.TextChoices):
        WAITING = "waiting", "Na fila"
        SENT = "sent", "Em análise"
        DONE = "done", "Concluída"
        ERROR = "error", "Falhou"

    version = models.OneToOneField(Version, related_name="job", on_delete=models.PROTECT)
    run = models.UUIDField(default=uuid.uuid4)
    state = models.CharField(max_length=8, choices=State.choices, default=State.WAITING, db_index=True)
    error = models.CharField(max_length=300, blank=True)
    changed = models.DateTimeField(auto_now=True)


class Upload(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    edition = models.ForeignKey(Edition, on_delete=models.PROTECT)
    name = models.CharField(max_length=180)
    size = models.PositiveBigIntegerField()
    offset = models.PositiveBigIntegerField(default=0)
    mode = models.CharField(max_length=10, choices=Version.Mode.choices)
    authorization = models.TextField()
    updated = models.DateTimeField(auto_now=True)
    version = models.OneToOneField(Version, null=True, on_delete=models.PROTECT)


class Licence(models.Model):
    version = models.OneToOneField(Version, related_name="licence", on_delete=models.PROTECT)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reference = models.TextField()
    recorded_at = models.DateTimeField(auto_now_add=True)
