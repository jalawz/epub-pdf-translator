"""Testes de checkpoint e retomada do TranslationPipeline."""

import os
import zipfile
from pathlib import Path

import pytest

from src.pipeline import TranslationPipeline
from src.core.translator import BaseTranslatorEngine


# ---------------------------------------------------------------------------
# Tradutor fake que grava chamadas
# ---------------------------------------------------------------------------
class RecordingTranslator(BaseTranslatorEngine):
    """Tradutor falso que grava quantas vezes translate() foi chamado."""

    def __init__(self, lang_in="en", lang_out="pt"):
        self.lang_in = lang_in
        self.lang_out = lang_out
        self.calls = []  # lista de textos recebidos
        self._call_count = 0

    def translate(self, text: str) -> str:
        self._call_count += 1
        self.calls.append(text)
        return f"[PT] {text}"


# ---------------------------------------------------------------------------
# Fixture de EPUB com 3 capítulos
# ---------------------------------------------------------------------------
def _make_multi_chapter_epub(path: Path):
    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

    content_opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Multi Chapter Test</dc:title>
    <dc:creator>Test Author</dc:creator>
    <dc:language>en</dc:language>
    <dc:identifier id="BookId">urn:uuid:11111111-1111-1111-1111-111111111111</dc:identifier>
  </metadata>
  <manifest>
    <item id="chap1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="chap2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>
    <item id="chap3" href="chapter3.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="nav">
    <itemref idref="chap1"/>
    <itemref idref="chap2"/>
    <itemref idref="chap3"/>
  </spine>
</package>"""

    def chapter(num):
        return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
<head><title>Chapter {num}</title></head>
<body>
    <h1>Chapter {num}</h1>
    <p>This is chapter {num} content.</p>
    <pre>public void chapter{num}() {{}}</pre>
</body>
</html>"""

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container_xml, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", content_opf, compress_type=zipfile.ZIP_DEFLATED)
        for n in (1, 2, 3):
            z.writestr(f"OEBPS/chapter{n}.xhtml", chapter(n), compress_type=zipfile.ZIP_DEFLATED)


class TestTranslationPipelineCheckpoint:
    def test_translates_all_chapters_and_caches(self, tmp_path):
        epub_path = tmp_path / "multi.epub"
        _make_multi_chapter_epub(epub_path)

        output_dir = tmp_path / "output"
        translator = RecordingTranslator()

        pipeline = TranslationPipeline(
            epub_path=str(epub_path),
            output_dir=str(output_dir),
            lang_in="en",
            lang_out="pt",
            translator=translator,
            max_workers=2,
        )

        # PdfRenderer vai falhar (sem Chrome), mas a tradução + cache devem ocorrer.
        pipeline.run()

        # Verifica que todos os 3 capítulos foram traduzidos e cacheados
        cache_base = output_dir / "cache" / "Multi_Chapter_Test"
        chapters_dir = cache_base / "chapters"
        cached = list(chapters_dir.glob("*.html"))
        assert len(cached) == 3

        # Verifica que o tradutor foi chamado para cada capítulo
        assert len(translator.calls) >= 3

    def test_checkpoint_avoids_retranslation(self, tmp_path):
        epub_path = tmp_path / "multi.epub"
        _make_multi_chapter_epub(epub_path)

        output_dir = tmp_path / "output"
        translator = RecordingTranslator()

        pipeline = TranslationPipeline(
            epub_path=str(epub_path),
            output_dir=str(output_dir),
            lang_in="en",
            lang_out="pt",
            translator=translator,
            max_workers=2,
        )

        pipeline.run()

        calls_after_first = len(translator.calls)
        assert calls_after_first >= 3

        # Segunda execução: capítulos já cacheados não devem ser re-traduzidos
        translator2 = RecordingTranslator()
        pipeline2 = TranslationPipeline(
            epub_path=str(epub_path),
            output_dir=str(output_dir),
            lang_in="en",
            lang_out="pt",
            translator=translator2,
            max_workers=2,
        )
        pipeline2.run()

        # O segundo tradutor não deveria ter sido chamado (todos cacheados)
        assert len(translator2.calls) == 0

    def test_keep_cache_preserves_chapter_pdfs(self, tmp_path):
        epub_path = tmp_path / "multi.epub"
        _make_multi_chapter_epub(epub_path)

        output_dir = tmp_path / "output"
        translator = RecordingTranslator()

        pipeline = TranslationPipeline(
            epub_path=str(epub_path),
            output_dir=str(output_dir),
            lang_in="en",
            lang_out="pt",
            translator=translator,
            max_workers=2,
        )

        pipeline.run(keep_cache=True)

        pdfs_dir = output_dir / "cache" / "Multi_Chapter_Test" / "pdfs"
        assert pdfs_dir.exists(), f"Diretório de PDFs não existe: {pdfs_dir}"
        pdfs = list(pdfs_dir.glob("*.pdf"))
        # Com keep_cache=True, os PDFs devem permanecer (3 capítulos)
        assert len(pdfs) == 3, f"Esperado 3 PDFs, encontrado {len(pdfs)}"

    def test_pipeline_progress_callback_is_called(self, tmp_path):
        epub_path = tmp_path / "multi.epub"
        _make_multi_chapter_epub(epub_path)

        output_dir = tmp_path / "output"
        translator = RecordingTranslator()

        progress_events = []

        def on_progress(percent, message):
            progress_events.append((percent, message))

        pipeline = TranslationPipeline(
            epub_path=str(epub_path),
            output_dir=str(output_dir),
            lang_in="en",
            lang_out="pt",
            translator=translator,
            max_workers=2,
        )

        pipeline.run(progress_callback=on_progress)

        assert len(progress_events) > 0
        # O pipeline deve começar em 0.05 e terminar em 1.0
        assert progress_events[0][0] == 0.05
        assert progress_events[-1][0] == 1.0

    def test_no_new_chapters_translated_when_all_cached(self, tmp_path):
        epub_path = tmp_path / "multi.epub"
        _make_multi_chapter_epub(epub_path)

        output_dir = tmp_path / "output"

        # Primeira execução preenche o cache
        t1 = RecordingTranslator()
        p1 = TranslationPipeline(
            epub_path=str(epub_path),
            output_dir=str(output_dir),
            lang_in="en",
            lang_out="pt",
            translator=t1,
            max_workers=1,
        )
        p1.run()

        # Segunda execução com keep_cache=False: não deve traduzir nada novo
        t2 = RecordingTranslator()
        p2 = TranslationPipeline(
            epub_path=str(epub_path),
            output_dir=str(output_dir),
            lang_in="en",
            lang_out="pt",
            translator=t2,
            max_workers=1,
        )
        p2.run(keep_cache=False)

        assert len(t2.calls) == 0
