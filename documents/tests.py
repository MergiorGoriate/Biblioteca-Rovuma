import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from catalog.models import Copy, Edition, Location, Work
from documents.models import Document, Job, Licence, Version
from documents.storage import original, part
from documents.worker import main as worker_main
from reading.models import Bookmark


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LibraryTest(TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        settings_context = override_settings(PRIVATE_ROOT=Path(temp.name) / "private",
            SPOOL_ROOT=Path(temp.name) / "spool", DISK_RESERVE_BYTES=0, UPLOAD_MAX_BYTES=140 * 1024**2)
        settings_context.enable()
        self.addCleanup(settings_context.disable)
        self.student = User.objects.create_user(username="0007", institutional_number="0007", password="Test!Student",
            state=User.State.ACTIVE, credential_until=timezone.localdate() + timedelta(days=30))
        self.staff = User.objects.create_user(username="librarian", state=User.State.ACTIVE)
        self.staff.user_permissions.add(*Permission.objects.filter(codename__in=["manage_collection", "manage_credential", "view_event"]))
        self.work = Work.objects.create(title="Método científico", kind="manual", language="Português", state="published")
        self.edition = Edition.objects.create(work=self.work, label="1.ª edição", year=2026)
        self.document = Document.objects.create(edition=self.edition)
        self.version = self.version_for(document=self.document)
        self.editor = Client()
        self.editor.force_login(self.staff)

    def version_for(self, document, state="published", mode="read", format_="pdf"):
        import hashlib
        payload = (Path(__file__).resolve().parent.parent / "docs/documento-demonstracao.pdf").read_bytes()
        version = Version.objects.create(document=document, original_name="guia.pdf", file_format=format_, state=state,
            pages=3 if state == "published" else 0, sha256=hashlib.sha256(payload).hexdigest() if state == "published" else "",
            access_mode=mode, authorization="Licença de teste")
        path = original(version.pk)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        Job.objects.create(version=version, state=Job.State.DONE if state == "published" else Job.State.WAITING)
        Licence.objects.create(version=version, recorded_by=self.staff, reference=version.authorization)
        return version

    def enter(self):
        self.client.force_login(self.student)

    def url(self, name, pk=None):
        return reverse(name, args=[pk] if pk is not None else None)

    def start(self, name, size):
        response = self.editor.post(self.url("start_upload", self.edition.pk),
            {"name": name, "size": size, "mode": "read", "authorization": "Referência de teste"})
        self.assertEqual(response.status_code, 201)
        return response.json()["url"]

    def upload_chunk(self, url, data, offset):
        return self.editor.post(url, {"offset": offset, "chunk": SimpleUploadedFile("part", data)})

    def test_guest_catalogue_bytes_and_download(self):
        for name in ("catalogue", "work", "reader", "pdf", "download"):
            pk = None if name == "catalogue" else self.work.pk if name == "work" else self.version.pk
            self.assertEqual(self.client.get(self.url(name, pk), HTTP_RANGE="bytes=0-7").status_code, 302)

    def test_published_catalogue_and_all_digital_works(self):
        other = Work.objects.create(title="Outra obra", kind="book", language="Português", state="published")
        edition = Edition.objects.create(work=other, label="Única")
        version = self.version_for(Document.objects.create(edition=edition))
        self.enter()
        self.assertContains(self.client.get(self.url("catalogue")), "Outra obra")
        for pk in (self.version.pk, version.pk):
            self.assertEqual(self.client.get(self.url("reader", pk)).status_code, 200)

    def test_drafts_processing_unknown_and_raw_paths(self):
        pending = self.version_for(self.document, state="processing")
        draft = Work.objects.create(title="Rascunho", kind="book", language="Português")
        self.enter()
        self.assertEqual(self.client.get(self.url("work", draft.pk)).status_code, 404)
        for name in ("reader", "pdf", "download"):
            self.assertEqual(self.client.get(self.url(name, pending.pk)).status_code, 404)
        self.assertEqual(self.client.get(f"/media/versions/{self.version.pk}/original").status_code, 404)

    def test_profile_number_immutable(self):
        self.enter()
        self.assertContains(self.client.get(self.url("profile")), "0007")
        self.client.post(self.url("profile"), {"institutional_number": "0123"})
        self.assertEqual(self.client.post(self.url("correct", self.student.pk), {"number": "9", "reason": "teste"}).status_code, 403)
        self.student.refresh_from_db()
        self.assertEqual(self.student.institutional_number, "0007")

    def test_suspend_invalidates_open_and_reactivated_session(self):
        self.enter()
        parallel = Client()
        parallel.force_login(self.student)
        self.editor.post(self.url("credential", self.student.pk), {"action": "suspend", "reason": "Validação de teste"})
        self.assertEqual(self.client.get(self.url("pdf", self.version.pk), HTTP_RANGE="bytes=0-7").status_code, 302)
        self.editor.post(self.url("credential", self.student.pk), {"action": "resume", "reason": "Validação de teste"})
        self.assertEqual(parallel.get(self.url("catalogue")).status_code, 302)
        self.assertTrue(self.client.login(username="0007", password="Test!Student"))

    def test_download_and_byte_ranges(self):
        self.enter()
        self.assertEqual(self.client.get(self.url("download", self.version.pk)).status_code, 403)
        response = self.client.get(self.url("pdf", self.version.pk), HTTP_RANGE="bytes=0-7")
        self.assertEqual(response.status_code, 206)
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF-"))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.client.get(self.url("pdf", self.version.pk), HTTP_RANGE="bytes=600000-").status_code, 416)
        self.version.access_mode = "download"
        self.version.save()
        response = self.client.get(self.url("download", self.version.pk))
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF-"))

    def test_failed_docx_cannot_publish(self):
        version = self.version_for(self.document, state="processing", format_="docx")
        version.job.state = Job.State.ERROR
        version.job.error = "Conversão falhou"
        version.job.save()
        self.editor.post(self.url("editorial", version.pk), {"action": "publish", "checked": "yes"})
        version.refresh_from_db()
        self.assertEqual(version.state, "processing")

    def test_large_upload_above_100_mib_and_resume(self):
        size = 101 * 1024**2 + 123
        url = self.start("grande.pdf", size)
        chunk = bytes(1024**2)
        self.assertEqual(self.upload_chunk(url, chunk, 0).json()["offset"], len(chunk))
        self.assertEqual(self.upload_chunk(url, chunk, 0).status_code, 409)
        resumed = self.editor.get(url).json()["offset"]
        for offset in range(resumed, size, len(chunk)):
            response = self.upload_chunk(url, chunk[:min(size - offset, len(chunk))], offset)
            self.assertEqual(response.status_code, 200)
        self.assertTrue(self.editor.post(url, {"finish": 1}).json()["complete"])
        self.assertTrue(self.editor.post(url, {"finish": 1}).json()["complete"])
        version = Version.objects.get(original_name="grande.pdf")
        self.assertEqual(original(version.pk).stat().st_size, size)
        self.assertEqual(version.state, "processing")

    def test_background_checks_publish_and_replacement(self):
        from django.conf import settings
        url = self.start("substituicao.pdf", original(self.version.pk).stat().st_size)
        self.upload_chunk(url, original(self.version.pk).read_bytes(), 0)
        self.editor.post(url, {"finish": 1})
        pending = Version.objects.get(original_name="substituicao.pdf")
        call_command("dispatch_documents", once=True)
        from unittest.mock import patch
        with patch("sys.argv", ["worker", "--spool", str(settings.SPOOL_ROOT), "--once", "--development-no-antivirus"]):
            worker_main()
        call_command("dispatch_documents", once=True)
        pending.refresh_from_db()
        self.assertEqual(pending.state, "review")
        self.assertContains(self.editor.get(self.url("manage_work", self.work.pk)), "Pendente de revisão")
        self.editor.post(self.url("editorial", pending.pk), {"action": "publish", "checked": "yes"})
        self.version.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual((self.version.state, pending.state), ("archived", "published"))
        self.assertTrue(original(self.version.pk).exists())

    def test_import_is_idempotent_and_does_not_suspend_missing(self):
        data = b"numero,validade,email_validado\n0008,2099-01-01,teste@example.invalid\n"
        for _ in range(2):
            response = self.editor.post(self.url("imports"), {"source": "Lista validada", "file": SimpleUploadedFile("lista.csv", data)})
            self.assertEqual(response.status_code, 302)
            self.assertContains(self.editor.get(response.url), "0008")
            self.assertEqual(self.editor.post(response.url).status_code, 302)
        self.assertEqual(User.objects.filter(username="0008").count(), 1)
        self.assertFalse(User.objects.get(username="0008").has_usable_password())
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)

    def test_password_recovery_changes_existing_account(self):
        from django.core import mail
        self.student.email = "geral@example.invalid"
        self.student.verified_email = "validado@example.invalid"
        self.student.save()
        User.objects.create_user(
            username="institutional", password="Test!Institutional",
            verified_email=self.student.verified_email, identity_source=User.Identity.INSTITUTIONAL,
        )
        User.objects.create_user(username="without-password", verified_email=self.student.verified_email)
        response = self.client.post(self.url("password_reset"), {"email": self.student.email})
        self.assertRedirects(response, self.url("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)
        response = self.client.post(self.url("password_reset"), {"email": self.student.verified_email})
        self.assertRedirects(response, self.url("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.student.verified_email])
        link = next(line for line in mail.outbox[0].body.splitlines() if line.startswith("http"))
        response = self.client.get(link)
        result = self.client.post(response.url, {"new_password1": "New!Example-135", "new_password2": "New!Example-135"})
        self.assertEqual(result.status_code, 302)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password("New!Example-135"))
        self.assertEqual(User.objects.filter(username="0007").count(), 1)

    @override_settings(
        EMAIL_BACKEND="rovuma.resend_backend.ResendEmailBackend",
        DEFAULT_FROM_EMAIL="biblioteca@example.invalid",
    )
    def test_password_recovery_via_resend(self):
        self.student.verified_email = "validado@example.invalid"
        self.student.save(update_fields=["verified_email"])

        with patch.dict("os.environ", {"RESEND_API_KEY": "chave-de-ensaio"}), patch(
            "rovuma.resend_backend.urlopen"
        ) as send:
            response = self.client.post(
                self.url("password_reset"), {"email": self.student.verified_email}, secure=True,
            )
        self.assertRedirects(response, self.url("password_reset_done"))

        send.assert_called_once()
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.resend.com/emails")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer chave-de-ensaio")
        payload = json.loads(request.data)
        self.assertEqual(payload["from"], "biblioteca@example.invalid")
        self.assertEqual(payload["to"], [self.student.verified_email])
        link = next(line for line in payload["text"].splitlines() if line.startswith("https://"))

        response = self.client.get(link, secure=True)
        self.assertEqual(response.status_code, 302)
        result = self.client.post(response.url, {
            "new_password1": "New!Example-135", "new_password2": "New!Example-135",
        }, secure=True)
        self.assertRedirects(result, self.url("password_reset_complete"))
        self.assertTrue(self.client.login(username=self.student.username, password="New!Example-135"))

    def test_manual_identity_activation_is_single_use(self):
        pending = User.objects.create(username="0008", institutional_number="0008", is_active=False, state=User.State.PENDING,
            credential_until=timezone.localdate() + timedelta(days=30))
        response = self.editor.post(self.url("credential", pending.pk), {"action": "activate", "reason": "Identidade verificada"})
        self.assertEqual(response.status_code, 200)
        link = response.context["activation_link"]
        payload = {"new_password1": "First!Example-135", "new_password2": "First!Example-135"}
        self.assertEqual(self.client.post(link, payload).status_code, 302)
        self.assertEqual(self.client.post(link, payload).status_code, 404)
        self.assertTrue(self.client.login(username="0008", password="First!Example-135"))

    def test_physical_location_and_native_search(self):
        location = Location.objects.create(name="Unidade de teste", description="Sala N, Estante 3, Prateleira 2")
        Copy.objects.create(edition=self.edition, location=location, inventory="000-A")
        Copy.objects.create(edition=self.edition, location=location, inventory="000-B")
        Copy.objects.create(edition=self.edition, location=location, inventory="000-C", state=Copy.State.MAINTENANCE)
        self.enter()
        detail = self.client.get(self.url("work", self.work.pk))
        self.assertContains(detail, "2</strong> exemplares catalogados para consulta local.")
        self.assertNotContains(detail, "000-C")
        self.assertContains(self.client.get(self.url("work", self.work.pk)), "Consulta local na biblioteca")
        self.assertContains(self.client.get(self.url("work", self.work.pk)), "Estante 3")
        self.assertContains(self.client.get(self.url("catalogue"), {"q": "Método", "formato": "ambos", "ano": "2026"}), self.work.title)
        self.assertNotContains(self.client.get(self.url("catalogue"), {"ano": "2024"}), self.work.title)

    def test_technical_profile_has_no_editorial_access(self):
        technical = User.objects.create_superuser("tech", password="never-used")
        technical.user_permissions.add(Permission.objects.get(codename="view_user", content_type__app_label="accounts"))
        self.client.force_login(technical)
        self.assertEqual(self.client.get(self.url("collection")).status_code, 403)
        self.assertEqual(self.client.get(self.url("students")).status_code, 403)
        self.assertEqual(self.client.get(self.url("pdf", self.version.pk)).status_code, 403)

    def test_progress_and_bookmarks(self):
        self.enter()
        url = self.url("reading_update", self.version.pk)
        self.assertEqual(self.client.post(url, {"page": 2}).json()["page"], 2)
        self.assertTrue(self.client.post(url, {"page": 2, "action": "mark"}).json()["marked"])
        self.assertEqual(self.client.get(self.url("reader", self.version.pk)).context["page"], 2)
        self.assertEqual(Bookmark.objects.get(user=self.student).page, 2)
        self.assertFalse(self.client.post(url, {"page": 2, "action": "unmark"}).json()["marked"])

    def test_management_dashboard_and_audit_scope(self):
        from audit.models import record
        record(self.staff, "collection", "Acção editorial visível", self.work.pk)
        record(self.staff, "technical", "Acção técnica reservada", self.work.pk)
        self.assertRedirects(self.editor.get(self.url("home")), self.url("management"))
        self.assertContains(self.editor.get(self.url("management")), "Gerir estudantes")
        audit = self.editor.get(self.url("audit"))
        self.assertContains(audit, "Acção editorial visível")
        self.assertNotContains(audit, "Acção técnica reservada")
        self.enter()
        self.assertEqual(self.client.get(self.url("management")).status_code, 403)

    def test_bad_import_is_reported_before_confirmation(self):
        payload = b"numero,validade,email_validado\n0009,2027-01-01,\n0008,impossivel,\n0009,2027-01-01,\n"
        upload = self.editor.post(self.url("imports"), {
            "source": "Demonstração", "file": SimpleUploadedFile("estudantes.csv", payload),
        })
        self.assertEqual(upload.status_code, 302)
        preview = self.editor.get(upload.url)
        self.assertContains(preview, "Validade inválida")
        self.assertContains(preview, "Número repetido")
        self.assertEqual(self.editor.post(upload.url).status_code, 200)
        self.assertFalse(User.objects.filter(username__in=["0008", "0009"]).exists())

    def test_expired_and_suspended_accounts_cannot_read(self):
        self.student.credential_until = timezone.localdate() - timedelta(days=1)
        self.student.save()
        self.enter()
        self.assertEqual(self.client.get(self.url("catalogue")).status_code, 403)
        self.student.state = User.State.SUSPENDED
        self.student.save()
        result = self.client.post(self.url("login"), {"username": "0007", "password": "Test!Student"}, follow=True)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(result.status_code, 200)

    def test_login_and_recovery_throttle(self):
        from accounts.views import LocalLogin, LocalReset
        for endpoint, view, data in [
            ("login", LocalLogin, {"username": "0007", "password": "wrong"}),
            ("password_reset", LocalReset, {"email": "unknown@example.invalid"}),
        ]:
            with patch.object(view, "rate_limit", 1):
                self.assertLess(self.client.post(self.url(endpoint), data).status_code, 400)
                response = self.client.post(self.url(endpoint), data)
                self.assertContains(response, "demasiadas tentativas", status_code=429)
                self.assertEqual(response["Retry-After"], "900")

    def test_cover_is_private_and_optimized(self):
        from io import BytesIO
        from PIL import Image
        buffer = BytesIO()
        Image.new("RGB", (1000, 1800), "navy").save(buffer, "PNG")
        response = self.editor.post(self.url("edit_work", self.work.pk), {
            "title": self.work.title, "kind": self.work.kind, "language": self.work.language,
            "cover_image": SimpleUploadedFile("cover.png", buffer.getvalue(), "image/png"),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(self.url("cover", self.work.pk)).status_code, 302)
        self.enter()
        response = self.client.get(self.url("cover", self.work.pk))
        with Image.open(BytesIO(b"".join(response.streaming_content))) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertLessEqual(image.height, 840)

    def test_draft_publication_requires_reviewed_version_or_physical_copy(self):
        work = Work.objects.create(title="Obra por rever", language="Português")
        self.editor.post(self.url("work_state", work.pk), {"action": "publish"})
        work.refresh_from_db()
        self.assertEqual(work.state, Work.State.DRAFT)
        edition = Edition.objects.create(work=work, label="Edição física")
        location = Location.objects.create(name="Biblioteca", shelf="Estante C")
        Copy.objects.create(edition=edition, inventory="A-1", location=location)
        self.editor.post(self.url("work_state", work.pk), {"action": "publish"})
        work.refresh_from_db()
        self.assertEqual(work.state, Work.State.PUBLISHED)

    def test_daily_cleanup_removes_expired_partial_uploads_and_counters(self):
        from accounts.models import Attempt, ImportBatch
        from documents.models import Upload
        recent = self.start("incompleto.pdf", 10)
        stale = Upload.objects.get(pk=recent.rstrip("/").split("/")[-1])
        Upload.objects.filter(pk=stale.pk).update(updated=timezone.now() - timedelta(days=4))
        Attempt.objects.create(scope="login", address="test")
        Attempt.objects.update(updated=timezone.now() - timedelta(days=4))
        draft = ImportBatch.objects.create(operator=self.staff, source="CSV")
        ImportBatch.objects.filter(pk=draft.pk).update(created=timezone.now() - timedelta(days=4))
        call_command("clean_uploads")
        self.assertFalse(Upload.objects.filter(pk=stale.pk).exists())
        self.assertFalse(Attempt.objects.exists())
        self.assertFalse(ImportBatch.objects.filter(pk=draft.pk).exists())

    def test_dashboard_links_and_document_queue_respect_permissions(self):
        failed = self.version_for(self.document, state=Version.State.PROCESSING, format_="docx")
        failed.job.state = Job.State.ERROR
        failed.job.error = "Conversão interrompida."
        failed.job.save()
        review = self.version_for(self.document, state=Version.State.REVIEW)
        review.job.state = Job.State.DONE
        review.job.save()
        queued = self.version_for(self.document, state=Version.State.PROCESSING)
        dashboard = self.editor.get(self.url("management"))
        self.assertEqual(dashboard.context["documents"], {"revisao": 1, "processamento": 1, "falhas": 1})
        self.assertEqual(dashboard.context["students"]["active"], 1)
        response = self.editor.get(self.url("document_queue"), {"estado": "falhas", "q": self.work.title})
        self.assertContains(response, "Conversão interrompida.")
        self.assertContains(response, f'#documento-{failed.pk}')
        self.assertEqual(list(response.context["page"]), [failed])
        response = self.editor.get(self.url("document_queue"), {"estado": "revisao"})
        self.assertEqual(list(response.context["page"]), [review])
        response = self.editor.get(self.url("document_queue"), {"estado": "processamento"})
        self.assertEqual(list(response.context["page"]), [queued])
        self.assertEqual(self.client.get(self.url("document_queue")).status_code, 302)
        self.enter()
        self.assertEqual(self.client.get(self.url("document_queue")).status_code, 403)
        credentials_only = User.objects.create_user(username="gestor-contas")
        credentials_only.user_permissions.add(Permission.objects.get(codename="manage_credential"))
        self.client.force_login(credentials_only)
        dashboard = self.client.get(self.url("management"))
        self.assertContains(dashboard, "Gerir estudantes")
        self.assertNotContains(dashboard, "Falhas de processamento")
        self.assertNotContains(dashboard, "Gerir acervo")
        self.assertEqual(self.client.get(self.url("document_queue")).status_code, 403)

    def test_dashboard_filters_match_lists(self):
        self.student.credential_until = timezone.localdate() - timedelta(days=1)
        self.student.save()
        pending = User.objects.create(username="0009", institutional_number="0009",
                                      is_active=False, state=User.State.PENDING)
        dashboard = self.editor.get(self.url("management"))
        self.assertEqual(dashboard.context["students"], {"active": 0, "pending": 1, "expired": 1, "suspended": 0})
        response = self.editor.get(self.url("students"), {"estado": "expired"})
        self.assertEqual(list(response.context["page"]), [self.student])
        self.assertContains(response, "Sem credenciamento válido")
        response = self.editor.get(self.url("students"), {"estado": "pending"})
        self.assertEqual(list(response.context["page"]), [pending])
        draft = Work.objects.create(title="Obra em preparação", language="Português")
        response = self.editor.get(self.url("collection"), {"estado": "draft"})
        self.assertEqual(list(response.context["page"]), [draft])

    def test_portal_and_management_have_distinct_navigation_and_permissions(self):
        from django.contrib.auth import SESSION_KEY
        draft = Work.objects.create(title="Rascunho exclusivo da gestão", language="Português")
        self.assertRedirects(self.client.get(self.url("management")), self.url("management_login") + "?next=/admin/")
        self.assertContains(self.client.get(self.url("management_login")), "Entre com a sua conta de bibliotecário")
        self.assertEqual(self.client.post(self.url("management_login"), {"username": "0007", "password": "Test!Student"}).status_code, 200)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.enter()
        portal = self.client.get(self.url("portal"))
        self.assertContains(portal, "Portal da biblioteca")
        self.assertNotContains(portal, "Painel administrativo")
        self.assertEqual(self.client.get(self.url("management")).status_code, 403)
        self.assertEqual(self.client.get(self.url("management_password")).status_code, 403)
        self.assertContains(self.editor.get(self.url("portal")), "Painel administrativo")
        self.assertNotContains(self.editor.get(self.url("catalogue")), draft.title)
        self.assertEqual(self.editor.get(self.url("work", draft.pk)).status_code, 404)
        self.assertContains(self.editor.get(self.url("collection")), draft.title)
        management = self.editor.get(self.url("management"))
        self.assertContains(management, "Navegação administrativa")
        self.assertNotContains(management, "Minhas leituras")
        preview = self.editor.get(self.url("reader_preview", self.version.pk))
        self.assertContains(preview, "Navegação administrativa")
        self.assertContains(preview, "Gestão da obra")
        self.assertEqual(self.client.get(self.url("reader_preview", self.version.pk)).status_code, 403)
        self.staff.set_password("Staff test password 927!")
        self.staff.save()
        result = Client().post(self.url("management_login"), {"username": self.staff.username, "password": "Staff test password 927!"})
        self.assertEqual(result.url, self.url("management"))

    def test_legacy_management_redirect_preserves_route_query_and_method(self):
        for previous, target in [
            ("/gestao", "/admin/"),
            ("/gestao/entrar/?next=%2Fgestao%2F", "/admin/entrar/?next=%2Fgestao%2F"),
            ("/gestao/obras/?estado=draft&page=2", "/admin/obras/?estado=draft&page=2"),
        ]:
            response = self.client.get(previous)
            self.assertEqual(response.status_code, 308)
            self.assertEqual(response.url, target)

        result = self.editor.post(f"/gestao/obras/{self.work.pk}/estado/", {"action": "archive"}, follow=True)
        self.assertEqual(result.redirect_chain[0], (self.url("work_state", self.work.pk), 308))
        self.work.refresh_from_db()
        self.assertEqual(self.work.state, Work.State.ARCHIVED)

    def test_physical_inventory_uses_existing_editor_permissions(self):
        location = Location.objects.create(name="Depósito", room="Sala A")
        copy = Copy.objects.create(edition=self.edition, location=location, inventory="DEPOSITO-18")
        Copy.objects.create(edition=self.edition, location=location, inventory="DEPOSITO-19",
                            state=Copy.State.MAINTENANCE)
        route = self.url("inventory")

        self.assertRedirects(self.client.get(route), self.url("management_login") + "?next=/admin/exemplares/")
        self.enter()
        self.assertEqual(self.client.get(route).status_code, 403)
        result = self.editor.get(route, {"q": "Sala", "estado": Copy.State.LOCAL})
        self.assertEqual(list(result.context["page"]), [copy])
        result = self.editor.get(route, {"q": "Depósito", "estado": Copy.State.LOCAL})
        self.assertEqual(list(result.context["page"]), [copy])
        self.assertContains(result, "Sala A")
        self.assertContains(result, reverse("edit_related", args=["exemplar", self.edition.pk, copy.pk]))
        self.assertContains(result, "Importar estudantes")
        self.assertRedirects(self.editor.get(self.url("management_login")), self.url("management"))
        self.assertRedirects(self.editor.get(self.url("management_login"), {"next": self.url("management_login")}),
                             self.url("management"))
