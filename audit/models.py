from django.conf import settings
from django.db import models


class Event(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    area = models.CharField(max_length=40)
    action = models.CharField(max_length=255)
    reference = models.CharField(max_length=100)
    details = models.JSONField(default=dict, blank=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created",)


def record(actor, area, action, reference, **details):
    return Event.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        area=area, action=action, reference=str(reference), details=details,
    )
