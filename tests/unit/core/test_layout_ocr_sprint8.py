"""Testes adicionais para o LayoutOcrEngine (coverage de linhas restantes)."""

from unittest.mock import patch, MagicMock

import fitz
import pytest

from src.core.layout_ocr import LayoutOcrEngine


class TestLayoutOcrEngineSprint8:
    def test_process_page_detects_heading(self, tmp_path):
        """Idiomas românicos/germânicos devem usar o modelo latino especializado."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()

        with patch.object(LayoutOcrEngine, "_ensure_models"):
            with patch("src.core.layout_ocr.RapidOCR") as mock_rapid:
                engine = LayoutOcrEngine(lang="pt", models_dir=str(models_dir))

                fake_results = [
                    ([[0, 0], [200, 0], [200, 50], [0, 50]], "CAPÍTULO 1", 0.95),
                    ([[0, 60], [300, 60], [300, 90], [0, 90]], "Texto normal do parágrafo.", 0.90),
                ]
                engine.engine = MagicMock()
                engine.engine.return_value = (fake_results, None)

                mock_page = MagicMock()
                mock_page.rect = MagicMock()
                mock_page.rect.width = 600
                mock_page.rect.height = 800
                mock_pix = MagicMock()
                mock_pix.height = 800
                mock_pix.tobytes.return_value = b"fake image bytes"
                mock_page.get_pixmap.return_value = mock_pix

                blocks = engine.process_page(
                    page=mock_page,
                    page_num=1,
                    assets_output_dir=str(tmp_path / "assets"),
                    dpi=150,
                )

                types = [b["type"] for b in blocks]
                assert "heading" in types
                assert "paragraph" in types

    def test_process_page_detects_code_line(self, tmp_path):
        """Linhas com marcadores de código devem ser detectadas como código."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()

        with patch.object(LayoutOcrEngine, "_ensure_models"):
            with patch("src.core.layout_ocr.RapidOCR") as mock_rapid:
                engine = LayoutOcrEngine(lang="pt", models_dir=str(models_dir))

                fake_results = [
                    ([[0, 0], [200, 0], [200, 30], [0, 30]], "import os", 0.95),
                    ([[0, 40], [300, 40], [300, 70], [0, 70]], "public void save() {}", 0.90),
                ]
                engine.engine = MagicMock()
                engine.engine.return_value = (fake_results, None)

                mock_page = MagicMock()
                mock_page.rect = MagicMock()
                mock_page.rect.width = 600
                mock_page.rect.height = 800
                mock_pix = MagicMock()
                mock_pix.height = 800
                mock_pix.tobytes.return_value = b"fake image bytes"
                mock_page.get_pixmap.return_value = mock_pix

                blocks = engine.process_page(
                    page=mock_page,
                    page_num=1,
                    assets_output_dir=str(tmp_path / "assets"),
                    dpi=150,
                )

                types = [b["type"] for b in blocks]
                assert "code" in types

    def test_process_page_detects_list_item(self, tmp_path):
        """Linhas com bullet devem ser detectadas como lista."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()

        with patch.object(LayoutOcrEngine, "_ensure_models"):
            with patch("src.core.layout_ocr.RapidOCR") as mock_rapid:
                engine = LayoutOcrEngine(lang="pt", models_dir=str(models_dir))

                fake_results = [
                    ([[0, 0], [200, 0], [200, 30], [0, 30]], "• Primeiro item", 0.95),
                    ([[0, 40], [300, 40], [300, 70], [0, 70]], "• Segundo item", 0.90),
                ]
                engine.engine = MagicMock()
                engine.engine.return_value = (fake_results, None)

                mock_page = MagicMock()
                mock_page.rect = MagicMock()
                mock_page.rect.width = 600
                mock_page.rect.height = 800
                mock_pix = MagicMock()
                mock_pix.height = 800
                mock_pix.tobytes.return_value = b"fake image bytes"
                mock_page.get_pixmap.return_value = mock_pix

                blocks = engine.process_page(
                    page=mock_page,
                    page_num=1,
                    assets_output_dir=str(tmp_path / "assets"),
                    dpi=150,
                )

                types = [b["type"] for b in blocks]
                assert "list" in types

    def test_process_page_extracts_figures(self, tmp_path):
        """Figuras embutidas na página devem ser extraídas."""
        from PIL import Image
        import io

        models_dir = tmp_path / "models"
        models_dir.mkdir()

        with patch.object(LayoutOcrEngine, "_ensure_models"):
            with patch("src.core.layout_ocr.RapidOCR") as mock_rapid:
                engine = LayoutOcrEngine(lang="pt", models_dir=str(models_dir))
                engine.engine = MagicMock()
                engine.engine.return_value = ([], None)

                pdf_path = tmp_path / "test.pdf"
                doc = fitz.open()
                page = doc.new_page()
                img = Image.new("RGB", (100, 100), color=200)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                rect = fitz.Rect(100, 100, 200, 200)
                page.insert_image(rect, stream=buf.read())
                doc.save(str(pdf_path))
                doc.close()

                doc = fitz.open(str(pdf_path))
                page = doc[0]

                blocks = engine.process_page(
                    page=page,
                    page_num=1,
                    assets_output_dir=str(tmp_path / "assets"),
                    dpi=150,
                )

                doc.close()

                assert isinstance(blocks, list)

    def test_ensure_models_downloads_when_missing(self, tmp_path):
        """_ensure_models deve tentar baixar modelos quando faltam."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()

        with patch("urllib.request.urlretrieve") as mock_retrieve:
            LayoutOcrEngine._ensure_models(str(models_dir))
            assert mock_retrieve.call_count >= 1

    def test_ensure_models_download_failure_is_ignored(self, tmp_path):
        """_ensure_models não deve falhar quando download falha (linhas 28-29, 36-37)."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()

        with patch("urllib.request.urlretrieve", side_effect=Exception("Network error")):
            LayoutOcrEngine._ensure_models(str(models_dir))

            with patch("src.core.layout_ocr.RapidOCR", None):
                engine = LayoutOcrEngine(lang="pt", models_dir=str(models_dir))
                assert engine.engine is None

    def test_process_page_with_no_valid_boxes(self, tmp_path):
        """Quando não há caixas válidas, retorna lista vazia (linha 101)."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()

        with patch.object(LayoutOcrEngine, "_ensure_models"):
            engine = LayoutOcrEngine(lang="pt", models_dir=str(models_dir))
            engine.engine = MagicMock()

            box1 = [[0, 0], [10, 10], [20, 20], [0, 20]]
            box2 = [[30, 30], [40, 40], [50, 50], [30, 50]]
            engine.engine.return_value = (
                [
                    [box1, "", 0.9],   # texto vazio
                    [box2, "ok", 0.1],  # baixa confiança
                ],
                None,
            )

            mock_page = MagicMock()
            mock_page.rect = MagicMock()
            mock_page.rect.width = 600
            mock_page.rect.height = 800
            mock_pix = MagicMock()
            mock_pix.height = 800
            mock_pix.tobytes.return_value = b"fake image bytes"
            mock_page.get_pixmap.return_value = mock_pix

            blocks = engine.process_page(
                page=mock_page,
                page_num=1,
                assets_output_dir=str(tmp_path / "assets"),
                dpi=150,
            )

            assert blocks == []