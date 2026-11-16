from django.core.paginator import Paginator
from django.shortcuts import render

from accounts.access import EDITOR, has, permission
from .models import Event


@permission("audit.view_event")
def events(request):
    areas = []
    if has(request.user, EDITOR):
        areas.append("collection")
    if has(request.user, "accounts.manage_credential") or has(request.user, "accounts.correct_number"):
        areas.append("credential")
    events = Event.objects.filter(area__in=areas).select_related("actor").order_by("-created", "-pk")
    return render(request, "audit.html", {"page": Paginator(events, 50).get_page(request.GET.get("page"))})
