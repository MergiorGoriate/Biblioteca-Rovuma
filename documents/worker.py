"""Executado num contentor sem rede nem acesso à base de dados ou ao acervo."""
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from defusedxml.ElementTree import fromstring
from defusedxml.common import DefusedXmlException
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .formats import CONVERTED_FORMATS, TEXT_MAX_BYTES


class Rejected(Exception):
    pass


def scan(path, required):
    binary = shutil.which("clamscan")
    if not binary and not required:
        return
    if not binary:
        raise Rejected("O antivírus não está disponível.")
    size = path.stat().st_size
    if size >= 2 * 1024**3:
        raise Rejected("O ficheiro ultrapassa o limite do motor antivírus.")
    limit = max(size + 1024**2, 128 * 1024**2)
    result = subprocess.run([binary, "--no-summary", f"--max-filesize={limit}",
                             f"--max-scansize={limit}", "--alert-exceeds-max=yes", str(path)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=240)
    if result.returncode == 1:
        raise Rejected("O antivírus sinalizou conteúdo malicioso ou limites de análise excedidos.")
    if result.returncode:
        raise Rejected("O antivírus não conseguiu concluir a análise. Verifique as assinaturas.")


def validate_docx(path):
    try:
        with ZipFile(path) as zipped:
            members = zipped.infolist()
            if len(members) > 8000 or sum(m.file_size for m in members) > 768 * 1024**2:
                raise Rejected("O DOCX ultrapassa os limites internos de segurança.")
            names = [m.filename for m in members]
            if len(set(names)) != len(names) or not {"[Content_Types].xml", "word/document.xml"} <= set(names):
                raise Rejected("Estrutura DOCX inválida.")
            for member in members:
                name = member.filename.lower()
                if (member.flag_bits & 1 or name.startswith("/") or ".." in Path(name).parts
                        or "vba" in name or "/activex/" in name or "/embeddings/" in name):
                    raise Rejected("O DOCX contém macros, objectos incorporados ou entradas inseguras.")
                if name.endswith(".rels") or name == "[content_types].xml":
                    if member.file_size > 2 * 1024**2:
                        raise Rejected("O DOCX contém relações demasiado grandes.")
                    for item in fromstring(zipped.read(member)).iter():
                        if (item.attrib.get("TargetMode", "").lower() == "external" and
                                not item.attrib.get("Type", "").endswith("/hyperlink")):
                            raise Rejected("O DOCX tem dependências externas.")
                        if any("macroenabled" in value.lower() for value in item.attrib.values()):
                            raise Rejected("O DOCX declara suporte para macros.")
    except (BadZipFile, ValueError) as exc:
        raise Rejected("Estrutura DOCX inválida.") from exc


def validate_odt(path):
    mimetype = b"application/vnd.oasis.opendocument.text"
    href_key = "{http://www.w3.org/1999/xlink}href"
    base_key = "{http://www.w3.org/XML/1998/namespace}base"
    office = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
    text_link = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}a"
    blocked_elements = {"script", "event-listener", "object", "object-ole",
                        "plugin", "applet", "floating-frame", "dde-connection", "encrypted-data", "encryption-data"}
    try:
        with ZipFile(path) as zipped:
            members = zipped.infolist()
            names = {member.filename for member in members}
            if len(members) > 8000 or sum(member.file_size for member in members) > 768 * 1024**2:
                raise Rejected("O ODT ultrapassa os limites internos de segurança.")
            if (len(names) != len(members) or not {"mimetype", "content.xml", "META-INF/manifest.xml"} <= names
                    or zipped.getinfo("mimetype").file_size != len(mimetype) or zipped.read("mimetype") != mimetype):
                raise Rejected("Estrutura ODT inválida.")
            for member in members:
                name = member.filename
                parts = Path(name.lower()).parts
                if (member.flag_bits & 1 or name.startswith("/") or "\\" in name or ".." in parts
                        or stat.S_ISLNK(member.external_attr >> 16)
                        or any(part in {"basic", "scripts", "objectreplacements"} or part.startswith("object ") for part in parts)):
                    raise Rejected("O ODT contém macros, objectos incorporados ou entradas inseguras.")
                if not name.lower().endswith(".xml"):
                    continue
                if member.file_size > 12 * 1024**2:
                    raise Rejected("O ODT contém uma entrada XML demasiado grande.")
                root = fromstring(zipped.read(member))
                if name == "content.xml" and (
                    root.tag != f"{office}document-content" or root.find(f"{office}body/{office}text") is None
                ):
                    raise Rejected("O ODT não contém um documento de texto válido.")
                for element in root.iter():
                    if element.tag.rsplit("}", 1)[-1] in blocked_elements or element.get(base_key):
                        raise Rejected("O ODT contém elementos activos, incorporados ou encriptados.")
                    href = element.get(href_key, "")
                    if not href or href.startswith("#"):
                        continue
                    link = urlsplit(href)
                    if element.tag == text_link and link.scheme.lower() in {"http", "https", "mailto"}:
                        continue
                    if link.scheme or link.netloc or unquote(href).removeprefix("./") not in names:
                        raise Rejected("O ODT tem dependências externas ou incompatíveis.")
    except (BadZipFile, ValueError, ParseError, DefusedXmlException, RuntimeError) as exc:
        raise Rejected("Estrutura ODT inválida.") from exc


