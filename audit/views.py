from django.core.paginator import Paginator
from django.shortcuts import render

from accounts.access import EDITOR, has, permission
from .models import Event


def visible_events(user):
    areas = []
    if has(user, EDITOR):
        areas.append("collection")
    if has(user, "accounts.manage_credential") or has(user, "accounts.correct_number"):
        areas.append("credential")
    return Event.objects.filter(area__in=areas).select_related("actor").order_by("-created", "-pk")


@permission("audit.view_event")
def events(request):
    events = visible_events(request.user)
    return render(request, "audit.html", {"page": Paginator(events, 50).get_page(request.GET.get("page"))})
