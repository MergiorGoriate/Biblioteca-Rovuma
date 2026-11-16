from io import BytesIO
import os
from tempfile import mkstemp

from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.db import IntegrityError, transaction
from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Exists, OuterRef
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.access import EDITOR, has, permission, require, student
from audit.models import record
from documents.models import Version
from reading.models import Bookmark, Progress
from .models import Author, Copy, Edition, Identifier, Location, Subject, Work


def allowed(user):
    return student(user) or has(user, EDITOR)


def visible(user):
    qs = Work.objects.prefetch_related("authors", "subjects", "editions__identifiers")
    if not has(user, EDITOR):
        qs = qs.filter(state=Work.State.PUBLISHED)
    return qs


def available_readings(model, user):
    return model.objects.filter(user=user, version__state=Version.State.PUBLISHED,
        version__document__edition__work__state=Work.State.PUBLISHED
    ).select_related("version__document__edition__work")


@require(lambda user: user.is_authenticated)
def home(request):
    if not student(request.user):
        return render(request, "staff_home.html")
    recent = available_readings(Progress, request.user).order_by("-updated")[:6]
    return render(request, "home.html", {"recent": recent})


@require(lambda user: any(has(user, code) for code in (
    EDITOR, "accounts.manage_credential", "accounts.correct_number", "audit.view_event"
)))
def management(request):
    return render(request, "staff_home.html")


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
    if len(year) <= 4 and year.isascii() and year.isdigit():
        qs = qs.filter(editions__year=int(year))
    qs = qs.annotate(
        digital=Exists(Version.objects.filter(document__edition__work=OuterRef("pk"), state=Version.State.PUBLISHED)),
        physical=Exists(Copy.objects.filter(edition__work=OuterRef("pk"), state=Copy.State.LOCAL)),
    )
    if fmt in {"digital", "ambos"}:
        qs = qs.filter(digital=True)
    if fmt in {"fisico", "ambos"}:
        qs = qs.filter(physical=True)
    languages = Work.objects.filter(state=Work.State.PUBLISHED).values_list("language", flat=True).distinct()
    page = Paginator(qs.distinct().order_by("title", "pk"), 24).get_page(request.GET.get("page"))
    return render(request, "catalogue.html", {"page": page, "q": q, "kind": kind, "language": language,
                   "year": year, "format": fmt, "kinds": Work.Kind.choices, "languages": languages})


@require(allowed)
def detail(request, pk):
    work = get_object_or_404(visible(request.user), pk=pk)
    versions = Version.objects.filter(document__edition__work=work, state=Version.State.PUBLISHED).select_related("document__edition")
    copies = Copy.objects.filter(edition__work=work, state=Copy.State.LOCAL).select_related("location", "edition")
    return render(request, "work.html", {"work": work, "versions": versions, "copies": copies})


def cover_path(pk):
    return settings.PRIVATE_ROOT / "covers" / f"{pk}.webp"


@require(allowed)
def cover(request, pk):
    work = get_object_or_404(visible(request.user), pk=pk)
    path = cover_path(work.pk)
    try:
        image = path.open("rb")
    except FileNotFoundError:
        from django.templatetags.static import static
        return redirect(static("cover-default.svg"))
    response = FileResponse(image, content_type="image/webp")
    response["Cache-Control"] = "private, no-store"
    return response


@require(student)
def library(request):
    recent = available_readings(Progress, request.user).order_by("-updated")[:50]
    bookmarks = available_readings(Bookmark, request.user).order_by("-created")[:100]
    return render(request, "library.html", {"recent": recent, "bookmarks": bookmarks})


@permission(EDITOR)
def collection(request):
    q = request.GET.get("q", "").strip()
    works = Work.objects.all()
    if q: works = works.filter(title__icontains=q)
    page = Paginator(works.order_by("-modified"), 30).get_page(request.GET.get("page"))
    return render(request, "collection.html", {"page": page, "q": q})


