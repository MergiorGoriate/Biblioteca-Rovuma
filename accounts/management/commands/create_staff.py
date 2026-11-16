from getpass import getpass

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from accounts.models import User
from audit.models import record


class Command(BaseCommand):
    help = "Cria uma conta individual sem funções atribuídas."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--email-validado", default="")

    def handle(self, *args, **options):
        user = User(username=options["username"], verified_email=options["email_validado"])
        password = getpass("Palavra-passe inicial: ")
        if password != getpass("Repita a palavra-passe: "):
            raise CommandError("As palavras-passe não coincidem.")
        try:
            user.full_clean(exclude=["password"])
            password_validation.validate_password(password, user)
            user.set_password(password)
            with transaction.atomic():
                user.save(force_insert=True)
                record(None, "credential", "Criou conta de funcionário pela consola", user.pk)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        except IntegrityError as exc:
            raise CommandError("Já existe uma conta com esse nome.") from exc
        self.stdout.write("Conta criada. Atribua as funções autorizadas com set_role.")
