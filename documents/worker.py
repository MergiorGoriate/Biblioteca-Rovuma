"""Executado num contentor sem rede nem acesso à base de dados ou ao acervo."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from defusedxml.ElementTree import fromstring
from pypdf import PdfReader
from pypdf.errors import PdfReadError


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


def convert(path, folder, target):
    binary = shutil.which("libreoffice")
    if not binary:
        raise Rejected("LibreOffice indisponível no processador isolado.")
    input_path = folder / "input.docx"
    shutil.copyfile(path, input_path)
    profile = folder / "profile/user"
    profile.mkdir(parents=True)
    (profile / "registrymodifications.xcu").write_text(
        '<oor:items xmlns:oor="http://openoffice.org/2001/registry">'
        '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
        '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
        '</item></oor:items>', encoding="utf-8")
    result = subprocess.run([binary, f"-env:UserInstallation={(folder / 'profile').as_uri()}",
                             "--headless", "--norestore", "--convert-to", "pdf:writer_pdf_Export",
                             "--outdir", str(folder), str(input_path)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    output = folder / "input.pdf"
    if result.returncode or not output.is_file():
        raise Rejected("Não foi possível converter o DOCX em PDF.")
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
        if job["format"] == "docx":
            validate_docx(origin)
            with tempfile.TemporaryDirectory() as working:
                convert(origin, Path(working), target)
            scan(target, required)
        else:
            target = origin
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
            if not (folder / "request.json").is_file() or (folder / "result.json").exists():
                continue
            result = run_one(folder, not args.development_no_antivirus)
            temp = folder / "result.tmp"
            temp.write_text(json.dumps(result), encoding="utf-8")
            temp.replace(folder / "result.json")
        if args.once:
            return
        time.sleep(3)


if __name__ == "__main__":
    main()
