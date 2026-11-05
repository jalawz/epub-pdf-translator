"""Testes unitários para o ScannedPdfDetector."""

import fitz
import pytest

from src.core.scanned_detector import ScannedPdfDetector


class TestScannedPdfDetectorAnalyze:
    def test_raises_on_missing_file(self, tmp_path):
        missing = tmp_path / "nao_existe.pdf"
        with pytest.raises(FileNotFoundError):
            ScannedPdfDetector.analyze(str(missing))

    def test_vector_pdf_is_not_scanned(self, tmp_path):
        pdf_path = tmp_path / "vetorial.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Texto vetorial real com muitas palavras aqui.", fontsize=12)
        doc.save(str(pdf_path))
        doc.close()

        result = ScannedPdfDetector.analyze(str(pdf_path))

        assert result["is_scanned"] is False
        assert result["total_pages"] == 1
        assert result["avg_text_chars"] > 0
        assert result["confidence"] > 0.5

    def test_scanned_pdf_is_detected(self, tmp_path):
        from PIL import Image
        import io

        pdf_path = tmp_path / "escaneado.pdf"
        doc = fitz.open()
        page = doc.new_page()
        # Página com imagem grande e sem texto vetorial (simula escaneado)
        img = Image.new("L", (200, 200), color=200)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        rect_insert = fitz.Rect(0, 0, page.rect.width, page.rect.height)
        page.insert_image(rect_insert, stream=buf.read())
        doc.save(str(pdf_path))
        doc.close()

        result = ScannedPdfDetector.analyze(str(pdf_path))

        assert result["is_scanned"] is True
        assert result["raster_page_ratio"] >= 0.6
        assert result["total_pages"] == 1

    def test_empty_pdf_returns_false(self, tmp_path):
        pdf_path = tmp_path / "vazio.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Este é um texto real em português do Brasil para teste.", fontsize=12)
        doc.save(str(pdf_path))
        doc.close()

        result = ScannedPdfDetector.analyze(str(pdf_path))

        assert result["is_scanned"] is False
        assert result["total_pages"] == 1
        assert result["avg_text_chars"] > 0

    def test_result_has_expected_keys(self, tmp_path):
        pdf_path = tmp_path / "teste.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "algum texto", fontsize=12)
        doc.save(str(pdf_path))
        doc.close()

        result = ScannedPdfDetector.analyze(str(pdf_path))

        expected_keys = {
            "is_scanned", "total_pages", "sample_pages",
            "avg_text_chars", "raster_page_ratio", "confidence",
        }
        assert set(result.keys()) == expected_keys
        assert isinstance(result["is_scanned"], bool)
        assert isinstance(result["confidence"], float)
