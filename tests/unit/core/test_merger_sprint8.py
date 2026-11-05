"""Testes adicionais para o DocumentMerger (coverage de linhas restantes)."""

from pathlib import Path

import fitz
import pypdf
import zipfile
import pytest

from src.core.merger import DocumentMerger


def _make_pdf(path: Path, title: str):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), title, fontsize=12)
    doc.save(str(path))
    doc.close()


class TestDocumentMergerSprint8:
    def test_merge_pdfs_with_chapter_keys(self, tmp_path):
        """chapter_keys deve registrar páginas iniciais para links internos."""
        p1 = tmp_path / "a.pdf"
        p2 = tmp_path / "b.pdf"
        _make_pdf(p1, "Capítulo A")
        _make_pdf(p2, "Capítulo B")

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
        # Verifica que bookmarks foram criados
        outline = reader.outline
        assert len(outline) == 2

    def test_merge_pdfs_missing_chapter_titles(self, tmp_path):
        """Quando chapter_titles não é fornecido, usa nomes padrão."""
        p1 = tmp_path / "a.pdf"
        _make_pdf(p1, "Qualquer Título")

        out = tmp_path / "merged.pdf"
        result = DocumentMerger.merge_pdfs([str(p1)], str(out))

        assert result is True
        reader = pypdf.PdfReader(str(out))
        assert len(reader.pages) == 1

    def test_pack_epub_empty_translated_files(self, tmp_path):
        """pack_epub com dict vazio deve copiar tudo do original."""
        original = tmp_path / "original.epub"
        with zipfile.ZipFile(original, "w") as z:
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            z.writestr("OEBPS/chapter1.xhtml", "<html><body>Hello</body></html>", compress_type=zipfile.ZIP_DEFLATED)
            z.writestr("OEBPS/styles.css", "body{}", compress_type=zipfile.ZIP_DEFLATED)

        out = tmp_path / "translated.epub"
        result = DocumentMerger.pack_epub(str(original), {}, str(out))

        assert result is True
        assert out.exists()

        with zipfile.ZipFile(out, "r") as z:
            names = z.namelist()
            assert names[0] == "mimetype"
            assert "OEBPS/chapter1.xhtml" in names
            assert "OEBPS/styles.css" in names

    def test_pack_epub_with_cover_properties(self, tmp_path):
        """Imagens de capa devem ter properties='cover-image' quando presentes."""
        original = tmp_path / "original.epub"
        content_opf_with_cover = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Original Book</dc:title>
    <dc:creator>Author</dc:creator>
    <dc:language>pt</dc:language>
    <dc:identifier id="BookId">urn:uuid:test</dc:identifier>
    <meta property="cover-image">cover-img</meta>
  </metadata>
  <manifest>
    <item id="cover-img" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>
    <item id="chap1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="nav">
    <itemref idref="chap1"/>
  </spine>
</package>"""

        with zipfile.ZipFile(original, "w") as z:
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            z.writestr("OEBPS/content.opf", content_opf_with_cover, compress_type=zipfile.ZIP_DEFLATED)
            z.writestr("OEBPS/chapter1.xhtml", "<html><body>Hello</body></html>", compress_type=zipfile.ZIP_DEFLATED)
            z.writestr("OEBPS/images/cover.jpg", b"\xff\xd8\xff fake jpg", compress_type=zipfile.ZIP_DEFLATED)

        out = tmp_path / "translated.epub"
        DocumentMerger.pack_epub(
            str(original),
            {"OEBPS/chapter1.xhtml": "<html><body>Olá</body></html>"},
            str(out),
        )

        with zipfile.ZipFile(out, "r") as z:
            opf = z.read("OEBPS/content.opf").decode("utf-8")
            assert "cover-image" in opf
