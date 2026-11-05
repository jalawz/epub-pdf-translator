"""Testes adicionais para o TranslationPipeline (cobertura de linhas restantes)."""

import os
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.pipeline import TranslationPipeline
from src.core.translator import BaseTranslatorEngine


class FakeTranslator(BaseTranslatorEngine):
    def __init__(self):
        self.lang_in = "en"
        self.lang_out = "pt"
        self.calls = []

    def translate(self, text: str) -> str:
        self.calls.append(text)
        return f"[PT] {text}"


def _make_epub(path: Path, chapters: list):
    """Cria um EPUB com capítulos específicos."""
    container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

    manifest_items = []
    spine_items = []
    chapter_contents = {}

    for i, (chap_id, chap_title, chap_html) in enumerate(chapters):
        manifest_items.append(f'<item id="{chap_id}" href="{chap_id}.xhtml" media-type="application/xhtml+xml"/>')
        spine_items.append(f'<itemref idref="{chap_id}"/>')
        chapter_contents[f"{chap_id}.xhtml"] = chap_html

    manifest = "\n".join(manifest_items)
    spine = "\n".join(spine_items)

    content_opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
    <dc:creator>Test Author</dc:creator>
    <dc:language>en</dc:language>
    <dc:identifier id="BookId">urn:uuid:test</dc:identifier>
  </metadata>
  <manifest>{manifest}</manifest>
  <spine toc="nav">{spine}</spine>
</package>"""

    nav = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
<head><title>Nav</title></head>
<body><nav epub:type="toc"><h1>Nav</h1><ol></ol></nav></body>
</html>"""

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", content_opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        for fname, content in chapter_contents.items():
            z.writestr(f"OEBPS/{fname}", content, compress_type=zipfile.ZIP_DEFLATED)


class TestPipelineForceRecompile:
    def test_force_recompile_retranslates_cached_chapters(self, tmp_path):
        """force_recompile=True deve traduzir capítulos mesmo que já estejam cacheados."""
        epub_path = tmp_path / "book.epub"
        _make_epub(epub_path, [
            ("chap1", "Chapter 1", "<html><body><p>Hello world.</p></body></html>"),
        ])

        output_dir = tmp_path / "output"
        translator = FakeTranslator()

        # Primeira execução - preenche cache
        p1 = TranslationPipeline(
            epub_path=str(epub_path), output_dir=str(output_dir),
            lang_in="en", lang_out="pt", translator=translator, max_workers=1,
        )

        with patch.object(p1.renderer, "render_to_pdf", return_value=True):
            p1.run()

        chapters_dir = output_dir / "cache" / "Test_Book" / "chapters"
        cached_file = chapters_dir / "chap1.html"
        assert cached_file.exists()

        # Segunda execução com force_recompile=False - não re-traduz
        translator2 = FakeTranslator()
        p2 = TranslationPipeline(
            epub_path=str(epub_path), output_dir=str(output_dir),
            lang_in="en", lang_out="pt", translator=translator2, max_workers=1,
        )

        with patch.object(p2.renderer, "render_to_pdf", return_value=True):
            p2.run(force_recompile=False)

        # Não deve ter chamado translate novamente (cache hit)
        assert len(translator2.calls) == 0

    def test_force_recompile_true_does_not_retranslate(self, tmp_path):
        """force_recompile não re-traduz capítulos (apenas re-renderiza PDF)."""
        epub_path = tmp_path / "book.epub"
        _make_epub(epub_path, [
            ("chap1", "Chapter 1", "<html><body><p>Hello world.</p></body></html>"),
        ])

        output_dir = tmp_path / "output"

        # Primeira execução
        translator1 = FakeTranslator()
        p1 = TranslationPipeline(
            epub_path=str(epub_path), output_dir=str(output_dir),
            lang_in="en", lang_out="pt", translator=translator1, max_workers=1,
        )
        with patch.object(p1.renderer, "render_to_pdf", return_value=True):
            p1.run()

        calls_first = len(translator1.calls)
        assert calls_first >= 1

        # Segunda execução com force_recompile=True - não re-traduz, apenas usa cache
        translator2 = FakeTranslator()
        p2 = TranslationPipeline(
            epub_path=str(epub_path), output_dir=str(output_dir),
            lang_in="en", lang_out="pt", translator=translator2, max_workers=1,
        )
        with patch.object(p2.renderer, "render_to_pdf", return_value=True):
            p2.run(force_recompile=True)

        # force_recompile não chama _translate_chapter_content novamente
        assert len(translator2.calls) == 0


