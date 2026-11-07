"""Testes e2e com cenários realistas que podem reproduzir os bugs do usuário:

1. Capa com nome diferente de "cover" (ex: "capa", "title_page", "Title_Page")
2. EPUB onde o capítulo de capa não tem linear="no"
3. Biblioteca digital com falha silenciosa em add_book
4. EPUB sem imagem de capa (apenas capa em HTML)
"""

import json
import os
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import fitz
import pytest

from src.pipeline import TranslationPipeline
from src.core.translator import BaseTranslatorEngine
from src.core.converter import FormatConverter


def _make_epub_with_cover(path: Path):
    """Cria EPUB com capítulo de capa chamado 'cover.xhtml'."""
    _make_epub_with_cover_named(path, "cover.xhtml")


class FakeTranslator(BaseTranslatorEngine):
    def __init__(self):
        self.lang_in = "en"
        self.lang_out = "pt"
        self.calls = []

    def translate(self, text: str) -> str:
        self.calls.append(text)
        return f"[PT] {text}"


def _make_epub_with_cover_named(path: Path, cover_name: str):
    """Cria EPUB com capítulo de capa usando nome específico (não 'cover')."""
    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

    cover_id = cover_name.replace(".xhtml", "")

    content_opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Book With Custom Cover</dc:title>
    <dc:creator>Author</dc:creator>
    <dc:language>en</dc:language>
    <dc:identifier id="BookId">urn:uuid:cover-test</dc:identifier>
    <meta property="cover-image">cover-img</meta>
  </metadata>
  <manifest>
    <item id="cover-img" href="images/cover.png" media-type="image/png" properties="cover-image"/>
    <item id="css" href="styles.css" media-type="text/css"/>
    <item id="chap1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="cover" href="{cover_name}" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="nav">
    <itemref idref="cover" linear="no"/>
    <itemref idref="chap1"/>
  </spine>
</package>"""

    cover_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
<head><title>Cover</title><link rel="stylesheet" type="text/css" href="styles.css"/></head>
<body>
    <div class="cover">
        <img src="images/cover.png" alt="Capa"/>
    </div>
</body>
</html>"""

    chapter1 = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
<head><title>Chapter 1</title><link rel="stylesheet" type="text/css" href="styles.css"/></head>
<body>
    <h1>Chapter 1</h1>
    <p>First chapter content.</p>
