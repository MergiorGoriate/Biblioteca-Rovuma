from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from accounts.access import require, student
from documents.views import read_permission, version_for
from .models import Bookmark, Progress


@require(read_permission)
def reader(request, pk):
    version = version_for(request.user, pk)
    personal = student(request.user) and version.state == version.State.PUBLISHED
    progress = Progress.objects.filter(user=request.user, version=version).first() if personal else None
    try:
        page = max(1, min(version.pages, int(request.GET.get("pagina", progress.page if progress else 1))))
    except ValueError:
        page = 1
    return render(request, "reader.html", {"version": version, "work": version.document.edition.work,
                                           "page": page, "personal": personal})


@require(student)
@require_POST
def update(request, pk):
    version = version_for(request.user, pk)
    if version.state != version.State.PUBLISHED or version.document.edition.work.state != "published":
        return JsonResponse({"error": "Versão indisponível."}, status=404)
    try:
        page = int(request.POST.get("page", "0"))
    except ValueError:
        page = 0
    if not 1 <= page <= version.pages:
        return JsonResponse({"error": "Página inválida."}, status=400)
    action = request.POST.get("action", "progress")
    if action == "mark":
        Bookmark.objects.get_or_create(user=request.user, version=version, page=page)
    elif action == "unmark":
        Bookmark.objects.filter(user=request.user, version=version, page=page).delete()
    elif action == "progress":
        Progress.objects.update_or_create(user=request.user, version=version, defaults={"page": page})
    else:
        return JsonResponse({"error": "Acção inválida."}, status=400)
    return JsonResponse({"page": page, "marked": Bookmark.objects.filter(user=request.user, version=version, page=page).exists()})
