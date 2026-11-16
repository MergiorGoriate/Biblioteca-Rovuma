from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q, Exists, OuterRef
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.access import EDITOR, has, permission, require, student
from audit.models import record
from documents.models import Version
from reading.models import Progress
from .models import Author, Copy, Edition, Identifier, Location, Subject, Work


def allowed(user):
    return student(user) or has(user, EDITOR)


def visible(user):
    qs = Work.objects.prefetch_related("authors", "subjects", "editions")
    if not has(user, EDITOR):
        qs = qs.filter(state=Work.State.PUBLISHED)
    return qs


@require(allowed)
def home(request):
    recent = Progress.objects.filter(user=request.user).select_related("version__document__edition__work").order_by("-updated")[:6] if student(request.user) else []
    return render(request, "home.html", {"recent": recent})


@require(allowed)
def catalogue(request):
    qs = visible(request.user)
    q = request.GET.get("q", "").strip()
    kind = request.GET.get("tipo", "")
    language = request.GET.get("idioma", "")
    year = request.GET.get("ano", "")
    fmt = request.GET.get("formato", "")
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(subtitle__icontains=q) | Q(authors__name__icontains=q) |
                       Q(subjects__name__icontains=q) | Q(keywords__icontains=q) |
                       Q(editions__identifiers__value__icontains=q))
    if kind: qs = qs.filter(kind=kind)
    if language: qs = qs.filter(language=language)
    if year.isdigit(): qs = qs.filter(editions__year=int(year))
    digital = Q(editions__document__versions__state=Version.State.PUBLISHED)
    physical = Q(editions__copies__state=Copy.State.LOCAL)
    if fmt == "digital": qs = qs.filter(digital)
    if fmt == "fisico": qs = qs.filter(physical)
    if fmt == "ambos": qs = qs.filter(digital & physical)
    languages = Work.objects.filter(state=Work.State.PUBLISHED).values_list("language", flat=True).distinct()
    page = Paginator(qs.distinct().order_by("title", "pk"), 24).get_page(request.GET.get("page"))
    for work in page:
        work.digital = Version.objects.filter(document__edition__work=work, state=Version.State.PUBLISHED).exists()
        work.physical = Copy.objects.filter(edition__work=work, state=Copy.State.LOCAL).exists()
    return render(request, "catalogue.html", {"page": page, "q": q, "kind": kind, "language": language,
                   "year": year, "format": fmt, "kinds": Work.Kind.choices, "languages": languages})


@require(allowed)
def detail(request, pk):
    work = get_object_or_404(visible(request.user), pk=pk)
    versions = Version.objects.filter(document__edition__work=work, state=Version.State.PUBLISHED).select_related("document__edition")
    copies = Copy.objects.filter(edition__work=work, state=Copy.State.LOCAL).select_related("location", "edition")
    return render(request, "work.html", {"work": work, "versions": versions, "copies": copies})


@require(allowed)
def cover(request, pk):
    get_object_or_404(visible(request.user), pk=pk)
    return HttpResponse(status=404)


@require(allowed)
def library(request):
    recent = Progress.objects.filter(user=request.user).select_related("version__document__edition__work").order_by("-updated") if student(request.user) else []
    return render(request, "home.html", {"recent": recent})


@permission(EDITOR)
def collection(request):
    q = request.GET.get("q", "").strip()
    works = Work.objects.all()
    if q: works = works.filter(title__icontains=q)
    page = Paginator(works.order_by("-modified"), 30).get_page(request.GET.get("page"))
    return render(request, "collection.html", {"page": page, "q": q})


class WorkForm(forms.ModelForm):
    class Meta:
        model = Work
        fields = ("title", "subtitle", "kind", "language", "summary", "keywords", "terms", "authors", "subjects")


@permission(EDITOR)
def edit_work(request, pk=None):
    work = get_object_or_404(Work, pk=pk) if pk else None
    form = WorkForm(request.POST or None, instance=work)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        record(request.user, "collection", "Guardou obra", saved.pk)
        return redirect("manage_work", pk=saved.pk)
    return render(request, "form.html", {"form": form, "heading": "Dados da obra"})


@permission(EDITOR)
def manage_work(request, pk):
    work = get_object_or_404(Work.objects.prefetch_related("editions__copies", "editions__identifiers"), pk=pk)
    versions = Version.objects.filter(document__edition__work=work).select_related("document__edition", "job").order_by("-created")
    return render(request, "manage_work.html", {"work": work, "versions": versions})


@permission(EDITOR)
@require_POST
def work_state(request, pk):
    work = get_object_or_404(Work, pk=pk)
    action = request.POST.get("action")
    if action == "publish": work.state = Work.State.PUBLISHED
    elif action == "withdraw": work.state = Work.State.DRAFT
    elif action == "archive": work.state = Work.State.ARCHIVED
    else: raise Http404
    work.save()
    record(request.user, "collection", "Alterou estado da obra", work.pk, state=work.state)
    return redirect("manage_work", pk=pk)


@permission(EDITOR)
def locations(request):
    return render(request, "locations.html", {"locations": Location.objects.all()})


@permission(EDITOR)
def edit_related(request, kind, parent=None, pk=None):
    definitions = {"edicao": (Edition, ("label", "publisher", "year"), "work"),
                   "identificador": (Identifier, ("scheme", "value"), "edition"),
                   "exemplar": (Copy, ("inventory", "location", "state"), "edition"),
                   "localizacao": (Location, ("name", "description"), None)}
    if kind not in definitions: raise Http404
    model, fields, relation = definitions[kind]
    instance = get_object_or_404(model, pk=pk) if pk else None
    if relation and not parent and not instance: raise Http404
    Form = forms.modelform_factory(model, fields=fields)
    form = Form(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        if relation and parent: setattr(item, relation + "_id", parent)
        item.save()
        record(request.user, "collection", "Guardou registo", item.pk, kind=kind)
        return redirect("manage_work", pk=item.work_id if kind == "edicao" else item.edition.work_id) if kind != "localizacao" else redirect("locations")
    return render(request, "form.html", {"form": form, "heading": "Registo do acervo"})
