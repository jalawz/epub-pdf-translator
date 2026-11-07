"""Testes unitários para o DocumentMerger (junção de PDFs + reempacotamento EPUB)."""

import os
import zipfile
from pathlib import Path

import fitz  # PyMuPDF
import pypdf
import pytest

from src.core.merger import DocumentMerger


# ---------------------------------------------------------------------------
# Helper: criar PDFs de teste com fitz
# ---------------------------------------------------------------------------
def _make_pdf(path: Path, title: str, pages: int = 1):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{title} - página {i + 1}", fontsize=12)
    doc.save(str(path))
    doc.close()


def _make_multi_page_pdf(path: Path, title: str, pages: int = 3):
    _make_pdf(path, title, pages=pages)


class TestMergePdfs:
    def test_merge_three_single_page_pdfs(self, tmp_path):
        p1 = tmp_path / "a.pdf"
        p2 = tmp_path / "b.pdf"
        p3 = tmp_path / "c.pdf"
        _make_pdf(p1, "Capítulo A")
        _make_pdf(p2, "Capítulo B")
        _make_pdf(p3, "Capítulo C")

        out = tmp_path / "merged.pdf"
        titles = ["Capítulo A", "Capítulo B", "Capítulo C"]
        keys = ["chap1.xhtml", "chap2.xhtml", "chap3.xhtml"]

        result = DocumentMerger.merge_pdfs([str(p1), str(p2), str(p3)], str(out), titles, keys)

        assert result is True
        assert out.exists()
        assert out.stat().st_size > 0

        reader = pypdf.PdfReader(str(out))
        assert len(reader.pages) == 3

        # Verifica outline (bookmarks)
        outline = reader.outline
        assert len(outline) == 3
        assert outline[0].title == "Capítulo A"
        assert outline[1].title == "Capítulo B"
        assert outline[2].title == "Capítulo C"

    def test_merge_with_empty_pdf_skips(self, tmp_path):
        p1 = tmp_path / "a.pdf"
        p2 = tmp_path / "b.pdf"
        _make_pdf(p1, "Capítulo A")
        # PDF vazio (arquivo existe mas tamanho 0)
        p2.write_bytes(b"")

        out = tmp_path / "merged.pdf"
        result = DocumentMerger.merge_pdfs([str(p1), str(p2)], str(out))

        assert result is True
        reader = pypdf.PdfReader(str(out))
        assert len(reader.pages) == 1

    def test_merge_nonexistent_pdf_skips(self, tmp_path):
        p1 = tmp_path / "a.pdf"
        _make_pdf(p1, "Capítulo A")
        p2 = tmp_path / "nao_existe.pdf"

        out = tmp_path / "merged.pdf"
        result = DocumentMerger.merge_pdfs([str(p1), str(p2)], str(out))

        assert result is True
        reader = pypdf.PdfReader(str(out))
        assert len(reader.pages) == 1

    def test_merge_creates_output_dir(self, tmp_path):
        p1 = tmp_path / "a.pdf"
        _make_pdf(p1, "Capítulo A")

        out = tmp_path / "subdir" / "nested" / "merged.pdf"
        result = DocumentMerger.merge_pdfs([str(p1)], str(out))

        assert result is True
        assert out.exists()


class TestPackEpub:
    def test_pack_epub_preserves_mimetype_first_and_uncompressed(self, tmp_path):
        # Cria EPUB original com mimetype + 1 capítulo + imagem
        original = tmp_path / "original.epub"
        with zipfile.ZipFile(original, "w") as z:
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            z.writestr("META-INF/container.xml", "<container/>", compress_type=zipfile.ZIP_DEFLATED)
            z.writestr("OEBPS/chapter1.xhtml", "<html><body>Hello</body></html>", compress_type=zipfile.ZIP_DEFLATED)
            z.writestr("OEBPS/styles.css", "body{}", compress_type=zipfile.ZIP_DEFLATED)

        translated = {
            "OEBPS/chapter1.xhtml": "<html><body>Olá</body></html>",
        }

        out = tmp_path / "translated.epub"
        result = DocumentMerger.pack_epub(str(original), translated, str(out))

        assert result is True
        assert out.exists()

        with zipfile.ZipFile(out, "r") as z:
            names = z.namelist()
            assert names[0] == "mimetype", f"mimetype deve ser o primeiro: {names}"
            # mimetype não comprimido
            info = z.getinfo("mimetype")
            assert info.compress_type == zipfile.ZIP_STORED
            # Conteúdo traduzido
            chap = z.read("OEBPS/chapter1.xhtml").decode("utf-8")
            assert "Olá" in chap
            # Ativos não traduzidos são copiados
            css = z.read("OEBPS/styles.css").decode("utf-8")
            assert css == "body{}"

    def test_pack_epub_copies_unchanged_assets(self, tmp_path):
        original = tmp_path / "original.epub"
        with zipfile.ZipFile(original, "w") as z:
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            z.writestr("OEBPS/image.png", b"\x89PNG fake", compress_type=zipfile.ZIP_DEFLATED)
            z.writestr("OEBPS/chapter1.xhtml", "<html><body>Hello</body></html>", compress_type=zipfile.ZIP_DEFLATED)

        out = tmp_path / "translated.epub"
        DocumentMerger.pack_epub(
            str(original),
            {"OEBPS/chapter1.xhtml": "<html><body>Olá</body></html>"},
            str(out),
        )

        with zipfile.ZipFile(out, "r") as z:
            img = z.read("OEBPS/image.png")
            assert img == b"\x89PNG fake"

    def test_pack_epub_output_path_valid(self, tmp_path):
        original = tmp_path / "original.epub"
        with zipfile.ZipFile(original, "w") as z:
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            z.writestr("OEBPS/chapter1.xhtml", "<html><body>Hello</body></html>", compress_type=zipfile.ZIP_DEFLATED)

        out = tmp_path / "deep" / "nested" / "out.epub"
        result = DocumentMerger.pack_epub(str(original), {}, str(out))

        assert result is True
        assert out.exists()
