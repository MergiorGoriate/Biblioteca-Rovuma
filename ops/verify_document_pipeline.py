"""Exercita o fluxo real numa base e num volume descartáveis."""

import argparse
import hashlib
import os

import django

from documents.worker import pdf_pages
from ops.verify_processor import write_probe_docx, write_probe_odt


def prepare(file_format):
    from django.contrib.auth import get_user_model
    from django.db import transaction

    from catalog.models import Edition, Work
    from documents.models import Document, Job, Licence, Version
    from documents.storage import original

    with transaction.atomic():
        operator, _ = get_user_model().objects.get_or_create(username="verificacao.processador")
        work = Work.objects.create(title="Verificação isolada do processador", language="Português")
        edition = Edition.objects.create(work=work, label="Sonda técnica")
        document = Document.objects.create(edition=edition)
        version = Version.objects.create(
            document=document, original_name=f"sonda.{file_format}", file_format=file_format,
            access_mode=Version.Mode.READ, authorization="Sonda fictícia de validação da instalação.",
        )
        Licence.objects.create(version=version, recorded_by=operator, reference=version.authorization)
        Job.objects.create(version=version)
        path = original(version.pk)
        path.parent.mkdir(parents=True)
        if file_format == "txt":
            path.write_text("Ensaio de conversão TXT em Português.\n", encoding="utf-8")
        else:
            {"docx": write_probe_docx, "odt": write_probe_odt}[file_format](path)
    print(version.pk)


def verify(version_id):
    from documents.models import Job, Version
    from documents.storage import original, reading_pdf

    version = Version.objects.select_related("job").get(pk=version_id)
    if version.job.state != Job.State.DONE or version.state != Version.State.REVIEW:
        raise SystemExit(f"A conversão não chegou à revisão: {version.job.get_state_display()} {version.job.error}")
    with original(version.pk).open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    path = reading_pdf(version)
    if digest != version.sha256 or pdf_pages(path) != version.pages:
        raise SystemExit("O original ou o PDF de leitura não passou a verificação de integridade.")
    from pypdf import PdfReader
    text = " ".join(page.extract_text() for page in PdfReader(path).pages)
    if version.file_format in {"odt", "txt"} and "Ensaio de conversão" not in text:
        raise SystemExit("O texto acentuado não foi preservado na conversão.")
    print(f"{version.file_format.upper()} analisado e convertido. PDF privado com {version.pages} página(s), pendente de revisão.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("version", nargs="?", help="UUID da versão a verificar; omita para preparar a sonda.")
    parser.add_argument("--format", choices=("docx", "odt", "txt"), default="docx")
    args = parser.parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rovuma.settings")
    django.setup()
    if args.version:
        verify(args.version)
    else:
        prepare(args.format)
