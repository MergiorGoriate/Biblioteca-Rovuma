from django.contrib.auth import logout
from django.shortcuts import redirect


class SessionVersion:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated:
            if not user.is_active or request.session.get("account_version", user.session_version) != user.session_version:
                logout(request)
                return redirect("login")
            request.session.setdefault("account_version", user.session_version)
        return self.get_response(request)
