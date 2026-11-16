import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        api_key = os.environ.get("RESEND_API_KEY")
        if not api_key:
            if self.fail_silently:
                return 0
            raise ImproperlyConfigured("Defina RESEND_API_KEY para enviar correio pelo Resend.")

        sent = 0
        for message in email_messages:
            if not message.to:
                continue
            payload = {
                "from": message.from_email,
                "to": message.to,
                "subject": message.subject,
                "text": message.body,
            }
            request = Request(
                "https://api.resend.com/emails",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=settings.EMAIL_TIMEOUT):
                    sent += 1
            except HTTPError as error:
                status = error.code
                error.close()
                if not self.fail_silently:
                    raise OSError(f"O Resend rejeitou o envio (HTTP {status}).") from None
            except (URLError, TimeoutError):
                if not self.fail_silently:
                    raise OSError("Falhou a ligação à API de correio do Resend.") from None
        return sent
