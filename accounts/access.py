from functools import wraps
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.utils import timezone

EDITOR = "catalog.manage_collection"


def has(user, permission):
    return bool(user.is_authenticated and user.is_active and (user.is_superuser or user.has_perm(permission)))


def student(user):
    return bool(user.is_authenticated and user.is_active
                and user.institutional_number and user.credential_until
                and user.credential_until >= timezone.localdate())


def require(predicate):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated or not request.user.is_active:
                return redirect_to_login(request.get_full_path())
            if not predicate(request.user):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorate


def permission(code):
    return require(lambda user: has(user, code))


def navigation(request):
    user = request.user
    return {"nav_editor": has(user, EDITOR),
            "nav_credential": has(user, "accounts.manage_credential"),
            "nav_correct": has(user, "accounts.correct_number"),
            "nav_audit": has(user, "audit.view_event")}
