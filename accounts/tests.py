from hashlib import sha256
from io import StringIO
from urllib.parse import urlsplit

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from audit.models import Event


@override_settings(ALLOWED_HOSTS=["biblioteca.example.invalid", "testserver"],
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StaffInvitationTests(TestCase):
    def invite(self, username="bibliotecario.ensaio", **options):
        stdout = StringIO()
        defaults = {"url_base": "https://biblioteca.example.invalid", "responsavel": "Operador de ensaio",
                    "referencia": "Registo fictício de validação"}
        call_command("invite_staff", username, "bibliotecario", stdout=stdout, **(defaults | options))
        return urlsplit(stdout.getvalue().strip()).path

    def test_individual_invitation_activates_and_grants_only_library_role(self):
        link = self.invite()
        account = User.objects.get(username="bibliotecario.ensaio")
        self.assertFalse(account.is_active)
        self.assertFalse(account.has_usable_password())
        self.assertFalse(account.is_superuser)
        self.assertFalse(account.is_staff)
        self.assertIsNone(account.institutional_number)
        token = link.strip("/").rsplit("/", 1)[-1]
        self.assertEqual(account.activation_token_hash, sha256(token.encode()).hexdigest())
        self.assertNotIn(token, str(Event.objects.get(reference=str(account.pk)).details))
        self.assertContains(self.client.post(link, {"new_password1": "curta", "new_password2": "curta"}),
                            "8 car", html=False)
        password = "Frase de ensaio comprida e individual 154!"
        self.assertRedirects(self.client.post(link, {"new_password1": password, "new_password2": password}), reverse("management_login"))
        self.assertEqual(self.client.get(link).status_code, 404)
        self.assertRedirects(self.client.post(reverse("login"), {"username": account.username, "password": password}),
                             reverse("home"), fetch_redirect_response=False)
        self.assertContains(self.client.get(reverse("management")), "Painel administrativo")
        self.assertEqual(self.client.get(reverse("management")).status_code, 200)

    def test_reissue_invalidates_old_link_and_preserves_account(self):
        first = self.invite()
        latest = self.invite(reemitir=True)
        self.assertNotEqual(first, latest)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(self.client.get(first).status_code, 404)
        self.assertContains(self.client.get(latest), "Activar conta")

    def test_cannot_invite_existing_account_or_use_an_unconfigured_host(self):
        User.objects.create_user(username="existente")
        with self.assertRaises(CommandError):
            self.invite(username="existente")
        with self.assertRaises(CommandError):
            self.invite(username="existente", reemitir=True)
        with self.assertRaises(CommandError):
            self.invite(url_base="https://outra-biblioteca.example.invalid")
        self.assertFalse(User.objects.get(username="existente").groups.exists())


    @override_settings(SECURE_REFERRER_POLICY="strict-origin", CSRF_COOKIE_SECURE=True)
    def test_invitation_form_accepts_https_same_origin_referer_without_token_path(self):
        link = self.invite()
        client = Client(enforce_csrf_checks=True)
        response = client.get(link, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Referrer-Policy"], "strict-origin")
        self.assertTrue(response.cookies["csrftoken"]["secure"])
        password = "Frase de activação apenas de ensaio 154!"
        values = {"new_password1": password, "new_password2": password}
        failure = client.post(link, values, secure=True, HTTP_REFERER="https://testserver/")
        self.assertContains(failure, "Reabrir o formulário", status_code=403)
        values["csrfmiddlewaretoken"] = response.cookies["csrftoken"].value
        self.assertEqual(client.post(link, values, secure=True, HTTP_ORIGIN="https://outro.example.invalid").status_code, 403)
        self.assertRedirects(client.post(link, values, secure=True, HTTP_REFERER="https://testserver/"),
                             reverse("management_login"), fetch_redirect_response=False)
        self.assertEqual(client.get(link, secure=True).status_code, 404)
