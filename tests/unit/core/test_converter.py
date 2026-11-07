"""Testes unitários para o FormatConverter (conversor EPUB <-> PDF)."""

import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import fitz
import pytest

from src.core.converter import FormatConverter


# ---------------------------------------------------------------------------
# Fixture de EPUB mínimo
# ---------------------------------------------------------------------------
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


class TestEpubToPdf:
    def test_epub_to_pdf_creates_output(self, tmp_path):
        """Converter EPUB válido deve gerar um PDF de saída."""
        epub_path = tmp_path / "livro.epub"
        _make_mini_epub(epub_path)

        output_dir = tmp_path / "output"

        with patch("src.core.converter.PdfRenderer") as mock_renderer_class:
            mock_renderer = MagicMock()
            mock_renderer.render_to_pdf.return_value = True
            mock_renderer.inject_print_style.return_value = "<html><body>printable</body></html>"
            mock_renderer_class.return_value = mock_renderer

            # Injetar mock no módulo converter
            import src.core.converter as converter_module
            converter_module.PdfRenderer = lambda *a, **k: mock_renderer

            result = FormatConverter.epub_to_pdf(
                epub_path=str(epub_path),
                output_dir=str(output_dir),
            )

            assert result is not None
            assert Path(result).exists()
            assert Path(result).suffix == ".pdf"

    def test_epub_to_pdf_raises_on_missing_file(self, tmp_path):
        """EPUB inexistente deve lançar FileNotFoundError."""
        missing = tmp_path / "nao_existe.epub"
        with pytest.raises(FileNotFoundError):
            FormatConverter.epub_to_pdf(
                epub_path=str(missing),
                output_dir=str(tmp_path / "output"),
            )

    def test_epub_to_pdf_preserves_language(self, tmp_path):
        """O idioma do EPUB deve ser preservado na biblioteca."""
        epub_path = tmp_path / "livro_fr.epub"
        _make_mini_epub(epub_path, title="Livro Francês")

        output_dir = tmp_path / "output"

        with patch("src.core.converter.PdfRenderer") as mock_renderer_class:
            mock_renderer = MagicMock()
            mock_renderer.render_to_pdf.return_value = True
            mock_renderer.inject_print_style.return_value = "<html><body>printable</body></html>"
            mock_renderer_class.return_value = mock_renderer

            import src.core.converter as converter_module
            converter_module.PdfRenderer = lambda *a, **k: mock_renderer

            with patch("src.core.converter.BookLibrary") as mock_lib:
                FormatConverter.epub_to_pdf(
                    epub_path=str(epub_path),
                    output_dir=str(output_dir),
                )
                # Verifica que add_book foi chamado com lang correto
                call_kwargs = mock_lib.return_value.add_book.call_args.kwargs
                assert call_kwargs["lang"] == "pt"  # hardcodeado no converter
                assert call_kwargs["source_lang"] == "pt"  # hardcodeado no converter


class TestPdfToEpubVector:
    def test_pdf_to_epub_vector_creates_output(self, tmp_path):
        """PDF vetorial deve ser convertido para EPUB."""
        pdf_path = tmp_path / "livro.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Capítulo 1\nConteúdo da página 1.\nConteúdo da página 2.")
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
        assert Path(result_epub).suffix == ".epub"
        assert stats["is_scanned"] is False
        assert stats["total_pages"] == 1

    def test_pdf_to_epub_raises_on_missing_file(self, tmp_path):
        """PDF inexistente deve lançar FileNotFoundError."""
        missing = tmp_path / "nao_existe.pdf"
        with pytest.raises(FileNotFoundError):
            FormatConverter.pdf_to_epub(
                pdf_path=str(missing),
                output_dir=str(tmp_path / "output"),
            )

    def test_pdf_to_epub_detects_chapters(self, tmp_path):
        """PDF com linhas 'Capítulo X' deve criar capítulos separados."""
        pdf_path = tmp_path / "com_capitulos.pdf"
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

        assert stats["chapters_created"] >= 2

    def test_pdf_to_epub_scanned_uses_ocr_pipeline(self, tmp_path):
        """PDF escaneado deve usar o OcrToEpubPipeline."""
        pdf_path = tmp_path / "escaneado.pdf"
        # Criar PDF com imagem grande e pouco texto (simula escaneado)
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "x", fontsize=12)  # texto mínimo
        doc.save(str(pdf_path))
        doc.close()

        output_dir = tmp_path / "output"

        with patch("src.core.converter.OcrToEpubPipeline") as mock_ocr_class:
            mock_ocr = MagicMock()
            mock_ocr.run.return_value = (str(tmp_path / "output" / "livro.epub"), {"title": "x", "is_scanned": True})
            mock_ocr_class.return_value = mock_ocr

            import src.core.converter as converter_module
            # Simular que ScannedPdfDetector detecta como escaneado
            with patch("src.core.converter.ScannedPdfDetector.analyze", return_value={"is_scanned": True, "total_pages": 1}):
                result_epub, stats = FormatConverter.pdf_to_epub(
                    pdf_path=str(pdf_path),
                    output_dir=str(output_dir),
                    lang="pt",
                )

                mock_ocr_class.assert_called_once()
                assert stats.get("is_scanned") is True