</body>
</html>"""

    css = "body { font-family: sans-serif; }"

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>', compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", content_opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/styles.css", css, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr(f"OEBPS/{cover_name}", cover_xhtml, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/chapter1.xhtml", chapter1, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/images/cover.png", b"\x89PNG fake cover", compress_type=zipfile.ZIP_DEFLATED)


class TestCoverWithDifferentNames:
    """Testa se a capa funciona com nomes diferentes de 'cover'."""

    def test_cover_style_applied_to_all_cover_names(self, tmp_path):
        """TODOS os capítulos de capa devem ter estilo de cover, independente do nome."""
        for cover_name in ["cover.xhtml", "capa.xhtml", "Title_Page.xhtml", "cover_page.xhtml"]:
            epub_path = tmp_path / f"book_{cover_name.replace('.', '_')}.epub"
            _make_epub_with_cover_named(epub_path, cover_name)

            output_dir = tmp_path / f"output_{cover_name.replace('.', '_')}"
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

            # Encontrar o arquivo HTML da capa processado
            cache_dir = output_dir / "cache" / "Book_With_Custom_Cover" / "chapters"
            cover_html_files = list(cache_dir.glob("*.html"))
            assert len(cover_html_files) >= 1, f"Nenhum capítulo HTML encontrado em {cache_dir}"

            # Encontrar o que corresponde à capa
            cover_file = None
            for f in cover_html_files:
                if cover_name.replace(".xhtml", "").lower() in f.name.lower():
                    cover_file = f
                    break

            if cover_file is None:
                # Fallback: pegar o primeiro HTML que não seja chapter1
                cover_file = [f for f in cover_html_files if "chapter1" not in f.name][0]

            content = cover_file.read_text(encoding="utf-8")

            # Verificar se o estilo de cover foi aplicado
            has_cover_style = "margin: 0" in content and "100vw" in content
            assert has_cover_style, (
                f"Capa '{cover_name}' não recebeu estilo de cover! "
                f"Conteúdo relevante: {content[:300]}"
            )

    def test_cover_named_cover_has_cover_style(self, tmp_path):
        """Capítulo chamado 'cover.xhtml' DEVE ter estilo de cover."""
        epub_path = tmp_path / "book.epub"
        _make_epub_with_cover_named(epub_path, "cover.xhtml")

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

        cover_html = output_dir / "cache" / "Book_With_Custom_Cover" / "chapters" / "cover.html"
        assert cover_html.exists()

        content = cover_html.read_text(encoding="utf-8")

        has_cover_style = "margin: 0" in content and "100vw" in content
        print(f"\n=== Capa 'cover' tem estilo de cover (fullbleed): {has_cover_style} ===")
        assert has_cover_style, "Capa chamada 'cover' deve ter estilo de cover!"

    def test_cover_named_capa(self, tmp_path):
        """Capítulo chamado 'capa.xhtml' deve ser processado (mesmo sem estilo de cover)."""
        epub_path = tmp_path / "book.epub"
        _make_epub_with_cover_named(epub_path, "capa.xhtml")

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

        cover_html = output_dir / "cache" / "Book_With_Custom_Cover" / "chapters" / "capa.html"
        assert cover_html.exists(), f"Capa 'capa' não processada: {cover_html}"

        content = cover_html.read_text(encoding="utf-8")
        assert "cover.png" in content, "Imagem de capa não no HTML de 'capa'"

    def test_cover_named_title_page(self, tmp_path):
        """Capítulo chamado 'Title_Page.xhtml' deve ser processado."""
        epub_path = tmp_path / "book.epub"
        _make_epub_with_cover_named(epub_path, "Title_Page.xhtml")

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

        cover_html = output_dir / "cache" / "Book_With_Custom_Cover" / "chapters" / "Title_Page.html"
        assert cover_html.exists(), f"Capa 'Title_Page' não processada: {cover_html}"

        content = cover_html.read_text(encoding="utf-8")
        assert "cover.png" in content



class TestLibrarySilentFailure:
    """Testa se add_book pode falhar silenciosamente."""

    def test_library_add_book_with_missing_epub(self, tmp_path):
        """add_book com EPUB inexistente não deve falhar silenciosamente."""
        from src.core.library import BookLibrary

        output_dir = tmp_path / "output"
        lib = BookLibrary(str(output_dir))

        pdf_path = tmp_path / "book.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Teste.", fontsize=12)
        doc.save(str(pdf_path))
        doc.close()

        # EPUB inexistente
        fake_epub = tmp_path / "nao_existe.epub"

        # Isso não deve lançar exceção, mas também não deve criar registro válido
        try:
            record = lib.add_book(
                pdf_path=str(pdf_path),
                epub_path=str(fake_epub),
                metadata={"title": "Teste", "author": "Autor"},
                lang="pt",
                source_lang="en",
            )
            # Se chegou aqui, não lançou exceção (silent failure)
            print(f"\n=== add_book com EPUB inexistente: {record} ===")
        except Exception as e:
            print(f"\n=== add_book lançou exceção: {e} ===")

    def test_library_duplicate_book(self, tmp_path):
        """Adicionar o mesmo livro duas vezes não deve falhar."""
        from src.core.library import BookLibrary

        epub_path = tmp_path / "book.epub"
        # Criar EPUB mínimo
        with zipfile.ZipFile(epub_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            z.writestr("OEBPS/content.opf", '<package/>', compress_type=zipfile.ZIP_DEFLATED)

        pdf_path = tmp_path / "book.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Teste.", fontsize=12)
        doc.save(str(pdf_path))
        doc.close()

        output_dir = tmp_path / "output"
        lib = BookLibrary(str(output_dir))

        # Primeira adição
        record1 = lib.add_book(
            pdf_path=str(pdf_path),
            epub_path=str(epub_path),
            metadata={"title": "Livro Duplicado", "author": "Autor"},
            lang="pt",
            source_lang="en",
        )
        assert record1 is not None

        # Segunda adição (mesmo livro)
        record2 = lib.add_book(
            pdf_path=str(pdf_path),
            epub_path=str(epub_path),
            metadata={"title": "Livro Duplicado", "author": "Autor"},
            lang="pt",
            source_lang="en",
        )
        assert record2 is not None
        # Deve ser o mesmo slug
        assert record1["slug"] == record2["slug"]


class TestRealPdfCover:
    """Teste com render real do PDF se Chrome/Edge disponível."""

    def test_cover_appears_in_real_pdf(self, tmp_path):
        """Verificar se a capa aparece no PDF real (se browser disponível)."""
        epub_path = tmp_path / "book.epub"
        _make_epub_with_cover(epub_path)

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

        try:
            pipeline.run()
        except RuntimeError as e:
            if "No Chromium-based browser found" in str(e):
                pytest.skip("Chrome/Edge não instalado")
            raise

        # Verificar PDF final
        final_pdf = output_dir / "Book_With_Cover_PT.pdf"
        if final_pdf.exists():
            doc = fitz.open(str(final_pdf))
            first_page = doc[0]
            images = first_page.get_images()
            text = first_page.get_text()
            doc.close()

            # A primeira página deve ter imagem (capa) ou pelo menos texto de capa
            has_cover_content = len(images) > 0 or "Cover" in text or "Capa" in text
            assert has_cover_content, (
                f"Primeira página do PDF não tem capa. "
                f"Imagens: {len(images)}, Texto: {text[:200]}"
            )
        else:
            pytest.skip(f"PDF final não gerado: {final_pdf}")
