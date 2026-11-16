import hashlib
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from audit.models import record
from catalog.models import Copy, Edition, Identifier, Location, Subject, Work
from catalog.views import cover_path
from documents.models import Document, Job, Licence, Version
from documents.storage import original
from documents.worker import pdf_pages


SAMPLES = (
    ("investigacao", "Métodos de investigação científica", "Investigação", "Três passos para formular uma pergunta, recolher evidências e interpretar os resultados.", "read", False),
    ("biologia", "Fundamentos de biologia", "Biologia", "Uma introdução breve à célula, à observação biológica e à análise de evidências.", "download", True),
    ("ecologia", "Ecologia e conservação", "Ecologia", "Exercícios de observação para distinguir espécies, habitats e pressões ambientais.", "read", False),
    ("escrita", "Escrita académica", "Língua portuguesa", "Registo fictício para experimentar a pesquisa e a localização de exemplares físicos.", None, True),
)
REFERENCE = "Material original de demonstração da aplicação, autorizado para ensaio no ambiente de teste."


def install_file(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
        try:
            temporary.write(contents)
            temporary.close()
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)


class Command(BaseCommand):
    help = "Insere obras fictícias no ambiente de ensaio."

    def add_arguments(self, parser):
        parser.add_argument("--confirm-test-environment", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        if not options["confirm_test_environment"] or (not settings.DEBUG and os.getenv("RAILWAY_ENVIRONMENT_NAME") != "teste"):
            raise CommandError("Execute apenas num ambiente de teste autorizado.")
        files = settings.BASE / "docs" / "amostras"
        operator, _ = User.objects.select_for_update().get_or_create(
            username="sistema-demonstracao",
            defaults={"first_name": "Registo automático de demonstração", "is_active": False,
                      "state": User.State.SUSPENDED, "password": "!"},
        )
        if operator.is_active or operator.has_usable_password():
            raise CommandError("O identificador reservado para demonstração já está em uso.")
        location, _ = Location.objects.get_or_create(name="Secção fictícia de demonstração", defaults={
            "description": "Localização de teste. Este exemplar não corresponde a um livro físico real.",
            "unit": "Unidade fictícia", "room": "Sala de teste", "shelf": "Estante D",
        })
        created = 0
        for key, title, subject, summary, mode, physical in SAMPLES:
            marker = f"ROVUMA-DEMO-{key.upper()}"
            existing = Identifier.objects.filter(scheme="Demonstração", value=marker).select_related("edition__work").first()
            if existing:
                if not existing.edition.work.is_demo:
                    raise CommandError(f"O identificador reservado {marker} pertence a uma obra do acervo.")
                continue
            work = Work.objects.create(title=title, summary=summary, language="Português", is_demo=True,
                                       kind=Work.Kind.BOOK, state=Work.State.PUBLISHED,
                                       terms="Obra fictícia para testar a Biblioteca Rovuma.")
            work.subjects.add(Subject.objects.get_or_create(name=subject)[0])
            edition = Edition.objects.create(work=work, label="Edição de demonstração", year=timezone.localdate().year)
            Identifier.objects.create(edition=edition, scheme="Demonstração", value=marker)
            install_file(cover_path(work.pk), (files / f"{key}.webp").read_bytes())
            if physical:
                Copy.objects.create(edition=edition, location=location, inventory=marker)
            if mode:
                source = files / f"{key}.pdf"
                content = source.read_bytes()
                document = Document.objects.create(edition=edition)
                version = Version.objects.create(
                    document=document, state=Version.State.PUBLISHED, access_mode=mode,
                    original_name=f"{key}-demonstracao.pdf", file_format="pdf", authorization=REFERENCE,
                    sha256=hashlib.sha256(content).hexdigest(), pages=pdf_pages(source),
                )
                install_file(original(version.pk), content)
                Licence.objects.create(version=version, recorded_by=operator, reference=REFERENCE)
                Job.objects.create(version=version, state=Job.State.DONE)
            record(None, "collection", "Registou obra fictícia", work.pk, identificador=marker)
            created += 1
        self.stdout.write(f"Obras de demonstração adicionadas: {created}.")
