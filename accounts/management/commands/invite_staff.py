import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from accounts.roles import ROLES, ensure_role
from audit.models import record


class Command(BaseCommand):
    help = "Emite um convite individual depois de validada a designação do funcionário."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("role", choices=ROLES)
        parser.add_argument("--url-base", required=True)
        parser.add_argument("--responsavel", required=True)
        parser.add_argument("--referencia", required=True)
        parser.add_argument("--email-validado", default="")
        parser.add_argument("--reemitir", action="store_true")

    def handle(self, *args, **options):
        origin = options["url_base"].strip().rstrip("/")
        try:
            url = urlsplit(origin)
            port = url.port
        except ValueError as exc:
            raise CommandError("A origem HTTPS é inválida.") from exc
        if (url.scheme != "https" or url.hostname not in settings.ALLOWED_HOSTS or
                url.username is not None or url.password is not None or port == 0 or url.path or url.query or url.fragment):
            raise CommandError("Indique a origem HTTPS exacta de um domínio configurado em DJANGO_ALLOWED_HOSTS.")
        responsible = options["responsavel"].strip()
        reference = options["referencia"].strip()
        if not responsible or not reference or len(responsible) > 160 or len(reference) > 255:
            raise CommandError("Indique o responsável e a referência da designação validada.")

        token = secrets.token_urlsafe(32)
        username = options["username"]
        role = options["role"]
        email = options["email_validado"].strip()
        try:
            with transaction.atomic():
                if options["reemitir"]:
                    user = User.objects.select_for_update().filter(
                        username=username, institutional_number__isnull=True, identity_source=User.Identity.LOCAL,
                        is_active=False, state=User.State.PENDING, is_staff=False, is_superuser=False,
                        groups__name=role,
                    ).first()
                    if user is None:
                        raise CommandError("Não existe um convite pendente para essa conta e função.")
                else:
                    user = User(username=username, verified_email=email, is_active=False, state=User.State.PENDING)
                    user.set_unusable_password()
                    user.full_clean()
                    user.save(force_insert=True)
                    user.groups.add(ensure_role(role))
                user.activation_token_hash = hashlib.sha256(token.encode()).hexdigest()
                user.activation_expires = timezone.now() + timedelta(hours=24)
                user.save(update_fields=["activation_token_hash", "activation_expires"])
                record(None, "credential", "Reemitiu convite de funcionário" if options["reemitir"] else "Convidou funcionário",
                       user.pk, role=role, responsible=responsible, designation_reference=reference)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        except IntegrityError as exc:
            raise CommandError("O nome de utilizador já está registado.") from exc

        self.stdout.write(origin + reverse("activate", kwargs={"token": token}))
