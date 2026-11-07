"""Teste de integração end-to-end: traduz um EPUB completo e gera PDF.

Este teste executa o TranslationPipeline inteiro com:
- Um EPUB real com múltiplos capítulos (incluindo um com código Java para CodeShield)
- Um tradutor fake que simula tradução EN → PT
- O PdfRenderer mockado (não depende de Chrome/Edge instalado)

Verifica que:
- PDF de saída é gerado
- EPUB traduzido é gerado
- Código-fonte não é traduzido (blindagem)
- Relatório de qualidade é produzido
- Livro é registrado na biblioteca digital
"""

import json
import os
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.pipeline import TranslationPipeline
from src.core.translator import BaseTranslatorEngine


# ---------------------------------------------------------------------------
# Tradutor fake para teste de integração
# ---------------------------------------------------------------------------
class FakeTranslator(BaseTranslatorEngine):
    """Tradutor que simula tradução EN → PT acrescentando '[PT] '."""

    def __init__(self):
        self.lang_in = "en"
        self.lang_out = "pt"
        self.calls = []

    def translate(self, text: str) -> str:
        self.calls.append(text)
        # Simula tradução: apenas acrescenta prefixo e devolve o texto
        return f"[PT] {text}"


# ---------------------------------------------------------------------------
# Helper: criar EPUB de teste com 3 capítulos
# ---------------------------------------------------------------------------
def _make_test_epub(path: Path):
    """Cria um EPUB com 3 capítulos, incluindo um com código Java."""

    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

    chapters = [
        ("chap_01.xhtml", "Chapter 1", """
        <?xml version="1.0" encoding="utf-8"?>
        <!DOCTYPE html>
        <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
        <head><title>Chapter 1</title></head>
        <body>
            <h1>Chapter 1</h1>
            <p>Welcome to this book about programming.</p>
            <p>This chapter introduces basic concepts.</p>
        </body>
        </html>"""),
        ("chap_02.xhtml", "Chapter 2", """
        <?xml version="1.0" encoding="utf-8"?>
        <!DOCTYPE html>
        <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
        <head><title>Chapter 2</title></head>
        <body>
            <h1>Chapter 2</h1>
            <p>Here is some Java code:</p>
            <pre><code>public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}</code></pre>
            <p>The code above prints a greeting.</p>
            <p>Visit https://example.com for more info.</p>
        </body>
        </html>"""),
        ("chap_03.xhtml", "Chapter 3", """
        <?xml version="1.0" encoding="utf-8"?>
        <!DOCTYPE html>
        <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
        <head><title>Chapter 3</title></head>
        <body>
            <h1>Chapter 3</h1>
            <p>Conclusion and final thoughts.</p>
            <pre>terminal command: $ curl https://api.example.com/data</pre>
        </body>
        </html>"""),
    ]

    manifest_items = []
    spine_items = []
    chapter_contents = {}

    for chap_id, chap_title, chap_html in chapters:
        manifest_items.append(
            f'<item id="{chap_id}" href="{chap_id}" media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'<itemref idref="{chap_id}"/>')
        chapter_contents[chap_id] = chap_html

    manifest = "\n".join(manifest_items)
    spine = "\n".join(spine_items)

    content_opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Integration Test Book</dc:title>
    <dc:creator>Test Author</dc:creator>
    <dc:language>en</dc:language>
    <dc:identifier id="BookId">urn:uuid:integration-test</dc:identifier>
  </metadata>
  <manifest>{manifest}</manifest>
  <spine toc="nav">{spine}</spine>
</package>"""

    nav = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="en">
<head><title>Navigation</title></head>
<body>
    <nav epub:type="toc" id="toc">
        <h1>Table of Contents</h1>
        <ol>
            <li><a href="chap_01.xhtml">Chapter 1</a></li>
            <li><a href="chap_02.xhtml">Chapter 2</a></li>
            <li><a href="chap_03.xhtml">Chapter 3</a></li>
        </ol>
    </nav>
</body>
</html>"""

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container_xml, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", content_opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        for fname, content in chapter_contents.items():
            z.writestr(f"OEBPS/{fname}", content, compress_type=zipfile.ZIP_DEFLATED)


class TestEndToEndTranslation:
    def test_full_translation_pipeline_generates_pdf_and_epub(self, tmp_path):
        """Teste completo: EPUB → tradução → PDF + EPUB traduzido."""
        epub_path = tmp_path / "book.epub"
        _make_test_epub(epub_path)

        output_dir = tmp_path / "output"

        translator = FakeTranslator()

        pipeline = TranslationPipeline(
            epub_path=str(epub_path),
            output_dir=str(output_dir),
            lang_in="en",
            lang_out="pt",
            translator=translator,
            max_workers=2,
        )

        # Mock do renderer para não depender de Chrome/Edge
        with patch.object(pipeline.renderer, "render_to_pdf", return_value=True):
            final_pdf, final_epub = pipeline.run()

        # --- Verificações de saída ---
        assert final_pdf is not None
        assert final_epub is not None
        assert Path(final_pdf).exists(), f"PDF não encontrado: {final_pdf}"
        assert Path(final_epub).exists(), f"EPUB não encontrado: {final_epub}"
        assert Path(final_pdf).suffix == ".pdf"
        assert Path(final_epub).suffix == ".epub"

        # --- Verificações de tradução ---
        # O tradutor deve ter sido chamado para cada capítulo
        assert len(translator.calls) >= 3, f"Esperado >= 3 chamadas, obteve {len(translator.calls)}"

        # --- Verificações de CodeShield: código Java não traduzido ---
        # Ler o EPUB traduzido e verificar que o código Java está intacto
        with zipfile.ZipFile(final_epub, "r") as z:
            chap2 = z.read("OEBPS/chap_02.xhtml").decode("utf-8")

            # Código Java deve estar presente e não traduzido
            assert "public class HelloWorld" in chap2
            assert "System.out.println" in chap2
            assert "String[] args" in chap2

            # Texto explicativo deve ter sido traduzido (tem [PT] prefixo)
            assert "[PT]" in chap2

        # --- Verificações de relatório de qualidade ---
        report_path = output_dir / "translation_quality_report.json"
        assert report_path.exists(), f"Relatório de qualidade não encontrado: {report_path}"

        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)

        assert "book" in report
        assert "total_chapters" in report
        assert "quality_certified" in report
        assert report["total_chapters"] >= 3

        # --- Verificações de biblioteca digital ---
        library_dir = output_dir / "library"
        assert library_dir.exists(), "Biblioteca digital não criada"

        # Deve existir pelo menos um livro registrado
        lang_dirs = [d for d in library_dir.iterdir() if d.is_dir()]
        assert len(lang_dirs) >= 1, "Nenhum idioma registrado na biblioteca"

        # Verificar que há metadata.json em algum idioma
        metadata_found = False
        for lang_dir in lang_dirs:
            for book_dir in lang_dir.iterdir():
                meta_file = book_dir / "metadata.json"
                if meta_file.exists():
                    metadata_found = True
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    assert meta["title"] == "Integration Test Book"
                    assert meta["lang"] == "pt"
                    break
            if metadata_found:
                break

        assert metadata_found, "Nenhum metadata.json encontrado na biblioteca"

    def test_pipeline_handles_cover_chapter(self, tmp_path):
        """Capítulo de capa deve ser processado corretamente."""
        epub_path = tmp_path / "book_with_cover.epub"

        container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

        chapters = [
            ("cover.xhtml", "Cover", """
            <?xml version="1.0" encoding="utf-8"?>
            <!DOCTYPE html>
            <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
            <head><title>Cover</title></head>
            <body>
                <h1>Cover Page</h1>
                <p>Beautiful cover image.</p>
            </body>
            </html>"""),
            ("chap_01.xhtml", "Chapter 1", """
            <?xml version="1.0" encoding="utf-8"?>
            <!DOCTYPE html>
            <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
            <head><title>Chapter 1</title></head>
            <body>
                <h1>Chapter 1</h1>
                <p>First real chapter.</p>
            </body>
            </html>"""),
        ]

        manifest_items = []
        spine_items = []
        chapter_contents = {}

        for chap_id, chap_title, chap_html in chapters:
            manifest_items.append(
                f'<item id="{chap_id}" href="{chap_id}" media-type="application/xhtml+xml"/>'
            )
            spine_items.append(f'<itemref idref="{chap_id}"/>')
            chapter_contents[chap_id] = chap_html

        manifest = "\n".join(manifest_items)
        spine = "\n".join(spine_items)

        content_opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Book With Cover</dc:title>
    <dc:creator>Author</dc:creator>
    <dc:language>en</dc:language>
    <dc:identifier id="BookId">urn:uuid:cover-test</dc:identifier>
  </metadata>
  <manifest>{manifest}</manifest>
  <spine toc="nav">{spine}</spine>
