import uuid

from django.core.management.base import BaseCommand
from django.db import transaction

from documents.models import Job, Upload


class Command(BaseCommand):
    help = "Recria a fila privada após restauro; executar com os escritores parados."

    @transaction.atomic
    def handle(self, *args, **options):
        discarded, _ = Upload.objects.filter(version__isnull=True).delete()
        jobs = Job.objects.select_for_update().filter(state=Job.State.SENT)
        count = 0
        for job in jobs:
            job.state, job.run, job.error = Job.State.WAITING, uuid.uuid4(), ""
            job.save()
            count += 1
        self.stdout.write(f"Processamentos reenfileirados: {count}. Transferências parciais removidas: {discarded}.")
