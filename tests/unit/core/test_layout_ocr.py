"""Testes unitários para o LayoutOcrEngine (OCR de layout de páginas)."""

from unittest.mock import patch, MagicMock

import pytest

from src.core.layout_ocr import LayoutOcrEngine


class TestLayoutOcrEngineInit:
    def test_uses_latin_model_for_romance_languages(self, tmp_path):
        """Idiomas românicos/germânicos devem usar o modelo latino especializado."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "latin_PP-OCRv3_rec_infer.onnx").write_bytes(b"fake model")
        (models_dir / "latin_dict.txt").write_text("a\nb\nc\n")

        with patch.object(LayoutOcrEngine, "_ensure_models"):
            with patch("src.core.layout_ocr.RapidOCR") as mock_rapid:
                engine = LayoutOcrEngine(lang="pt", models_dir=str(models_dir))

                # Deve chamar RapidOCR com caminhos do modelo latino
                mock_rapid.assert_called_once_with(
                    rec_model_path=str(models_dir / "latin_PP-OCRv3_rec_infer.onnx"),
                    rec_keys_path=str(models_dir / "latin_dict.txt"),
                )
                assert engine.engine is not None

    def test_falls_back_to_default_when_no_latin_model(self, tmp_path):
        """Sem modelo latino, inicializa RapidOCR sem argumentos."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()

        with patch.object(LayoutOcrEngine, "_ensure_models"):
            with patch("src.core.layout_ocr.RapidOCR") as mock_rapid:
                engine = LayoutOcrEngine(lang="pt", models_dir=str(models_dir))

                mock_rapid.assert_called_once_with()
                assert engine.engine is not None

    def test_unsupported_language_uses_default(self, tmp_path):
        """Idioma não suportado pelo modelo latino usa RapidOCR padrão."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()

        with patch.object(LayoutOcrEngine, "_ensure_models"):
            with patch("src.core.layout_ocr.RapidOCR") as mock_rapid:
                engine = LayoutOcrEngine(lang="ar", models_dir=str(models_dir))  # árabe

                mock_rapid.assert_called_once_with()
                assert engine.engine is not None


class TestProcessPage:
    def _make_mock_page(self, page_w=600, page_h=800, pix_h=800):
        mock_page = MagicMock()
        mock_page.rect = MagicMock()
        mock_page.rect.width = page_w
        mock_page.rect.height = page_h
        mock_pix = MagicMock()
        mock_pix.height = pix_h
        mock_pix.tobytes.return_value = b"fake image bytes"
        mock_page.get_pixmap.return_value = mock_pix
        return mock_page

    def test_process_page_returns_blocks(self, tmp_path):
        """Processar uma página deve retornar lista de blocos semânticos."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()

        with patch.object(LayoutOcrEngine, "_ensure_models"):
            with patch("src.core.layout_ocr.RapidOCR") as mock_rapid:
                engine = LayoutOcrEngine(lang="pt", models_dir=str(models_dir))

                # Mock do RapidOCR retornando resultados
                fake_results = [
                    ([[0, 0], [100, 0], [100, 30], [0, 30]], "Capítulo 1", 0.95),
                    ([[0, 40], [200, 40], [200, 70], [0, 70]], "Este é um parágrafo de teste.", 0.90),
                ]
                engine.engine = MagicMock()
                engine.engine.return_value = (fake_results, None)

                mock_page = self._make_mock_page()

                blocks = engine.process_page(
                    page=mock_page,
                    page_num=1,
                    assets_output_dir=str(tmp_path / "assets"),
                    dpi=150,
                )

                assert isinstance(blocks, list)
                types = [b["type"] for b in blocks]
                assert "heading" in types
                assert "paragraph" in types

    def test_process_page_filters_low_confidence(self, tmp_path):
        """Caixas com confiança baixa (< 0.40) devem ser filtradas."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()

        with patch.object(LayoutOcrEngine, "_ensure_models"):
            with patch("src.core.layout_ocr.RapidOCR") as mock_rapid:
                engine = LayoutOcrEngine(lang="pt", models_dir=str(models_dir))

                fake_results = [
                    ([[0, 0], [100, 0], [100, 30], [0, 30]], "Texto ruim", 0.10),  # filtrado
                    ([[0, 40], [200, 40], [200, 70], [0, 70]], "Texto bom", 0.90),  # mantido
                ]
                engine.engine = MagicMock()
                engine.engine.return_value = (fake_results, None)

                mock_page = self._make_mock_page()

                blocks = engine.process_page(
                    page=mock_page,
                    page_num=1,
                    assets_output_dir=str(tmp_path / "assets"),
                    dpi=150,
                )

                texts = [b["text"] for b in blocks]
                assert "Texto bom" in texts
                assert "Texto ruim" not in texts

    def test_process_page_returns_empty_when_no_results(self, tmp_path):
        """Sem resultados do OCR deve retornar lista vazia."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()

        with patch.object(LayoutOcrEngine, "_ensure_models"):
            with patch("src.core.layout_ocr.RapidOCR") as mock_rapid:
                engine = LayoutOcrEngine(lang="pt", models_dir=str(models_dir))
                engine.engine = MagicMock()
                engine.engine.return_value = ([], None)

                mock_page = self._make_mock_page()

                blocks = engine.process_page(
                    page=mock_page,
                    page_num=1,
                    assets_output_dir=str(tmp_path / "assets"),
                    dpi=150,
                )

                assert blocks == []

    def test_process_page_raises_when_no_engine(self, tmp_path):
        """Sem engine inicializada deve lançar RuntimeError."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()

        with patch.object(LayoutOcrEngine, "_ensure_models"):
            with patch("src.core.layout_ocr.RapidOCR") as mock_rapid:
                engine = LayoutOcrEngine(lang="pt", models_dir=str(models_dir))
                engine.engine = None

                mock_page = self._make_mock_page()
                with pytest.raises(RuntimeError, match="RapidOCR engine is not initialized"):
                    engine.process_page(
                        page=mock_page,
                        page_num=1,
                        assets_output_dir=str(tmp_path / "assets"),
                        dpi=150,
                    )
