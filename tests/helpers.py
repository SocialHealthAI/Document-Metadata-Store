from __future__ import annotations

from pathlib import Path


def _assemble_pdf(objects: list[str], *, info_index: int | None = None) -> bytes:
    header = "%PDF-1.4\n"
    body_parts: list[str] = []
    offsets = [0]
    cursor = len(header.encode("latin-1"))
    for index, obj in enumerate(objects, start=1):
        rendered = f"{index} 0 obj\n{obj}\nendobj\n"
        offsets.append(cursor)
        body_parts.append(rendered)
        cursor += len(rendered.encode("latin-1"))
    body = "".join(body_parts)
    xref_start = cursor
    xref_lines = ["xref", f"0 {len(objects) + 1}", "0000000000 65535 f "]
    for offset in offsets[1:]:
        xref_lines.append(f"{offset:010d} 00000 n ")
    trailer = (
        "trailer\n"
        f"<< /Size {len(objects) + 1} /Root 1 0 R"
        + (f" /Info {info_index} 0 R" if info_index else "")
        + " >>\n"
        f"startxref\n{xref_start}\n%%EOF\n"
    )
    return (header + body + "\n".join(xref_lines) + "\n" + trailer).encode("latin-1")


def write_text_pdf(path: Path, *, title: str | None = "Test Document") -> Path:
    """Write a one-page PDF with extractable Helvetica text."""
    stream = (
        "BT\n"
        "/F1 24 Tf 72 720 Td (Heading Line) Tj\n"
        "/F2 12 Tf 0 -36 Td (Body paragraph text for the loader.) Tj\n"
        "ET\n"
    )
    info = "<< >>"
    if title:
        escaped = title.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        info = f"<< /Title ({escaped}) /Author (Unit Test) >>"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}endstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        info,
    ]
    path.write_bytes(_assemble_pdf(objects, info_index=7))
    return path


def write_blank_pdf(path: Path) -> Path:
    """Write a one-page PDF with no text operators (image-only stand-in)."""
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>",
        "<< /Length 0 >>\nstream\nendstream",
    ]
    path.write_bytes(_assemble_pdf(objects))
    return path


def write_broken_pdf(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.4 this is not a valid pdf")
    return path
