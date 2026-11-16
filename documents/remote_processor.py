"""Private HTTP transport for one quarantined document at a time."""

import hashlib
import hmac
import http.client
import json
import os
import shutil
import socket
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore
from time import time
from urllib.parse import urlsplit

from .formats import CONVERTED_FORMATS, SUPPORTED_FORMATS
from .worker import run_one


MAX_BYTES = 1024**3
CHUNK_BYTES = 64 * 1024


class Unavailable(Exception):
    pass


def transfer(source, target, size):
    if not 0 <= size <= MAX_BYTES:
        raise ValueError("Tamanho inesperado.")
    while size:
        block = source.read(min(CHUNK_BYTES, size))
        if not block:
            raise ValueError("Transferência incompleta.")
        target.write(block)
        size -= len(block)


def process(url, token, source, file_format, target):
    parsed = urlsplit(url)
    if (parsed.scheme != "http" or not parsed.hostname or not parsed.hostname.endswith(".railway.internal")
            or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or len(token) < 32):
        raise ValueError("Configuração do processador inválida.")
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 8080, timeout=850)
    try:
        with source.open("rb") as stream:
            conn.request("POST", "/process", stream, {
                "Authorization": f"Bearer {token}",
                "Content-Length": str(source.stat().st_size),
                "X-Document-Format": file_format,
            })
            response = conn.getresponse()
            if response.status in {429, 503}:
                raise Unavailable
            if response.status == 422:
                error = json.loads(response.read(4096))["error"]
                if not isinstance(error, str) or not error:
                    raise ValueError("Resultado inesperado.")
                return {"error": error[:300]}
            if response.status != 200:
                raise ValueError("O processador recusou o pedido.")
            pages = int(response.getheader("X-PDF-Pages", "0"))
            digest = response.getheader("X-Original-SHA256", "")
            with source.open("rb") as stream:
                if not hmac.compare_digest(digest, hashlib.file_digest(stream, "sha256").hexdigest()):
                    raise ValueError("O ficheiro original não corresponde ao resultado.")
            if not 1 <= pages <= 1_000_000:
                raise ValueError("Número de páginas inválido.")
            size = int(response.getheader("Content-Length"))
            if file_format in CONVERTED_FORMATS:
                if not 0 < size <= MAX_BYTES or shutil.disk_usage(target.parent).free < size:
                    raise ValueError("O PDF convertido excede o espaço disponível.")
                with target.open("wb") as output:
                    transfer(response, output, size)
            elif size != 0:
                raise ValueError("O processador devolveu um ficheiro inesperado.")
            return {"sha256": digest, "pages": pages}
    except (OSError, http.client.HTTPException) as exc:
        raise Unavailable from exc
    finally:
        conn.close()


def signatures_ready():
    return any(time() - path.stat().st_mtime < 14 * 86400
               for path in Path("/var/lib/clamav").glob("daily.c[vl]d"))


class ProcessorServer(ThreadingHTTPServer):
    daemon_threads = True
    address_family = socket.AF_INET6

    def __init__(self, address, token):
        if len(token) < 32:
            raise ValueError("Defina uma chave privada para o processador.")
        self.authorization = f"Bearer {token}"
        self.slot = BoundedSemaphore()
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(90)

    def log_message(self, *args):
        pass

    def reply(self, status, body=b"", **headers):
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.close_connection = True
        for name, value in headers.items():
            self.send_header(name, str(value))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        if self.path != "/health":
            self.reply(404)
        elif not signatures_ready():
            self.reply(503)
        else:
            self.reply(200, b"ok")

    def do_POST(self):
        if self.path != "/process":
            self.reply(404)
            return
        presented = self.headers.get("Authorization", "").encode("utf-8")
        if not hmac.compare_digest(presented, self.server.authorization.encode("utf-8")):
            self.reply(401)
            return
        file_format = self.headers.get("X-Document-Format")
        try:
            size = int(self.headers.get("Content-Length", ""))
        except ValueError:
            size = 0
        if file_format not in SUPPORTED_FORMATS or not 0 < size <= MAX_BYTES or self.headers.get("Transfer-Encoding"):
            self.reply(400)
            return
        if not signatures_ready():
            self.reply(503)
            return
        if not self.server.slot.acquire(blocking=False):
            self.reply(429)
            return
        try:
            with tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                footprint = 3 if file_format in CONVERTED_FORMATS else 1
                if shutil.disk_usage(folder).free < footprint * size + 128 * 1024**2:
                    self.reply(503)
                    return
                with (folder / "original").open("wb") as target:
                    transfer(self.rfile, target, size)
                (folder / "request.json").write_text(json.dumps({"format": file_format}))
                result = run_one(folder, True)
                if result.get("error"):
                    self.reply(422, json.dumps(result).encode(), **{"Content-Type": "application/json"})
                    return
                pdf = folder / "reader.pdf"
                size = pdf.stat().st_size if file_format in CONVERTED_FORMATS else 0
                if size > MAX_BYTES:
                    self.reply(422, json.dumps({"error": "O PDF convertido é demasiado grande."}).encode())
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(size))
                self.send_header("X-PDF-Pages", str(result["pages"]))
                self.send_header("X-Original-SHA256", result["sha256"])
                self.send_header("Connection", "close")
                self.close_connection = True
                self.end_headers()
                if size:
                    with pdf.open("rb") as source:
                        transfer(source, self.wfile, size)
        except (OSError, ValueError):
            self.close_connection = True
        finally:
            self.server.slot.release()


if __name__ == "__main__":
    ProcessorServer(("::", 8080), os.environ["ROVUMA_PROCESSOR_TOKEN"]).serve_forever()
