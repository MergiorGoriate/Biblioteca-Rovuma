from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.contrib.auth.models
import django.contrib.auth.validators
import django.utils.timezone

class Migration(migrations.Migration):
    initial = True
    dependencies = [("auth", "0012_alter_user_first_name_max_length")]
    operations = [
        migrations.CreateModel(name="User", fields=[
            ("id", models.BigAutoField(primary_key=True, serialize=False)),
            ("password", models.CharField(max_length=128, verbose_name="password")),
            ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
            ("is_superuser", models.BooleanField(default=False, help_text="Designates that this user has all permissions without explicitly assigning them.", verbose_name="superuser status")),
            ("username", models.CharField(max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name="username")),
            ("first_name", models.CharField(max_length=150, blank=True, verbose_name="first name")),
            ("last_name", models.CharField(max_length=150, blank=True, verbose_name="last name")),
            ("email", models.EmailField(max_length=254, blank=True, verbose_name="email address")),
            ("is_staff", models.BooleanField(default=False, verbose_name="staff status")),
            ("is_active", models.BooleanField(default=True, verbose_name="active")),
            ("date_joined", models.DateTimeField(default=django.utils.timezone.now, verbose_name="date joined")),
            ("institutional_number", models.CharField(max_length=64, unique=True, null=True, blank=True)),
            ("credential_until", models.DateField(null=True, blank=True)),
            ("verified_email", models.EmailField(blank=True, max_length=254)),
            ("state", models.CharField(max_length=12, choices=[("pending","Pendente"),("active","Activa"),("suspended","Suspensa")], default="active")),
            ("identity_source", models.CharField(max_length=16, choices=[("local","Biblioteca"),("institutional","Institucional")], default="local")),
            ("identity_subject", models.CharField(max_length=255, blank=True)),
            ("session_version", models.PositiveIntegerField(default=0)),
            ("activation_token_hash", models.CharField(max_length=64, blank=True)),
            ("activation_expires", models.DateTimeField(null=True, blank=True)),
            ("groups", models.ManyToManyField(blank=True, related_name="user_set", related_query_name="user", to="auth.group", verbose_name="groups")),
            ("user_permissions", models.ManyToManyField(blank=True, related_name="user_set", related_query_name="user", to="auth.permission", verbose_name="user permissions")),
        ], options={"permissions": (("manage_credential","Gerir credenciamento"),("correct_number","Corrigir número institucional"))}, managers=[("objects", django.contrib.auth.models.UserManager())]),
        migrations.CreateModel(name="Attempt",fields=[("id",models.BigAutoField(primary_key=True,serialize=False)),("scope",models.CharField(max_length=64)),("address",models.CharField(max_length=100)),("count",models.PositiveIntegerField(default=0)),("updated",models.DateTimeField(auto_now=True))],options={"constraints":[models.UniqueConstraint(fields=("scope","address"),name="unique_attempt_scope")]}),
        migrations.CreateModel(name="ImportBatch",fields=[("id",models.BigAutoField(primary_key=True,serialize=False)),("source",models.CharField(max_length=255)),("payload",models.TextField(blank=True)),("confirmed",models.BooleanField(default=False)),("created",models.DateTimeField(auto_now_add=True)),("operator",models.ForeignKey(to=settings.AUTH_USER_MODEL,on_delete=django.db.models.deletion.PROTECT))]),
    ]
