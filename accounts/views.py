import csv
import hashlib
import io
import secrets
from datetime import timedelta
from django import forms
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.contrib.auth.views import LoginView, PasswordChangeView, PasswordResetView
from django.contrib.auth.forms import PasswordResetForm
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from audit.models import record
from .access import has, permission, require, student
from .models import ImportBatch, User


class LocalLogin(LoginView):
    template_name = "registration/login.html"
    def form_valid(self, form):
        user = form.get_user()
        if user.identity_source != User.Identity.LOCAL:
            form.add_error(None, "Utilize a autenticação institucional.")
            return self.form_invalid(form)
        response = super().form_valid(form)
        self.request.session["account_version"] = user.session_version
        return response


@require_POST
def sign_out(request):
    logout(request)
    return redirect("login")


class ResetToken(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return super()._make_hash_value(user, timestamp) + str(user.session_version)


class VerifiedEmailResetForm(PasswordResetForm):
    def get_users(self, email):
        return User.objects.filter(verified_email__iexact=email, is_active=True,
                                   state=User.State.ACTIVE).exclude(password="").iterator()


class LocalReset(PasswordResetView):
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.html"
    success_url = reverse_lazy("password_reset_done")
    token_generator = ResetToken()
    form_class = VerifiedEmailResetForm


class LocalChange(PasswordChangeView):
    template_name = "registration/password_change_form.html"
    success_url = reverse_lazy("password_change_done")


@require(lambda u: student(u) or has(u, "catalog.manage_collection"))
def profile(request):
    return render(request, "profile.html")


def activate(request, token):
    digest = hashlib.sha256(token.encode()).hexdigest()
    user = get_object_or_404(User, activation_token_hash=digest,
                             activation_expires__gt=timezone.now(), is_active=False)
    class ActivationForm(forms.Form):
        new_password1 = forms.CharField(widget=forms.PasswordInput)
        new_password2 = forms.CharField(widget=forms.PasswordInput)
        def clean(self):
            data = super().clean()
            if data.get("new_password1") != data.get("new_password2"):
                raise forms.ValidationError("As senhas não coincidem.")
            return data
    form = ActivationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        from django.contrib.auth.password_validation import validate_password
        validate_password(form.cleaned_data["new_password1"], user)
        user.set_password(form.cleaned_data["password1"])
        user.state = User.State.ACTIVE
        user.is_active = True
        user.activation_token_hash = ""
        user.activation_expires = None
        user.session_version += 1
        user.save()
        return redirect("login")
    return render(request, "form.html", {"heading": "Activar conta", "form": form})


@permission("accounts.manage_credential")
def students(request):
    q = request.GET.get("q", "").strip()
    qs = User.objects.filter(institutional_number__isnull=False)
    if q: qs = qs.filter(institutional_number__icontains=q)
    return render(request, "students.html", {"page": Paginator(qs.order_by("username"), 30).get_page(request.GET.get("page")), "q": q})


@permission("accounts.manage_credential")
def credential(request, pk):
    account = get_object_or_404(User, pk=pk)
    activation_link = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action in ("suspend", "resume"):
            if not request.POST.get("reason", "").strip():
                messages.error(request, "Indique a justificação.")
            else:
                account.state = User.State.SUSPENDED if action == "suspend" else User.State.ACTIVE
                account.session_version += 1
                account.save()
                record(request.user, "credential", action, account.pk, reason=request.POST["reason"])
                return redirect("credential", pk=pk)
        elif action == "activate" and account.state == User.State.PENDING:
            token = secrets.token_urlsafe(32)
            account.activation_token_hash = hashlib.sha256(token.encode()).hexdigest()
            account.activation_expires = timezone.now() + timedelta(minutes=30)
            account.save()
            record(request.user, "credential", "Emitiu activação", account.pk)
            activation_link = request.build_absolute_uri(reverse_lazy("activate", kwargs={"token": token}))
    return render(request, "credential_rebuilt.html", {"account": account, "activation_link": activation_link})


@permission("accounts.correct_number")
def correct(request, pk):
    account = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        number = request.POST.get("number", "").strip()
        reason = request.POST.get("reason", "").strip()
        if number and reason and not User.objects.filter(institutional_number=number).exclude(pk=pk).exists():
            account.institutional_number = number
            account.username = number
            account.session_version += 1
            account.save()
            record(request.user, "credential", "Corrigiu número", account.pk, reason=reason)
            return redirect("credential", pk=pk)
    return render(request, "correct_rebuilt.html", {"account": account})


@permission("accounts.manage_credential")
def imports(request):
    if request.method == "POST":
        source = request.POST.get("source", "").strip()
        uploaded = request.FILES.get("file")
        if source and uploaded and uploaded.size <= 2 * 1024 * 1024:
            try:
                payload = uploaded.read().decode("utf-8-sig")
                rows = list(csv.DictReader(io.StringIO(payload)))
                if not rows or not {"numero", "validade", "email_validado"}.issubset(rows[0]):
                    raise ValueError("Cabeçalhos inválidos")
                batch = ImportBatch.objects.create(source=source, operator=request.user, payload=payload)
                return redirect("import_preview", pk=batch.pk)
            except (UnicodeError, ValueError):
                messages.error(request, "Lista CSV inválida.")
    return render(request, "imports_rebuilt.html")


@permission("accounts.manage_credential")
def import_preview(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk)
    rows = list(csv.DictReader(io.StringIO(batch.payload)))
    if request.method == "POST" and not batch.confirmed:
        from datetime import date
        for row in rows:
            number = row["numero"].strip()
            try: valid = date.fromisoformat(row["validade"].strip())
            except ValueError: continue
            if not number: continue
            user, created = User.objects.get_or_create(username=number, defaults={
                "institutional_number": number, "state": User.State.PENDING})
            if created: user.set_unusable_password()
            user.credential_until = valid
            user.verified_email = row["email_validado"].strip()
            user.save()
        batch.confirmed = True
        batch.save()
        record(request.user, "credential", "Importou estudantes", batch.pk)
        return redirect("students")
    return render(request, "import_preview_rebuilt.html", {"batch": batch, "rows": rows})