class WorkForm(forms.ModelForm):
    cover_image = forms.FileField(label="Capa (JPEG, PNG ou WebP)", required=False)

    def clean_cover_image(self):
        uploaded = self.cleaned_data["cover_image"]
        if not uploaded:
            return None
        if uploaded.size > 5 * 1024**2:
            raise forms.ValidationError("A capa pode ter até 5 MiB.")
        try:
            with Image.open(uploaded, formats=("JPEG", "PNG", "WEBP")) as image:
                if image.width * image.height > 16_000_000:
                    raise forms.ValidationError("A imagem excede o limite de 16 megapíxeis.")
                image.thumbnail((600, 840))
                target = BytesIO()
                image.convert("RGB").save(target, "WEBP", quality=82)
                return target.getvalue()
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
            raise forms.ValidationError("Escolha uma imagem JPEG, PNG ou WebP válida.")

    class Meta:
        model = Work
        fields = ("title", "subtitle", "kind", "language", "summary", "keywords", "terms", "authors", "subjects")


@permission(EDITOR)
def edit_work(request, pk=None):
    work = get_object_or_404(Work, pk=pk) if pk else None
    form = WorkForm(request.POST or None, request.FILES or None, instance=work)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        if form.cleaned_data["cover_image"]:
            path = cover_path(saved.pk)
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = mkstemp(dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as target:
                    target.write(form.cleaned_data["cover_image"])
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
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
    states = {"publish": Work.State.PUBLISHED, "withdraw": Work.State.DRAFT, "archive": Work.State.ARCHIVED}
    action = request.POST.get("action")
    if action not in states:
        raise Http404
    with transaction.atomic():
        work = get_object_or_404(Work.objects.select_for_update(), pk=pk)
        if action == "publish" and not (
            Copy.objects.filter(edition__work=work, state=Copy.State.LOCAL).exists()
            or Version.objects.filter(document__edition__work=work, state=Version.State.PUBLISHED).exists()
        ):
            messages.error(request, "Registe um exemplar para consulta local ou publique uma versão digital revista.")
        else:
            work.state = states[action]
            work.save(update_fields=["state", "modified"])
            record(request.user, "collection", "Alterou estado da obra", work.pk, state=work.state)
    return redirect("manage_work", pk=pk)


@permission(EDITOR)
def locations(request):
    return render(request, "locations.html", {"locations": Location.objects.all(),
                  "authors": Author.objects.order_by("name"), "subjects": Subject.objects.order_by("name")})


@permission(EDITOR)
def edit_related(request, kind, parent=None, pk=None):
    definitions = {
        "edicao": (Edition, ("label", "publisher", "year"), "work", Work),
        "identificador": (Identifier, ("scheme", "value"), "edition", Edition),
        "exemplar": (Copy, ("inventory", "location", "state", "condition"), "edition", Edition),
        "localizacao": (Location, ("name", "unit", "room", "shelf", "level", "description"), None, None),
        "autor": (Author, ("name",), None, None),
        "assunto": (Subject, ("name",), None, None),
    }
    if kind not in definitions:
        raise Http404
    model, fields, relation, parent_model = definitions[kind]
    qs = model.objects.all()
    if relation:
        get_object_or_404(parent_model, pk=parent)
        qs = qs.filter(**{relation + "_id": parent})
    instance = get_object_or_404(qs, pk=pk) if pk else model()
    if relation and not pk:
        setattr(instance, relation + "_id", parent)
    Form = forms.modelform_factory(model, fields=fields)
    form = Form(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                item = form.save()
                record(request.user, "collection", "Guardou registo", item.pk, kind=kind)
            if kind == "edicao":
                return redirect("manage_work", pk=item.work_id)
            if relation:
                return redirect("manage_work", pk=item.edition.work_id)
            return redirect("locations")
        except IntegrityError:
            form.add_error(None, "Já existe um registo com esses dados.")
    return render(request, "form.html", {"form": form, "heading": "Registo do acervo"})
