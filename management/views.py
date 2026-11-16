from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from accounts.access import EDITOR, can_manage, has, permission, require
from accounts.models import User
from audit.views import visible_events
from catalog.models import Copy, Work
from documents.models import Job, Version


DOCUMENT_FILTERS = {
    "revisao": ("Pendentes de revisão", Q(state=Version.State.REVIEW, job__state=Job.State.DONE)),
    "processamento": ("Em processamento", Q(job__state__in=(Job.State.WAITING, Job.State.SENT))),
    "falhas": ("Falhas de processamento", Q(job__state=Job.State.ERROR)),
}


@require(can_manage, login_url="management_login")
@never_cache
def dashboard(request):
    context = {}
    if has(request.user, EDITOR):
        context["works"] = Work.objects.aggregate(
            published=Count("pk", filter=Q(state=Work.State.PUBLISHED)),
            draft=Count("pk", filter=Q(state=Work.State.DRAFT)),
        )
        context["local_copies"] = Copy.objects.filter(state=Copy.State.LOCAL).count()
        context["documents"] = Version.objects.aggregate(**{
            key: Count("pk", filter=condition) for key, (_, condition) in DOCUMENT_FILTERS.items()
        })
        context["recent_works"] = Work.objects.order_by("-modified", "-pk")[:5]
    if has(request.user, "accounts.manage_credential"):
        active = Q(state=User.State.ACTIVE, is_active=True)
        valid = Q(credential_until__gte=timezone.localdate())
        context["students"] = User.objects.filter(institutional_number__isnull=False).aggregate(
            active=Count("pk", filter=active & valid),
            pending=Count("pk", filter=Q(state=User.State.PENDING)),
            expired=Count("pk", filter=active & ~valid),
            suspended=Count("pk", filter=Q(state=User.State.SUSPENDED)),
        )
    if has(request.user, "audit.view_event"):
        context["recent_events"] = visible_events(request.user)[:6]
    return render(request, "management/dashboard.html", context)


@permission(EDITOR)
@never_cache
def document_queue(request):
    state = request.GET.get("estado", "")
    versions = Version.objects.select_related("document__edition__work", "job")
    if state in DOCUMENT_FILTERS:
        versions = versions.filter(DOCUMENT_FILTERS[state][1])
    else:
        state = ""
        versions = versions.filter(DOCUMENT_FILTERS["revisao"][1] | DOCUMENT_FILTERS["processamento"][1] | DOCUMENT_FILTERS["falhas"][1])
    q = request.GET.get("q", "").strip()[:150]
    if q:
        versions = versions.filter(
            Q(original_name__icontains=q) | Q(document__edition__work__title__icontains=q),
        )
    page = Paginator(versions.order_by("-job__changed", "-pk"), 24).get_page(request.GET.get("page"))
    labels = {key: label for key, (label, _) in DOCUMENT_FILTERS.items()}
    return render(request, "management/documents.html", {"page": page, "labels": labels, "state": state, "q": q})
