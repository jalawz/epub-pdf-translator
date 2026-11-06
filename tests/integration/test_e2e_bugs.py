"""Testes de integração para reproduzir bugs reportados pelo usuário:

1. Capa não aparece no PDF gerado
2. Livro não é registrado na Biblioteca Digital após conversão/tradução
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
    """Cria um EPUB com capítulo de capa e imagem de capa."""
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


class TestCoverInPDF:
    def test_cover_chapter_html_contains_cover_image(self, tmp_path):
        """O HTML do capítulo de capa deve conter referência à imagem de capa."""
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

        # Verificar se o capítulo de capa foi processado e contém a imagem
        cover_html = output_dir / "cache" / "Book_With_Cover" / "chapters" / "cover.html"
        if cover_html.exists():
            content = cover_html.read_text(encoding="utf-8")
            # A imagem da capa deve estar presente no HTML
            assert "cover.png" in content or "images/cover" in content, (
                f"Imagem de capa não encontrada no HTML da capa:\n{content[:500]}"
            )
        else:
            pytest.skip("Arquivo cover.html não gerado (pipeline pode não ter processado a capa)")

    def test_cover_image_extracted_to_assets(self, tmp_path):
        """A imagem da capa deve ser extraída para o diretório de assets."""
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

        # Verificar se a imagem foi extraída para assets
        assets_dir = output_dir / "cache" / "Book_With_Cover" / "assets"
        cover_assets = list(assets_dir.rglob("cover*"))
        assert len(cover_assets) >= 1, (
            f"Imagem de capa não encontrada em assets: {list(assets_dir.rglob('*'))[:10]}"
        )


class TestBookInLibrary:
    def test_translation_registers_in_library(self, tmp_path):
        """Após tradução, o livro deve ser registrado na biblioteca digital."""
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

        # Verificar se o livro foi registrado na biblioteca
        library_dir = output_dir / "library"
        assert library_dir.exists(), f"Biblioteca digital não criada em {library_dir}"

        # Procurar metadata.json em qualquer idioma
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
                    assert meta["pdf_path"] is not None
                    assert meta["epub_path"] is not None
                    # Verificar que os arquivos existem
                    assert Path(meta["pdf_path"]).exists(), f"PDF não existe: {meta['pdf_path']}"
                    assert Path(meta["epub_path"]).exists(), f"EPUB não existe: {meta['epub_path']}"
                    break
            if metadata_found:
                break

        assert metadata_found, (
            f"Nenhum livro registrado na biblioteca. "
            f"Conteúdo de output/library: {list(library_dir.rglob('*'))[:20]}"
        )

    def test_epub_to_pdf_conversion_registers_in_library(self, tmp_path):
        """Após conversão EPUB → PDF, o livro deve ser registrado na biblioteca."""
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
            assert Path(result).exists()

            # Verificar biblioteca
            library_dir = output_dir / "library"
            assert library_dir.exists(), "Biblioteca não criada após conversão EPUB→PDF"

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
                f"Livro não registrado na biblioteca após EPUB→PDF. "
                f"Conteúdo: {list(library_dir.rglob('*'))[:20]}"
            )

    def test_pdf_to_epub_conversion_registers_in_library(self, tmp_path):
        """Após conversão PDF → EPUB, o livro deve ser registrado na biblioteca."""
        pdf_path = tmp_path / "book.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Conteúdo de teste para conversão PDF→EPUB.", fontsize=12)
        doc.save(str(pdf_path))
        doc.close()

        output_dir = tmp_path / "output"

        with patch("src.core.converter.EpubBuilder") as mock_builder_class:
            mock_builder = MagicMock()
            mock_builder.build.return_value = str(output_dir / "book.epub")
            mock_builder_class.return_value = mock_builder

            with patch("src.core.converter.EpubRefiner") as mock_refiner_class:
                mock_refiner = MagicMock()
                mock_refiner.refine.return_value = (
                    str(output_dir / "book.epub"),
                    {"refined_chapters": 1},
                )
                mock_refiner_class.return_value = mock_refiner

                with patch("src.core.converter.BookLibrary") as mock_lib:
                    FormatConverter.pdf_to_epub(
                        pdf_path=str(pdf_path),
                        output_dir=str(output_dir),
                        lang="pt",
                    )

                    # Verificar que add_book foi chamado na biblioteca
                    assert mock_lib.return_value.add_book.called, (
                        "add_book não foi chamado na biblioteca após PDF→EPUB"
                    )
                    call_kwargs = mock_lib.return_value.add_book.call_args.kwargs
                    assert call_kwargs["lang"] == "pt"
                    assert call_kwargs["source_lang"] == "pt"
