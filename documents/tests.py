from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

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
        self.student.verified_email = "validado@example.invalid"
        self.student.save()
        self.client.post(self.url("password_reset"), {"email": self.student.verified_email})
        link = next(line for line in mail.outbox[0].body.splitlines() if line.startswith("http"))
        response = self.client.get(link)
        result = self.client.post(response.url, {"new_password1": "New!Example-135", "new_password2": "New!Example-135"})
        self.assertEqual(result.status_code, 302)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password("New!Example-135"))
        self.assertEqual(User.objects.filter(username="0007").count(), 1)

    def test_manual_identity_activation_is_single_use(self):
        pending = User.objects.create(username="0008", institutional_number="0008", is_active=False,
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
        self.enter()
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
