from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User
from accounts.roles import ROLES, ensure_role
from audit.models import record


class Command(BaseCommand):
    help = "Atribui ou retira um grupo com justificação e auditoria."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("role", choices=ROLES)
        parser.add_argument("--actor", required=True, help="Conta do responsável pela operação")
        parser.add_argument("--reason", required=True)
        parser.add_argument("--remove", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        reason = options["reason"].strip()
        if not reason:
            raise CommandError("Indique a justificação.")
        try:
            user = User.objects.select_for_update().get(username=options["username"])
            actor = User.objects.get(username=options["actor"], is_active=True, state=User.State.ACTIVE)
        except User.DoesNotExist as exc:
            raise CommandError("Conta do operador ou do destinatário inválida.") from exc
        group = ensure_role(options["role"])
        if options["remove"]:
            user.groups.remove(group)
        else:
            user.groups.add(group)
        user.session_version += 1
        user.save(update_fields=["session_version"])
        record(actor, "credential", "Retirou função" if options["remove"] else "Atribuiu função",
               user.pk, role=group.name, reason=reason)
