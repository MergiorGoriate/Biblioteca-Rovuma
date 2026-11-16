from django.db import models


class Author(models.Model):
    name = models.CharField(max_length=200, unique=True)
    def __str__(self): return self.name


class Subject(models.Model):
    name = models.CharField(max_length=150, unique=True)
    def __str__(self): return self.name


class Work(models.Model):
    class State(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        PUBLISHED = "published", "Publicada"
        ARCHIVED = "archived", "Arquivada"

    class Kind(models.TextChoices):
        BOOK = "book", "Livro"
        MANUAL = "manual", "Manual"
        THESIS = "thesis", "Trabalho académico"
        ARTICLE = "article", "Artigo"
        OTHER = "other", "Outro"

    title = models.CharField(max_length=300)
    subtitle = models.CharField(max_length=300, blank=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.BOOK)
    language = models.CharField(max_length=80)
    summary = models.TextField(blank=True)
    keywords = models.TextField(blank=True)
    terms = models.TextField(blank=True)
    state = models.CharField(max_length=12, choices=State.choices, default=State.DRAFT, db_index=True)
    authors = models.ManyToManyField(Author, blank=True)
    subjects = models.ManyToManyField(Subject, blank=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        permissions = (("manage_collection", "Gerir acervo"),)
    def __str__(self): return self.title


class Edition(models.Model):
    work = models.ForeignKey(Work, related_name="editions", on_delete=models.PROTECT)
    label = models.CharField(max_length=150)
    publisher = models.CharField(max_length=200, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    def __str__(self): return f"{self.work}: {self.label}"


class Identifier(models.Model):
    edition = models.ForeignKey(Edition, related_name="identifiers", on_delete=models.CASCADE)
    scheme = models.CharField(max_length=30)
    value = models.CharField(max_length=150)
    class Meta:
        constraints = [models.UniqueConstraint(fields=("scheme", "value"), name="unique_bibliographic_identifier")]


class Location(models.Model):
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    def __str__(self): return self.name


class Copy(models.Model):
    class State(models.TextChoices):
        LOCAL = "local", "Consulta local"
        UNAVAILABLE = "unavailable", "Indisponível"
        REMOVED = "removed", "Retirado"
    edition = models.ForeignKey(Edition, related_name="copies", on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    inventory = models.CharField(max_length=100, unique=True)
    state = models.CharField(max_length=16, choices=State.choices, default=State.LOCAL)
