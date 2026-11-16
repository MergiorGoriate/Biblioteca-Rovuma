from datetime import timedelta
from hashlib import sha256
from ipaddress import ip_address

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Attempt


def admit(request, scope, limit):
    address = request.META.get("REMOTE_ADDR", "")
    if settings.TRUST_ROVUMA_PROXY:
        address = request.META.get("HTTP_X_ROVUMA_CLIENT", address)
    try:
        address = str(ip_address(address))
    except ValueError:
        address = "unknown"
    key = sha256(f"{settings.SECRET_KEY}:{address}".encode()).hexdigest()
    cutoff = timezone.now() - timedelta(minutes=15)

    with transaction.atomic():
        counters = Attempt.objects.select_for_update()
        attempt, _ = counters.get_or_create(scope=scope, address=key)
        if attempt.updated < cutoff:
            attempt.count = 0
        if attempt.count >= limit:
            return False
        attempt.count += 1
        attempt.save(update_fields=["count", "updated"])
    return True
