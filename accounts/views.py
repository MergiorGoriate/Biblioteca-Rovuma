import csv
import hashlib
import secrets
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.contrib.auth.views import LoginView, PasswordChangeView, PasswordResetView, redirect_to_login
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import BooleanField, Case, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from audit.models import record
from .access import can_manage, has, permission, require, student
from .importing import validate_number, validate_rows
from .models import ImportBatch, User
from .throttling import admit


class LocalAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        if not user.is_active or user.state != User.State.ACTIVE or user.identity_source != User.Identity.LOCAL:
            raise self.get_invalid_login_error()


class ThrottledFormView:
    def post(self, request, *args, **kwargs):
        if not admit(request, self.rate_scope, self.rate_limit):
            form = self.get_form_class()()
            response = self.render_to_response(self.get_context_data(form=form, limited=True), status=429)
            response["Retry-After"] = "900"
            return response
        return super().post(request, *args, **kwargs)


class LocalLogin(ThrottledFormView, LoginView):
    template_name = "registration/login.html"
    authentication_form = LocalAuthenticationForm
    rate_scope = "login"
    rate_limit = 20


class ManagementAuthenticationForm(LocalAuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not can_manage(user):
            raise self.get_invalid_login_error()


class ManagementLogin(LocalLogin):
    template_name = "management/login.html"
    authentication_form = ManagementAuthenticationForm
    next_page = reverse_lazy("management")
    def get(self, request, *args, **kwargs):
        if can_manage(request.user):
            destination = self.get_success_url()
            if destination.split("?", 1)[0].rstrip("/") == request.path.rstrip("/"):
                destination = self.get_default_redirect_url()
            return redirect(destination)
        return super().get(request, *args, **kwargs)


@require_POST
def sign_out(request):
    logout(request)
    return redirect("login")


class ResetToken(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return f"{super()._make_hash_value(user, timestamp)}:{user.session_version}:{user.verified_email}"


class VerifiedEmailResetForm(PasswordResetForm):
    def get_users(self, email):
        users = User.objects.filter(
            verified_email__iexact=email,
            is_active=True,
            state=User.State.ACTIVE,
            identity_source=User.Identity.LOCAL,
        ).exclude(password="")
        return (user for user in users.iterator() if user.has_usable_password())

    def send_mail(self, subject_template_name, email_template_name, context,
                  from_email, to_email, html_email_template_name=None):
        verified_email = context["user"].verified_email
        return super().send_mail(
            subject_template_name, email_template_name,
            {**context, "email": verified_email}, from_email, verified_email,
            html_email_template_name=html_email_template_name,
        )


class LocalReset(ThrottledFormView, PasswordResetView):
    rate_scope = "reset"
    rate_limit = 12
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.html"
    success_url = reverse_lazy("password_reset_done")
    token_generator = ResetToken()
    form_class = VerifiedEmailResetForm


class LocalChange(PasswordChangeView):
    template_name = "registration/password_change_form.html"
    management_area = False
    success_url = reverse_lazy("password_change_done")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.management_area:
            context["layout"] = "management/base.html"
        return context

    def dispatch(self, request, *args, **kwargs):
        if self.management_area and not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url=reverse_lazy("management_login"))
        if self.management_area and not can_manage(request.user):
            raise PermissionDenied
        if request.user.is_authenticated and request.user.identity_source != User.Identity.LOCAL:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


@require(lambda u: student(u) or has(u, "catalog.manage_collection"))
def profile(request):
    return render(request, "profile.html")


@never_cache
def activate(request, token):
    digest = hashlib.sha256(token.encode()).hexdigest()
    eligible = User.objects.filter(activation_token_hash=digest, activation_expires__gt=timezone.now(),
                                   state=User.State.PENDING, is_active=False, identity_source=User.Identity.LOCAL)
    with transaction.atomic():
        user = get_object_or_404(eligible.select_for_update() if request.method == "POST" else eligible)
        form = SetPasswordForm(user, request.POST if request.method == "POST" else None)
        if request.method == "POST" and form.is_valid():
            user = form.save(commit=False)
            user.state = User.State.ACTIVE
            user.is_active = True
            user.activation_token_hash = ""
            user.activation_expires = None
            user.session_version += 1
            user.save()
            return redirect("login")
    return render(request, "form.html", {"heading": "Activar conta", "form": form})


@require(lambda user: has(user, "accounts.manage_credential") or has(user, "accounts.correct_number"),
         login_url="management_login")
def students(request):
    q = request.GET.get("q", "").strip()[:64]
    state = request.GET.get("estado", "")
    qs = User.objects.filter(institutional_number__isnull=False)
    if q:
        qs = qs.filter(institutional_number__icontains=q)
    active = Q(state=User.State.ACTIVE, is_active=True)
    valid = Q(credential_until__gte=timezone.localdate())
    if state == "active":
        qs = qs.filter(active & valid)
    elif state == "expired":
        qs = qs.filter(active & ~valid)
    elif state in (User.State.PENDING, User.State.SUSPENDED):
        qs = qs.filter(state=state)
    else:
        state = ""
    states = (("active", "Credenciamento válido"), ("pending", "Pendentes de activação"),
              ("expired", "Sem credenciamento válido"), ("suspended", "Suspensas"))
    qs = qs.annotate(has_current_credential=Case(When(active & valid, then=Value(True)),
                                                default=Value(False), output_field=BooleanField()))
    page = Paginator(qs.order_by("username"), 30).get_page(request.GET.get("page"))
    return render(request, "students.html", {"page": page, "q": q, "state": state, "states": states})



@permission("accounts.manage_credential")
@never_cache
def credential(request, pk):
    accounts = User.objects.filter(institutional_number__isnull=False)
    account = get_object_or_404(accounts, pk=pk)
    activation_link = None
    if request.method == "POST":
        action = request.POST.get("action")
        reason = request.POST.get("reason", "").strip()
        with transaction.atomic():
            account = get_object_or_404(accounts.select_for_update(), pk=pk)
            transitions = {"suspend": (User.State.ACTIVE, User.State.SUSPENDED),
                           "resume": (User.State.SUSPENDED, User.State.ACTIVE)}
            if action in transitions and reason and account.is_active and account.state == transitions[action][0]:
                account.state = transitions[action][1]
                account.session_version += 1
                account.save(update_fields=["state", "session_version"])
                record(request.user, "credential", action, account.pk, reason=reason)
                return redirect("credential", pk=pk)
            if action == "activate" and reason and account.state == User.State.PENDING and not account.is_active and account.identity_source == User.Identity.LOCAL:
                token = secrets.token_urlsafe(32)
                account.activation_token_hash = hashlib.sha256(token.encode()).hexdigest()
                account.activation_expires = timezone.now() + timedelta(minutes=30)
                account.save(update_fields=["activation_token_hash", "activation_expires"])
                record(request.user, "credential", "Emitiu activação", account.pk, reason=reason)
                activation_link = request.build_absolute_uri(reverse_lazy("activate", kwargs={"token": token}))
            else:
                messages.error(request, "Confirme o estado da conta e indique a justificação para confirmar a identidade, suspender ou reactivar.")
    return render(request, "credential_rebuilt.html", {"account": account, "activation_link": activation_link})


@permission("accounts.correct_number")
def correct(request, pk):
    accounts = User.objects.filter(institutional_number__isnull=False)
    account = get_object_or_404(accounts, pk=pk)
    if request.method == "POST":
        number = request.POST.get("number", "").strip()
        reason = request.POST.get("reason", "").strip()
        try:
            validate_number(number)
            if not reason:
                raise ValidationError("Indique a justificação.")
            with transaction.atomic():
                account = get_object_or_404(accounts.select_for_update(), pk=pk)
                account.institutional_number = number
                account.username = number
                account.session_version += 1
                account.activation_token_hash = ""
                account.activation_expires = None
                account.save()
                record(request.user, "credential", "Corrigiu número", account.pk, reason=reason)
            return redirect("students")
        except IntegrityError:
            messages.error(request, "O número já está associado a outra conta.")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    return render(request, "correct_rebuilt.html", {"account": account})


@permission("accounts.manage_credential")
def imports(request):
    if request.method == "POST":
        source = request.POST.get("source", "").strip()
        uploaded = request.FILES.get("file")
        if not source or len(source) > 255 or not uploaded or uploaded.size > 2 * 1024 * 1024:
            messages.error(request, "Indique a origem e escolha um CSV de até 2 MiB.")
        else:
            try:
                payload = uploaded.read().decode("utf-8-sig")
                validate_rows(payload)
                batch = ImportBatch.objects.create(source=source, operator=request.user, payload=payload)
                return redirect("import_preview", pk=batch.pk)
            except (UnicodeError, csv.Error):
                messages.error(request, "O ficheiro deve ser um CSV válido em UTF-8.")
            except ValueError as exc:
                messages.error(request, str(exc))
    return render(request, "imports_rebuilt.html")


@permission("accounts.manage_credential")
def import_preview(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk)
    rows = []
    try:
        with transaction.atomic():
            if request.method == "POST":
                batch = get_object_or_404(ImportBatch.objects.select_for_update(), pk=pk)
            if batch.confirmed:
                return redirect("students")
            rows = validate_rows(batch.payload)
            if request.method == "POST" and not any(row["error"] for row in rows):
                for row in sorted(rows, key=lambda row: row["numero"]):
                    number = row["numero"]
                    user, _ = User.objects.select_for_update().get_or_create(username=number, defaults={
                        "institutional_number": number, "state": User.State.PENDING, "is_active": False, "password": "!",
                    })
                    if user.institutional_number != number:
                        raise IntegrityError("Número associado a outra conta")
                    user.credential_until = row["expiry"]
                    user.verified_email = row["email_validado"]
                    user.save(update_fields=["credential_until", "verified_email"])
                batch.confirmed = True
                batch.payload = ""
                batch.save(update_fields=["confirmed", "payload"])
                record(request.user, "credential", "Importou estudantes", batch.pk, total=len(rows))
                return redirect("students")
    except IntegrityError:
        messages.error(request, "A lista conflita com uma conta criada entretanto. Volte a verificar os registos.")
        rows = validate_rows(batch.payload)
    except (ValueError, csv.Error):
        messages.error(request, "O conteúdo desta importação é inválido. Carregue uma lista corrigida.")
    return render(request, "import_preview_rebuilt.html", {"batch": batch, "rows": rows,
                  "can_confirm": bool(rows) and not any(row["error"] for row in rows)})
