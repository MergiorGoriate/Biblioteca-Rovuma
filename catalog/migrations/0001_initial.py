from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(name="Author", fields=[("id", models.BigAutoField(primary_key=True, serialize=False)), ("name", models.CharField(max_length=200, unique=True))]),
        migrations.CreateModel(name="Subject", fields=[("id", models.BigAutoField(primary_key=True, serialize=False)), ("name", models.CharField(max_length=150, unique=True))]),
        migrations.CreateModel(name="Location", fields=[("id", models.BigAutoField(primary_key=True, serialize=False)), ("name", models.CharField(max_length=200, unique=True)), ("description", models.TextField(blank=True))]),
        migrations.CreateModel(name="Work", fields=[
            ("id", models.BigAutoField(primary_key=True, serialize=False)),
            ("title", models.CharField(max_length=300)),
            ("subtitle", models.CharField(max_length=300, blank=True)),
            ("kind", models.CharField(max_length=20, choices=[("book","Livro"),("manual","Manual"),("thesis","Trabalho académico"),("article","Artigo"),("other","Outro")], default="book")),
            ("language", models.CharField(max_length=80)),
            ("summary", models.TextField(blank=True)),
            ("keywords", models.TextField(blank=True)),
            ("terms", models.TextField(blank=True)),
            ("state", models.CharField(max_length=12, choices=[("draft","Rascunho"),("published","Publicada"),("archived","Arquivada")], default="draft", db_index=True)),
            ("modified", models.DateTimeField(auto_now=True)),
            ("authors", models.ManyToManyField(to="catalog.author", blank=True)),
            ("subjects", models.ManyToManyField(to="catalog.subject", blank=True)),
        ], options={"permissions": (("manage_collection","Gerir acervo"),)}),
        migrations.CreateModel(name="Edition", fields=[("id", models.BigAutoField(primary_key=True, serialize=False)),("label",models.CharField(max_length=150)),("publisher",models.CharField(max_length=200,blank=True)),("year",models.PositiveIntegerField(null=True,blank=True)),("work",models.ForeignKey(to="catalog.work",on_delete=django.db.models.deletion.PROTECT,related_name="editions"))]),
        migrations.CreateModel(name="Identifier", fields=[("id",models.BigAutoField(primary_key=True,serialize=False)),("scheme",models.CharField(max_length=30)),("value",models.CharField(max_length=150)),("edition",models.ForeignKey(to="catalog.edition",on_delete=django.db.models.deletion.CASCADE,related_name="identifiers"))],options={"constraints":[models.UniqueConstraint(fields=("scheme","value"),name="unique_bibliographic_identifier")]}),
        migrations.CreateModel(name="Copy", fields=[("id",models.BigAutoField(primary_key=True,serialize=False)),("inventory",models.CharField(max_length=100,unique=True)),("state",models.CharField(max_length=16,choices=[("local","Consulta local"),("unavailable","Indisponível"),("removed","Retirado")],default="local")),("edition",models.ForeignKey(to="catalog.edition",on_delete=django.db.models.deletion.PROTECT,related_name="copies")),("location",models.ForeignKey(to="catalog.location",on_delete=django.db.models.deletion.PROTECT))]),
    ]
