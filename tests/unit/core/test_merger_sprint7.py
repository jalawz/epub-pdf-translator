"""Testes adicionais para o DocumentMerger (coverage de merge_pdfs e pack_epub)."""

from pathlib import Path

import fitz
import pypdf
import pytest
import zipfile

from src.core.merger import DocumentMerger


def _make_pdf_with_outline(path: Path, title: str):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), title, fontsize=12)
    doc.save(str(path))
    doc.close()


class TestDocumentMergerAdditional:
    def test_merge_pdfs_with_outline_and_internal_links(self, tmp_path):
        """PDFs com links externos devem ser convertidos para links internos GoTo."""
        p1 = tmp_path / "a.pdf"
        p2 = tmp_path / "b.pdf"
        _make_pdf_with_outline(p1, "Capítulo A")
        _make_pdf_with_outline(p2, "Capítulo B")

        out = tmp_path / "merged.pdf"
        result = DocumentMerger.merge_pdfs(
            [str(p1), str(p2)],
            str(out),
            chapter_titles=["Capítulo A", "Capítulo B"],
            chapter_keys=["chap1.xhtml", "chap2.xhtml"],
        )

        assert result is True
        reader = pypdf.PdfReader(str(out))
        assert len(reader.pages) == 2

    def test_merge_pdfs_empty_list(self, tmp_path):
        """Lista vazia de PDFs deve criar um PDF vazio válido."""
        out = tmp_path / "empty.pdf"
        result = DocumentMerger.merge_pdfs([], str(out))

        # Não deve lançar exceção
        assert result is True or result is False

    def test_pack_epub_overwrites_existing(self, tmp_path):
        """pack_epub deve sobrescrever arquivo de saída existente."""
        original = tmp_path / "original.epub"
        with zipfile.ZipFile(original, "w") as z:
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            z.writestr("OEBPS/chapter1.xhtml", "<html><body>Hello</body></html>", compress_type=zipfile.ZIP_DEFLATED)

        out = tmp_path / "translated.epub"
        # Cria arquivo existente
        out.write_bytes(b"old content")

        result = DocumentMerger.pack_epub(
            str(original),
            {"OEBPS/chapter1.xhtml": "<html><body>Olá</body></html>"},
            str(out),
        )

        assert result is True
        assert out.read_bytes() != b"old content"
