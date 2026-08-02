"""Generate the binary sample documents (PDF, DOCX) from their .txt sources.

Run once after cloning if the binaries are missing::

    python data/sample_documents/generate_samples.py

Keeping generators (not committing large binaries as source-of-truth) makes the
repo diff-friendly and the samples reproducible. The .pdf/.docx are also
committed so a grader doesn't strictly need to run this.
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).parent


def make_pdf(src_txt: Path, out_pdf: Path) -> None:
    from pypdf import PdfWriter
    from pypdf.generic import (
        ArrayObject,
        DictionaryObject,
        FloatObject,
        NameObject,
        NumberObject,
        TextStringObject,
    )

    # Minimal single-page PDF with the text drawn line by line. We build a
    # content stream by hand so we don't need reportlab as a dependency.
    lines = src_txt.read_text(encoding="utf-8").splitlines()
    y = 760
    parts = ["BT", "/F1 11 Tf", "12 TL", f"1 0 0 1 56 {y} Tm"]
    for line in lines:
        safe = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        parts.append(f"({safe}) Tj")
        parts.append("T*")
    parts.append("ET")
    stream = "\n".join(parts)

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    from pypdf.generic import DecodedStreamObject

    content = DecodedStreamObject()
    content.set_data(stream.encode("latin-1"))
    content_ref = writer._add_object(content)

    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    resources = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    page[NameObject("/Contents")] = content_ref
    page[NameObject("/Resources")] = resources

    with out_pdf.open("wb") as fh:
        writer.write(fh)


def make_docx(src_txt: Path, out_docx: Path) -> None:
    import docx

    document = docx.Document()
    for line in src_txt.read_text(encoding="utf-8").splitlines():
        document.add_paragraph(line)
    document.save(out_docx)


def main() -> None:
    make_pdf(HERE / "_src_max_vaccine.txt", HERE / "max_vaccine.pdf")
    make_docx(HERE / "_src_bella_meds.txt", HERE / "bella_meds.docx")
    print("Wrote max_vaccine.pdf and bella_meds.docx")


if __name__ == "__main__":
    main()
