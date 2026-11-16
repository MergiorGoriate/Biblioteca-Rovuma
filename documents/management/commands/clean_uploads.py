from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Attempt, ImportBatch
from documents.models import Upload
from documents.storage import part


class Command(BaseCommand):
    help = "Limpa carregamentos incompletos após 72 horas, limites expirados e pré-visualizações antigas."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=72)
        ids = list(Upload.objects.filter(updated__lt=cutoff, version__isnull=True).values_list("pk", flat=True))
        for pk in ids:
            with transaction.atomic():
                upload = Upload.objects.select_for_update().filter(pk=pk, updated__lt=cutoff, version__isnull=True).first()
                if upload:
                    part(pk).unlink(missing_ok=True)
                    upload.delete()
        Attempt.objects.filter(updated__lt=cutoff).delete()
        ImportBatch.objects.filter(confirmed=False, created__lt=cutoff).delete()
