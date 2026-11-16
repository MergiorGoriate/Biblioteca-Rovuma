from contextlib import closing
from hashlib import sha256
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import TestCase
from unittest.mock import patch

from .remote_processor import ProcessorServer, process


class PrivateTransportTests(TestCase):
    def test_authorization_and_docx_round_trip(self):
        key = "temporary-local-test-key-" * 2
        payload = b"Conteudo de ensaio"
        converted = b"%PDF-1.7"
        with ProcessorServer(("::1", 0), key) as server, TemporaryDirectory() as root:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port, *_ = server.server_address
                def worker(folder, required):
                    self.assertTrue(required)
                    self.assertEqual((folder / "original").read_bytes(), payload)
                    (folder / "reader.pdf").write_bytes(converted)
                    return {"pages": 3, "sha256": sha256(payload).hexdigest()}

                with closing(HTTPConnection(host, port, timeout=5)) as connection:
                    connection.request("POST", "/process", b"", {"X-Document-Format": "docx"})
                    self.assertEqual(connection.getresponse().status, 401)

                source = Path(root) / "original"
                target = Path(root) / "reader.pdf"
                source.write_bytes(payload)
                with patch("documents.remote_processor.signatures_ready", return_value=True), \
                     patch("documents.remote_processor.run_one", side_effect=worker), \
                     patch("documents.remote_processor.http.client.HTTPConnection",
                           side_effect=lambda name, port, timeout: HTTPConnection(host, port, timeout=5)):
                    result = process(f"http://processador.railway.internal:{port}", key, source, "docx", target)
                self.assertEqual(result["pages"], 3)
                self.assertEqual(target.read_bytes(), converted)
            finally:
                server.shutdown()
                thread.join()
