from django.shortcuts import render
from accounts.access import permission
from .models import Event


@permission("audit.view_event")
def events(request):
    return render(request, "audit.html", {"events": Event.objects.select_related("actor")[:200]})
