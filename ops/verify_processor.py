"""Exercise antivirus scanning, DOCX conversion and PDF validation in the processor image."""

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from documents.worker import convert, pdf_pages, scan, validate_docx


def write_probe_docx(path):
    with ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", """
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Override PartName="/word/document.xml"
ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""".strip())
        archive.writestr("_rels/.rels", """
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
Target="word/document.xml"/>
</Relationships>""".strip())
        archive.writestr("word/document.xml", """
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>Sonda de verificação do processador.</w:t></w:r></w:p></w:body>
</w:document>""".strip())


def write_probe_odt(path):
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        archive.writestr("META-INF/manifest.xml", """\
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">
  <manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>
  <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
</manifest:manifest>""")
        archive.writestr("content.xml", """\
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2">
  <office:scripts/>
  <office:body><office:text><text:p>Ensaio de conversão ODT.</text:p></office:text></office:body>
</office:document-content>""")


def main():
    for binary in ("clamscan", "libreoffice"):
        if not shutil.which(binary):
            raise SystemExit(f"O processador precisa do executável {binary}.")
    with TemporaryDirectory() as name:
        directory = Path(name)
        original = directory / "sonda.docx"
        output = directory / "leitura.pdf"
        write_probe_docx(original)
        scan(original, required=True)
        validate_docx(original)
        convert(original, directory, output)
        scan(output, required=True)
        pages = pdf_pages(output)
        print(f"Processador verificado. DOCX convertido e PDF validado com {pages} página(s).")


if __name__ == "__main__":
    main()
