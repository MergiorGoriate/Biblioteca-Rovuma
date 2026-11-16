from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    class State(models.TextChoices):
        PENDING = "pending", "Pendente"
        ACTIVE = "active", "Activa"
        SUSPENDED = "suspended", "Suspensa"

    class Identity(models.TextChoices):
        LOCAL = "local", "Biblioteca"
        INSTITUTIONAL = "institutional", "Institucional"

    institutional_number = models.CharField(max_length=64, unique=True, null=True, blank=True)
    credential_until = models.DateField(null=True, blank=True)
    verified_email = models.EmailField(blank=True)
    state = models.CharField(max_length=12, choices=State.choices, default=State.ACTIVE)
    identity_source = models.CharField(max_length=16, choices=Identity.choices, default=Identity.LOCAL)
    identity_subject = models.CharField(max_length=255, blank=True)
    session_version = models.PositiveIntegerField(default=0)
    activation_token_hash = models.CharField(max_length=64, blank=True)
    activation_expires = models.DateTimeField(null=True, blank=True)

    class Meta:
        permissions = (
            ("manage_credential", "Gerir credenciamento"),
            ("correct_number", "Corrigir número institucional"),
        )


class ImportBatch(models.Model):
    source = models.CharField(max_length=255)
    operator = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    payload = models.TextField(blank=True)
    confirmed = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)


class Attempt(models.Model):
    scope = models.CharField(max_length=64)
    address = models.CharField(max_length=100)
    count = models.PositiveIntegerField(default=0)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("scope", "address"), name="unique_attempt_scope")]
