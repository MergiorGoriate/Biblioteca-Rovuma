import hashlib
import json
import shutil
import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from documents.models import Job, Version
from documents.remote_processor import Unavailable, process
from documents.storage import original, reading_pdf


def advance(job):
    folder = settings.SPOOL_ROOT / str(job.run)
    version = job.version
    if job.state == Job.State.WAITING:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            source = original(version.pk)
            if shutil.disk_usage(folder).free < source.stat().st_size + settings.DISK_RESERVE_BYTES:
                raise OSError("Espaço insuficiente")
            target = folder / "original"
            if not (folder / "request.json").exists():
                shutil.copyfile(source, target)
                metadata = folder / "request.tmp"
                metadata.write_text(json.dumps({"format": version.file_format}), encoding="utf-8")
                metadata.replace(folder / "request.json")
            job.state = Job.State.SENT
        except OSError:
            job.state = Job.State.ERROR
            job.error = "Não foi possível enviar o ficheiro para análise. Verifique espaço e permissões."
    elif (folder / "result.json").is_file():
        try:
            result = json.loads((folder / "result.json").read_text())
            if result.get("error"):
                job.state, job.error = Job.State.ERROR, str(result["error"])[:300]
            else:
                with original(version.pk).open("rb") as file:
                    digest = hashlib.file_digest(file, "sha256").hexdigest()
                if result["sha256"] != digest or not 1 <= result["pages"] <= 1_000_000:
                    raise ValueError
                if version.file_format == "docx":
                    path = reading_pdf(version)
                    converted = folder / "reader.pdf"
                    if shutil.disk_usage(path.parent).free < converted.stat().st_size + settings.DISK_RESERVE_BYTES:
                        raise OSError("Espaço insuficiente")
                    pending = path.with_suffix(".tmp")
                    shutil.copyfile(converted, pending)
                    pending.replace(path)
                version.sha256, version.pages = digest, result["pages"]
                version.state = Version.State.REVIEW
                version.save(update_fields=["pages", "sha256", "state"])
                job.state, job.error = Job.State.DONE, ""
        except (OSError, KeyError, ValueError, TypeError):
            job.state, job.error = Job.State.ERROR, "Não foi possível validar ou guardar o resultado do processador."
        transaction.on_commit(lambda: shutil.rmtree(folder, ignore_errors=True))
    elif job.changed < timezone.now() - timedelta(minutes=20):
        job.state, job.error = Job.State.ERROR, "O processador não respondeu dentro do tempo máximo."
    else:
        return
    job.save(update_fields=["state", "error", "changed"])


def advance_remote(job, url, token):
    version = job.version
    path = reading_pdf(version)
    pending = path.with_name("remote-reader.tmp")
    if job.state == Job.State.WAITING:
        job.state = Job.State.SENT
        job.save(update_fields=["state", "changed"])
    try:
        result = process(url, token, original(version.pk), version.file_format, pending)
        if result.get("error"):
            job.state, job.error = Job.State.ERROR, result["error"]
        else:
            if version.file_format == "docx":
                pending.replace(path)
            version.sha256 = result["sha256"]
            version.pages = result["pages"]
            version.state = Version.State.REVIEW
            version.save(update_fields=["pages", "sha256", "state"])
            job.state, job.error = Job.State.DONE, ""
    except Unavailable:
        if job.changed >= timezone.now() - timedelta(minutes=20):
            return False
        job.state, job.error = Job.State.ERROR, "O processador privado não respondeu dentro do tempo máximo."
    except (OSError, ValueError, KeyError, TypeError):
        job.state, job.error = Job.State.ERROR, "Não foi possível validar ou guardar o resultado do processador privado."
    finally:
        pending.unlink(missing_ok=True)
    job.save(update_fields=["state", "error", "changed"])
    return True


class Command(BaseCommand):
    help = "Envia documentos ao processador e recolhe os resultados."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        import os

        url = os.environ.get("ROVUMA_PROCESSOR_URL")
        token = os.environ.get("ROVUMA_PROCESSOR_TOKEN", "")
        while True:
            ids = list(Job.objects.filter(state__in=[Job.State.WAITING, Job.State.SENT]).order_by("changed").values_list("pk", flat=True))
            for pk in ids:
                with transaction.atomic():
                    job = Job.objects.select_for_update().get(pk=pk)
                    if job.state in {Job.State.WAITING, Job.State.SENT}:
                        if url:
                            if not advance_remote(job, url, token):
                                break
                        else:
                            advance(job)
            if options["once"]:
                return
            time.sleep(3)
