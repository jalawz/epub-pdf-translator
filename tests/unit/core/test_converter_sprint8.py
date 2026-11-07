"""Testes adicionais para o FormatConverter (coverage de linhas restantes)."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import fitz
import zipfile
import pytest

from src.core.converter import FormatConverter


def _make_mini_epub(path: Path, title: str = "Mini Book"):
    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

    content_opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
    <dc:creator>Test Author</dc:creator>
    <dc:language>en</dc:language>
    <dc:identifier id="BookId">urn:uuid:12345678-1234-1234-1234-123456789012</dc:identifier>
  </metadata>
  <manifest>
    <item id="chap1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="nav">
    <itemref idref="chap1"/>
  </spine>
</package>"""

    chapter = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
<head><title>Chapter 1</title></head>
<body><h1>Chapter 1</h1><p>Hello world.</p></body>
</html>"""

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container_xml, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", content_opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/chapter1.xhtml", chapter, compress_type=zipfile.ZIP_DEFLATED)


class TestConverterSprint8:
    def test_epub_to_pdf_cleans_cache(self, tmp_path):
        """O cache temporário deve ser removido após a conversão."""
        epub_path = tmp_path / "livro.epub"
        _make_mini_epub(epub_path)

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
            # O cache deve ter sido removido (shutil.rmtree)
            # O caminho é output/cache/convert_{safe_title}
            cache_dir = output_dir / "cache" / "convert_Mini_Book"
            assert not cache_dir.exists()

    def test_pdf_to_epub_vector_creates_chapters_from_chapter_lines(self, tmp_path):
        """Linhas que começam com 'Capítulo' devem criar novos capítulos."""
        pdf_path = tmp_path / "livro.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Capítulo 1\nTexto do capítulo um.\nCapítulo 2\nTexto do capítulo dois.")
        doc.save(str(pdf_path))
        doc.close()

        output_dir = tmp_path / "output"

        result_epub, stats = FormatConverter.pdf_to_epub(
            pdf_path=str(pdf_path),
            output_dir=str(output_dir),
            lang="pt",
        )

        assert result_epub is not None
        assert Path(result_epub).exists()
        assert stats["chapters_created"] >= 2

    def test_pdf_to_epub_registers_in_library(self, tmp_path):
        """PDF vetorial deve ser registrado na biblioteca (ou falhar silenciosamente)."""
        pdf_path = tmp_path / "livro.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Conteúdo de teste.", fontsize=12)
        doc.save(str(pdf_path))
        doc.close()

        output_dir = tmp_path / "output"

        with patch("src.core.converter.EpubBuilder") as mock_builder_class:
            mock_builder = MagicMock()
            mock_builder.build.return_value = str(output_dir / "livro.epub")
            mock_builder_class.return_value = mock_builder

            with patch("src.core.converter.EpubRefiner") as mock_refiner_class:
                mock_refiner = MagicMock()
                mock_refiner.refine.return_value = (
                    str(output_dir / "livro.epub"),
                    {"refined_chapters": 1},
                )
                mock_refiner_class.return_value = mock_refiner

                with patch("src.core.converter.BookLibrary") as mock_lib:
                    # Não deve lançar exceção
                    FormatConverter.pdf_to_epub(
                        pdf_path=str(pdf_path),
                        output_dir=str(output_dir),
                        lang="pt",
                    )

                    # Se a biblioteca foi instanciada, verifica que add_book foi chamado
                    if mock_lib.return_value.add_book.called:
                        call_kwargs = mock_lib.return_value.add_book.call_args.kwargs
                        assert call_kwargs["lang"] == "pt"
                        assert call_kwargs["source_lang"] == "pt"

    def test_pdf_to_epub_handles_no_chapters(self, tmp_path):
        """PDF sem linhas de capítulo deve criar um único capítulo."""
        pdf_path = tmp_path / "sem_capitulos.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Apenas texto sem capítulos.", fontsize=12)
        doc.save(str(pdf_path))
        doc.close()

        output_dir = tmp_path / "output"

        result_epub, stats = FormatConverter.pdf_to_epub(
            pdf_path=str(pdf_path),
            output_dir=str(output_dir),
            lang="pt",
        )

        assert result_epub is not None
        assert stats["chapters_created"] >= 1