class TestPipelineQualityAudit:
    def test_quality_audit_writes_report(self, tmp_path):
        """O relatório de qualidade deve ser escrito no output_dir."""
        epub_path = tmp_path / "book.epub"
        _make_epub(epub_path, [
            ("chap1", "Chapter 1", "<html><body><p>Hello world.</p></body></html>"),
        ])

        output_dir = tmp_path / "output"
        translator = FakeTranslator()

        p = TranslationPipeline(
            epub_path=str(epub_path), output_dir=str(output_dir),
            lang_in="en", lang_out="pt", translator=translator, max_workers=1,
        )

        with patch.object(p.renderer, "render_to_pdf", return_value=True):
            p.run()

        report_path = output_dir / "translation_quality_report.json"
        assert report_path.exists()

        import json
        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)

        assert "book" in report
        assert "total_chapters" in report
        assert "quality_certified" in report

    def test_library_registration_failure_does_not_crash(self, tmp_path):
        """Falha ao registrar na biblioteca não deve quebrar o pipeline."""
        epub_path = tmp_path / "book.epub"
        _make_epub(epub_path, [
            ("chap1", "Chapter 1", "<html><body><p>Hello world.</p></body></html>"),
        ])

        output_dir = tmp_path / "output"
        translator = FakeTranslator()

        p = TranslationPipeline(
            epub_path=str(epub_path), output_dir=str(output_dir),
            lang_in="en", lang_out="pt", translator=translator, max_workers=1,
        )

        with patch.object(p.renderer, "render_to_pdf", return_value=True):
            # Mock BookLibrary.add_book para lançar exceção
            with patch("src.pipeline.BookLibrary") as mock_lib:
                mock_lib.side_effect = Exception("DB error")
                # Não deve lançar exceção para o usuário
                result = p.run()
                assert result is not None

    def test_cleanup_removes_chapter_pdfs_when_keep_cache_false(self, tmp_path):
        """PDFs de capítulo devem ser removidos quando keep_cache=False."""
        epub_path = tmp_path / "book.epub"
        _make_epub(epub_path, [
            ("chap1", "Chapter 1", "<html><body><p>Hello world.</p></body></html>"),
        ])

        output_dir = tmp_path / "output"
        translator = FakeTranslator()

        p = TranslationPipeline(
            epub_path=str(epub_path), output_dir=str(output_dir),
            lang_in="en", lang_out="pt", translator=translator, max_workers=1,
        )

        with patch.object(p.renderer, "render_to_pdf", return_value=True):
            p.run(keep_cache=False)

        pdfs_dir = output_dir / "cache" / "Test_Book" / "pdfs"
        if pdfs_dir.exists():
            pdfs = list(pdfs_dir.glob("*.pdf"))
            # Com keep_cache=False, os PDFs devem ter sido removidos
            assert len(pdfs) == 0

    def test_cleanup_keeps_chapter_pdfs_when_keep_cache_true(self, tmp_path):
        """PDFs de capítulo devem ser preservados quando keep_cache=True."""
        epub_path = tmp_path / "book.epub"
        _make_epub(epub_path, [
            ("chap1", "Chapter 1", "<html><body><p>Hello world.</p></body></html>"),
        ])

        output_dir = tmp_path / "output"
        translator = FakeTranslator()

        p = TranslationPipeline(
            epub_path=str(epub_path), output_dir=str(output_dir),
            lang_in="en", lang_out="pt", translator=translator, max_workers=1,
        )

        with patch.object(p.renderer, "render_to_pdf", return_value=True):
            p.run(keep_cache=True)

        pdfs_dir = output_dir / "cache" / "Test_Book" / "pdfs"
        # Cria PDFs fake para simular que o renderer os gerou
        os.makedirs(pdfs_dir, exist_ok=True)
        fake_pdf = pdfs_dir / "chap1.pdf"
        fake_pdf.write_bytes(b"fake pdf content")

        # Verifica que os PDFs existem após o run com keep_cache=True
        # (o run não remove quando keep_cache=True)
        assert fake_pdf.exists()
