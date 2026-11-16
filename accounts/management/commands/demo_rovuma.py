from datetime import timedelta
from hashlib import sha256
import os
from shutil import copyfile

from django.conf import settings
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from accounts.roles import ensure_role
from catalog.models import Copy, Edition, Location, Work
from documents.models import Document, Job, Licence, Version
from documents.storage import original


class Command(BaseCommand):
    help = "Coloca dados fictícios num ambiente de desenvolvimento local."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG or settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("A demonstração só pode ser instalada no SQLite local de desenvolvimento.")
        student, staff = [
            self.demo_user("000042", "DEMO_STUDENT_PASSWORD", "000042"),
            self.demo_user("bibliotecario.demo", "DEMO_STAFF_PASSWORD"),
        ]
        staff.groups.add(ensure_role("bibliotecario"))
        work, _ = Work.objects.get_or_create(title="Introdução à investigação — obra fictícia", defaults={
            "language": "Português", "kind": Work.Kind.MANUAL, "state": Work.State.PUBLISHED,
            "summary": "Material fictício de demonstração, sem dados académicos reais.",
        })
        edition, _ = Edition.objects.get_or_create(work=work, label="Edição de demonstração")
        location, _ = Location.objects.get_or_create(name="Unidade fictícia", defaults={
            "unit": "Unidade de demonstração", "room": "Sala fictícia", "shelf": "Estante A", "level": "Prateleira 1",
        })
        Copy.objects.get_or_create(inventory="FICTICIO-42", defaults={"edition": edition, "location": location})
        document, _ = Document.objects.get_or_create(edition=edition)
        fixture = settings.BASE / "docs" / "documento-demonstracao.pdf"
        version, _ = Version.objects.get_or_create(document=document, state=Version.State.PUBLISHED, defaults={
            "original_name": "demonstracao.pdf", "file_format": "pdf", "access_mode": Version.Mode.READ,
            "authorization": "Documento fictício incluído para teste da aplicação.",
            "sha256": sha256(fixture.read_bytes()).hexdigest(), "pages": 3,
        })
        path = original(version.pk)
        path.parent.mkdir(parents=True, exist_ok=True)
        copyfile(fixture, path)
        Job.objects.get_or_create(version=version, defaults={"state": Job.State.DONE})
        Licence.objects.get_or_create(version=version, defaults={"recorded_by": staff, "reference": version.authorization})
        self.stdout.write("Demonstração local pronta. Utilizadores: 000042 e bibliotecario.demo.")

    def demo_user(self, username, variable, number=None):
        password = os.environ.get(variable)
        if not password:
            raise CommandError(f"Defina {variable} no ambiente local.")
        user, created = User.objects.get_or_create(username=username, defaults={
            "institutional_number": number, "first_name": "Demonstração local",
        })
        if not created and (user.first_name != "Demonstração local" or user.institutional_number != number
                            or user.is_superuser or user.is_staff):
            raise CommandError("Já existe uma conta incompatível com a demonstração.")
        try:
            password_validation.validate_password(password, user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        user.set_password(password)
        user.credential_until = timezone.localdate() + timedelta(days=30) if number else None
        user.save(update_fields=["password", "credential_until"])
        return user
