import csv
from datetime import date
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models

from .models import User


def validate_number(number):
    if not number or len(number) > 64:
        raise ValidationError("Indique um número de estudante com 1 a 64 caracteres.")
    for validator in User._meta.get_field("username").validators:
        validator(number)


def validate_rows(payload):
    reader = csv.DictReader(StringIO(payload, newline=""), strict=True)
    columns = {"numero", "validade", "email_validado"}
    if not reader.fieldnames or len(reader.fieldnames) != 3 or set(reader.fieldnames) != columns:
        raise ValueError("Use os cabeçalhos numero, validade e email_validado.")
    rows, seen = [], set()
    for raw in reader:
        row = {"line": reader.line_num, "error": ""}
        number, expiry, email = ((raw.get(field) or "").strip() for field in ("numero", "validade", "email_validado"))
        row.update(numero=number, validade=expiry, email_validado=email)
        try:
            if None in raw or any(value is None for value in raw.values()):
                raise ValueError("A linha deve ter três colunas.")
            validate_number(number)
            if number in seen:
                raise ValueError("Número repetido nesta lista.")
            try:
                row["expiry"] = date.fromisoformat(expiry)
            except ValueError:
                raise ValueError("Validade inválida. Use AAAA-MM-DD.") from None
            if row["expiry"].isoformat() != expiry:
                raise ValueError("Validade inválida. Use AAAA-MM-DD.")
            if email:
                if len(email) > 254:
                    raise ValueError("O endereço excede 254 caracteres.")
                validate_email(email)
        except ValidationError as exc:
            row["error"] = " ".join(exc.messages)
        except ValueError as exc:
            row["error"] = str(exc)
        seen.add(number)
        rows.append(row)

    if not rows:
        raise ValueError("A lista não contém estudantes.")
    numbers = {row["numero"] for row in rows if not row["error"]}
    accounts = User.objects.filter(username__in=numbers).in_bulk(field_name="username")
    conflicting = User.objects.filter(institutional_number__in=numbers).exclude(
        username=models.F("institutional_number")).values_list("institutional_number", flat=True)
    reserved = set(conflicting)
    for row in rows:
        number = row["numero"]
        account = accounts.get(number)
        if not row["error"] and (number in reserved or account and account.institutional_number != number):
            row["error"] = "O número já está associado a outra conta."
    return rows