</package>"""

        nav = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
<head><title>Nav</title></head>
<body>
    <nav epub:type="toc" id="toc">
        <h1>Contents</h1>
        <ol>
            <li><a href="chap_01.xhtml">Chapter 1</a></li>
        </ol>
    </nav>
</body>
</html>"""

        with zipfile.ZipFile(epub_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            z.writestr("META-INF/container.xml", container_xml, compress_type=zipfile.ZIP_DEFLATED)
            z.writestr("OEBPS/content.opf", content_opf, compress_type=zipfile.ZIP_DEFLATED)
            z.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
            for fname, content in chapter_contents.items():
                z.writestr(f"OEBPS/{fname}", content, compress_type=zipfile.ZIP_DEFLATED)

            # Adicionar imagem de capa
            z.writestr("OEBPS/images/cover.png", b"\x89PNG fake cover", compress_type=zipfile.ZIP_DEFLATED)

        output_dir = tmp_path / "output"
        translator = FakeTranslator()

        pipeline = TranslationPipeline(
            epub_path=str(epub_path),
            output_dir=str(output_dir),
            lang_in="en",
            lang_out="pt",
            translator=translator,
            max_workers=1,
        )

        with patch.object(pipeline.renderer, "render_to_pdf", return_value=True):
            final_pdf, final_epub = pipeline.run()

        assert Path(final_pdf).exists()
        assert Path(final_epub).exists()

        # Verificar que o capítulo de capa não quebrou nada
        with zipfile.ZipFile(final_epub, "r") as z:
            cover_content = z.read("OEBPS/cover.xhtml").decode("utf-8")
            assert "[PT]" in cover_content or "Cover Page" in cover_content

    def test_pipeline_checkpoint_avoids_duplicate_translation(self, tmp_path):
        """Segundo run não deve re-traduzir capítulos já cacheados."""
        epub_path = tmp_path / "book.epub"
        _make_test_epub(epub_path)

        output_dir = tmp_path / "output"
        translator = FakeTranslator()

        pipeline = TranslationPipeline(
            epub_path=str(epub_path),
            output_dir=str(output_dir),
            lang_in="en",
            lang_out="pt",
            translator=translator,
            max_workers=1,
        )

        with patch.object(pipeline.renderer, "render_to_pdf", return_value=True):
            pipeline.run()

        calls_first_run = len(translator.calls)
        assert calls_first_run >= 3

        # Segundo run: capítulos já cacheados não devem ser re-traduzidos
        translator2 = FakeTranslator()
        pipeline2 = TranslationPipeline(
            epub_path=str(epub_path),
            output_dir=str(output_dir),
            lang_in="en",
            lang_out="pt",
            translator=translator2,
            max_workers=1,
        )

        with patch.object(pipeline2.renderer, "render_to_pdf", return_value=True):
            pipeline2.run()

        # Não deve ter chamado translate novamente (cache hit)
        assert len(translator2.calls) == 0, (
            f"Esperado 0 chamadas no segundo run, obteve {len(translator2.calls)}"
        )
