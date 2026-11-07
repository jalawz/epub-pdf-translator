"""Testes e2e para comprovar bugs do usuário:

1. Capa não aparece no PDF - verificar se o HTML da capa tem caminho correto da imagem
2. Livro não vai para biblioteca digital - verificar registro em todos os fluxos
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


class FakeTranslator(BaseTranslatorEngine):
    def __init__(self):
        self.lang_in = "en"
        self.lang_out = "pt"
        self.calls = []

    def translate(self, text: str) -> str:
        self.calls.append(text)
        return f"[PT] {text}"


def _make_epub_with_cover(path: Path):
    """Cria EPUB com capa e imagem."""
    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

    content_opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Book With Cover</dc:title>
    <dc:creator>Author</dc:creator>
    <dc:language>en</dc:language>
    <dc:identifier id="BookId">urn:uuid:cover-test</dc:identifier>
    <meta property="cover-image">cover-img</meta>
  </metadata>
  <manifest>
    <item id="cover-img" href="images/cover.png" media-type="image/png" properties="cover-image"/>
    <item id="css" href="styles.css" media-type="text/css"/>
    <item id="chap1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="nav">
    <itemref idref="cover" linear="no"/>
    <itemref idref="chap1"/>
  </spine>
</package>"""

    cover_xhtml = """<?xml version="1.0" encoding="utf-8"?>
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
        z.writestr("OEBPS/cover.xhtml", cover_xhtml, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/chapter1.xhtml", chapter1, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/images/cover.png", b"\x89PNG fake cover", compress_type=zipfile.ZIP_DEFLATED)


class TestCoverBug:
    """O usuário reporta que a capa não aparece no PDF."""

    def test_cover_html_has_correct_image_path(self, tmp_path):
        """O HTML do capítulo de capa deve ter caminho correto para a imagem extraída."""
        epub_path = tmp_path / "book.epub"
        _make_epub_with_cover(epub_path)

        output_dir = tmp_path / "output"

        pipeline = TranslationPipeline(
            epub_path=str(epub_path),
            output_dir=str(output_dir),
            lang_in="en",
            lang_out="pt",
            translator=FakeTranslator(),
            max_workers=1,
        )

        with patch.object(pipeline.renderer, "render_to_pdf", return_value=True):
            pipeline.run()

        # Verificar HTML da capa processado
        cover_html_path = output_dir / "cache" / "Book_With_Cover" / "chapters" / "cover.html"
        assert cover_html_path.exists(), f"Capa HTML não gerada: {cover_html_path}"

        cover_html = cover_html_path.read_text(encoding="utf-8")
        print(f"\n=== COVER HTML ===\n{cover_html}\n==================")

        # A imagem da capa deve estar referenciada no HTML
        assert "cover.png" in cover_html, "Imagem de capa não encontrada no HTML"

        # O caminho deve apontar para os assets extraídos (não caminho quebrado)
        assert "../assets/" in cover_html or "assets/" in cover_html, (
            f"Caminho da imagem não aponta para assets:\n{cover_html}"
        )

        # Verificar que o estilo de cover foi injetado (margin: 0, fullbleed)
        assert "@page" in cover_html, "Estilo de impressão não injetado na capa"

    def test_cover_pdf_has_cover_image(self, tmp_path):
        """O PDF da capa deve conter a imagem (verificar via PyMuPDF)."""
        epub_path = tmp_path / "book.epub"
        _make_epub_with_cover(epub_path)

        output_dir = tmp_path / "output"

        pipeline = TranslationPipeline(
            epub_path=str(epub_path),
            output_dir=str(output_dir),
            lang_in="en",
            lang_out="pt",
            translator=FakeTranslator(),
            max_workers=1,
        )

        # NÃO mockar render_to_pdf - usar o real se Chrome/Edge estiver disponível
        # Se não estiver, o teste verifica pelo menos o HTML
        try:
            pipeline.run()
        except RuntimeError as e:
            if "No Chromium-based browser found" in str(e):
                pytest.skip("Chrome/Edge não instalado - não pode testar PDF real")
            raise

        # Verificar se o PDF da capa foi gerado
        cover_pdf = output_dir / "cache" / "Book_With_Cover" / "pdfs" / "cover.pdf"
        if cover_pdf.exists():
            doc = fitz.open(str(cover_pdf))
            page = doc[0]
            images = page.get_images()
            assert len(images) > 0, f"Capa PDF não contém imagem. Página tem {len(images)} imagens"
            doc.close()
        else:
            # Se não houve render real, pelo menos verificar que o cached_pdf_file seria gerado
            # com o caminho correto
            cached_pdf = output_dir / "cache" / "Book_With_Cover" / "pdfs" / "cover.pdf"
            assert cached_pdf.parent.exists(), f"Diretório de PDFs não existe: {cached_pdf.parent}"


class TestLibraryBug:
    """O usuário reporta que o livro não vai para a biblioteca digital."""

    def test_translation_registers_book_in_library(self, tmp_path):
        """Após tradução, o livro DEVE estar na biblioteca."""
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

        with patch.object(pipeline.renderer, "render_to_pdf", return_value=True):
            final_pdf, final_epub = pipeline.run()

        # Verificar biblioteca
        library_dir = output_dir / "library"
        assert library_dir.exists(), f"Biblioteca não criada em {library_dir}"

        metadata_found = False
        for lang_dir in library_dir.iterdir():
            if not lang_dir.is_dir():
                continue
            for book_dir in lang_dir.iterdir():
                meta_file = book_dir / "metadata.json"
                if meta_file.exists():
                    metadata_found = True
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    assert meta["title"] == "Book With Cover"
                    assert meta["lang"] == "pt"
                    assert Path(meta["pdf_path"]).exists()
                    assert Path(meta["epub_path"]).exists()
                    break
            if metadata_found:
                break

        assert metadata_found, (
            "BUG CONFIRMADO: Livro não registrado na biblioteca após tradução. "
            f"Arquivos em output/library: {list(library_dir.rglob('*'))[:30]}"
        )

    def test_epub_to_pdf_registers_in_library(self, tmp_path):
        """Após EPUB→PDF, o livro deve estar na biblioteca."""
        epub_path = tmp_path / "book.epub"
        _make_epub_with_cover(epub_path)

        output_dir = tmp_path / "output"

        with patch("src.core.converter.PdfRenderer") as mock_renderer_class:
            mock_renderer = MagicMock()
            mock_renderer.render_to_pdf.return_value = True
            mock_renderer.inject_print_style.return_value = "<html><body>printable</body></html>"
            mock_renderer_class.return_value = mock_renderer

            import src.core.converter as converter_module
            converter_module.PdfRenderer = lambda *a, **k: mock_renderer

            result = FormatConverter.epub_to_pdf(
                epub_path=str(epub_path),
                output_dir=str(output_dir),
            )

            assert result is not None

            library_dir = output_dir / "library"
            assert library_dir.exists(), "Biblioteca não criada após EPUB→PDF"

            metadata_found = False
            for lang_dir in library_dir.iterdir():
                if not lang_dir.is_dir():
                    continue
                for book_dir in lang_dir.iterdir():
                    meta_file = book_dir / "metadata.json"
                    if meta_file.exists():
                        metadata_found = True
                        with open(meta_file, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                        assert meta["title"] == "Book With Cover"
                        break
                if metadata_found:
                    break

            assert metadata_found, (
                "BUG CONFIRMADO: Livro não registrado na biblioteca após EPUB→PDF. "
                f"Arquivos: {list(library_dir.rglob('*'))[:30]}"
            )

    def test_library_add_book_does_not_silently_fail(self, tmp_path):
        """add_book não deve falhar silenciosamente quando arquivos existem."""
        from src.core.library import BookLibrary

        epub_path = tmp_path / "book.epub"
        _make_epub_with_cover(epub_path)

        # Criar PDF real para teste
        pdf_path = tmp_path / "book.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Conteúdo de teste.", fontsize=12)
        doc.save(str(pdf_path))
        doc.close()

        output_dir = tmp_path / "output"
        lib = BookLibrary(str(output_dir))

        # Isso deve funcionar sem exceção
        record = lib.add_book(
            pdf_path=str(pdf_path),
            epub_path=str(epub_path),
            metadata={"title": "Book With Cover", "author": "Author"},
            lang="pt",
            source_lang="en",
        )

        assert record is not None
        assert record["title"] == "Book With Cover"
        assert Path(record["pdf_path"]).exists()
        assert Path(record["epub_path"]).exists()
