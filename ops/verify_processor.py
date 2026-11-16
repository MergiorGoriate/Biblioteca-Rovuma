"""Exercise antivirus scanning, DOCX conversion and PDF validation in the processor image."""

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from documents.worker import convert, pdf_pages, scan, validate_docx


def main():
    for binary in ("clamscan", "libreoffice"):
        if not shutil.which(binary):
            raise SystemExit(f"O processador precisa do executável {binary}.")
    with TemporaryDirectory() as name:
        directory = Path(name)
        original = directory / "sonda.docx"
        output = directory / "leitura.pdf"
        with ZipFile(original, "w") as archive:
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
        scan(original, required=True)
        validate_docx(original)
        convert(original, directory, output)
        scan(output, required=True)
        pages = pdf_pages(output)
        print(f"Processador verificado. DOCX convertido e PDF validado com {pages} página(s).")


if __name__ == "__main__":
    main()