def validate_text(path):
    if path.stat().st_size > TEXT_MAX_BYTES:
        raise Rejected("Os ficheiros TXT podem ter até 10 MiB.")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise Rejected("Guarde o ficheiro TXT com codificação UTF-8.") from exc
    if not text.strip() or re.search(r"[\x00-\x08\x0b\x0e-\x1f\x7f-\x9f]", text):
        raise Rejected("O TXT está vazio ou contém caracteres de controlo incompatíveis.")


def convert(path, folder, target, file_format="docx"):
    binary = shutil.which("libreoffice")
    if not binary:
        raise Rejected("LibreOffice indisponível no processador isolado.")
    filters = {"docx": "MS Word 2007 XML", "odt": "writer8", "txt": "Text (encoded):UTF8,LF,Liberation Mono,pt-PT"}
    input_path = folder / f"input.{file_format}"
    shutil.copyfile(path, input_path)
    profile = folder / "profile/user"
    profile.mkdir(parents=True)
    (profile / "registrymodifications.xcu").write_text(
        '<oor:items xmlns:oor="http://openoffice.org/2001/registry">'
        '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
        '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
        '</item></oor:items>', encoding="utf-8")
    result = subprocess.run([binary, f"-env:UserInstallation={(folder / 'profile').as_uri()}",
                             "--headless", "--norestore", f"--infilter={filters[file_format]}",
                             "--convert-to", "pdf:writer_pdf_Export",
                             "--outdir", str(folder), str(input_path)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    output = folder / "input.pdf"
    if result.returncode or not output.is_file():
        raise Rejected(f"Não foi possível converter o {file_format.upper()} em PDF.")
    shutil.copyfile(output, target)


def pdf_pages(path):
    with path.open("rb") as file:
        if not file.read(8).startswith(b"%PDF-"):
            raise Rejected("O conteúdo não corresponde a um PDF.")
        reader = PdfReader(file, strict=True)
        if reader.is_encrypted:
            raise Rejected("O PDF está protegido por senha.")
        root = reader.root_object
        forbidden = {"/JavaScript", "/EmbeddedFiles", "/JS", "/Launch", "/RichMedia", "/AA", "/XFA"}
        stack, seen, total = [root], set(), 0
        from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject
        while stack:
            item = stack.pop()
            if isinstance(item, IndirectObject):
                identity = (item.idnum, item.generation)
                if identity in seen:
                    continue
                seen.add(identity)
                item = item.get_object()
            total += 1
            if total > 1_000_000:
                raise Rejected("O PDF ultrapassa o limite de complexidade.")
            if isinstance(item, DictionaryObject):
                if "/OpenAction" in item:
                    opening = item["/OpenAction"]
                    # LibreOffice exports an internal destination to set the initial view.
                    destination = opening
                    if isinstance(opening, DictionaryObject) and opening.get("/S") == "/GoTo" and "/Next" not in opening:
                        destination = opening.get("/D")
                        if isinstance(destination, IndirectObject):
                            destination = destination.get_object()
                    if not isinstance(destination, ArrayObject):
                        raise Rejected("O PDF contém uma acção de abertura incompatível.")
                if forbidden.intersection(item) or any(item.get(key) in forbidden for key in ("/S", "/Subtype")
                                                             if isinstance(item.get(key), str)):
                    raise Rejected("O PDF contém acções ou componentes activos.")
                stack.extend(item.values())
            elif isinstance(item, ArrayObject):
                stack.extend(item)
        pages = len(reader.pages)
        if not pages:
            raise Rejected("O PDF está vazio.")
        return pages


def run_one(folder, required):
    job = json.loads((folder / "request.json").read_text())
    origin = folder / "original"
    target = folder / "reader.tmp"
    try:
        scan(origin, required)
        with origin.open("rb") as fp:
            digest = hashlib.file_digest(fp, "sha256").hexdigest()
        file_format = job["format"]
        if file_format in CONVERTED_FORMATS:
            {"docx": validate_docx, "odt": validate_odt, "txt": validate_text}[file_format](origin)
            with tempfile.TemporaryDirectory(dir=folder) as working:
                convert(origin, Path(working), target, file_format)
            scan(target, required)
        elif file_format == "pdf":
            target = origin
        else:
            raise Rejected("Formato de documento incompatível.")
        pages = pdf_pages(target)
        if target != origin:
            target.replace(folder / "reader.pdf")
        return {"pages": pages, "sha256": digest}
    except Rejected as exc:
        return {"error": str(exc)}
    except subprocess.TimeoutExpired:
        return {"error": "O processamento ultrapassou o tempo máximo."}
    except (PdfReadError, ValueError, KeyError, TypeError, EOFError):
        return {"error": "A estrutura do documento é inválida ou contém elementos incompatíveis."}
    except Exception:
        return {"error": "Falha ao verificar o documento. Consulte a configuração do processador."}
    finally:
        (folder / "reader.tmp").unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spool", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--development-no-antivirus", action="store_true")
    args = parser.parse_args()
    args.spool.mkdir(parents=True, exist_ok=True)
    while True:
        for folder in sorted(args.spool.iterdir()):
            try:
                if str(uuid.UUID(folder.name)) != folder.name:
                    continue
            except ValueError:
                continue
            try:
                request = folder / "request.json"
                if not request.is_file():
                    continue
                if (folder / "result.json").exists():
                    continue
                result = run_one(folder, not args.development_no_antivirus)
                temp = folder / "result.tmp"
                temp.write_text(json.dumps(result), encoding="utf-8")
                temp.replace(folder / "result.json")
            except FileNotFoundError:
                # The dispatcher may remove an expired or interrupted request.
                continue
        if args.once:
            return
        time.sleep(3)


if __name__ == "__main__":
    main()
