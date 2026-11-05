"""Testes unitários para o OcrToEpubPipeline (OCR de PDFs escaneados)."""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import fitz
import pytest

from src.ocr_pipeline import OcrToEpubPipeline


def _make_vector_pdf(path: Path, pages: int = 2):
    """Cria um PDF vetorial simples."""
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Página {i + 1} - conteúdo de teste.", fontsize=12)
    doc.save(str(path))
    doc.close()


class TestOcrToEpubPipelineInit:
    def test_default_values(self, tmp_path):
        pdf_path = tmp_path / "livro.pdf"
        _make_vector_pdf(pdf_path)

        pipeline = OcrToEpubPipeline(pdf_path=str(pdf_path))

        assert pipeline.pdf_path == str(pdf_path.resolve())
        assert pipeline.lang == "pt"
        assert pipeline.title == "Livro"
        assert pipeline.author == "Autor Desconhecido"
        assert pipeline.safe_slug == "Livro"
        assert os.path.isdir(pipeline.cache_dir)
        assert os.path.isdir(pipeline.assets_dir)

    def test_custom_title_author_lang(self, tmp_path):
        pdf_path = tmp_path / "livro.pdf"
        _make_vector_pdf(pdf_path)

        pipeline = OcrToEpubPipeline(
            pdf_path=str(pdf_path),
            lang="en",
            title="Meu Título",
            author="Meu Autor",
        )

        assert pipeline.lang == "en"
        assert pipeline.title == "Meu Título"
        assert pipeline.author == "Meu Autor"
        assert pipeline.safe_slug == "Meu_T_tulo"

    def test_raises_on_missing_pdf(self, tmp_path):
        missing = tmp_path / "nao_existe.pdf"
        pipeline = OcrToEpubPipeline(pdf_path=str(missing))
        with pytest.raises(FileNotFoundError):
            pipeline.run()


class TestOcrToEpubPipelineRun:
    def test_run_creates_epub(self, tmp_path):
        """Pipeline OCR deve gerar um EPUB válido."""
        pdf_path = tmp_path / "livro.pdf"
        _make_vector_pdf(pdf_path)

        output_dir = tmp_path / "output"

        # Mock de todos os componentes externos
        with patch("src.ocr_pipeline.ScannedPdfDetector.analyze",
                   return_value={"is_scanned": False, "total_pages": 2}):
            with patch("src.ocr_pipeline.LayoutOcrEngine") as mock_ocr_class:
                mock_ocr = MagicMock()
                mock_ocr.process_page.return_value = [
                    {"type": "paragraph", "text": "Parágrafo de teste."}
                ]
                mock_ocr_class.return_value = mock_ocr

                with patch("src.ocr_pipeline.EpubBuilder") as mock_builder_class:
                    mock_builder = MagicMock()
                    mock_builder_class.return_value = mock_builder

                    with patch("src.ocr_pipeline.EpubRefiner", create=True) as mock_refiner_class:
                        mock_refiner = MagicMock()
                        mock_refiner.refine.return_value = (
                            str(output_dir / "livro_OCR.epub"),
                            {"refined_chapters": 1, "code_blocks_merged": 0},
                        )
                        mock_refiner_class.return_value = mock_refiner

                        with patch("src.ocr_pipeline.BookLibrary") as mock_lib:
                            pipeline = OcrToEpubPipeline(
                                pdf_path=str(pdf_path),
                                output_dir=str(output_dir),
                                lang="pt",
                                title="Meu Livro",
                                author="Autor Teste",
                            )

                            # Cria o arquivo EPUB fake para que os.path.getsize funcione
                            os.makedirs(output_dir, exist_ok=True)
                            fake_epub = output_dir / "Meu_Livro_OCR.epub"
                            fake_epub.write_bytes(b"fake epub content")

                            final_epub, stats = pipeline.run()

                            assert final_epub is not None
                            assert stats["title"] == "Meu Livro"
                            assert stats["author"] == "Autor Teste"
                            assert stats["total_pages"] == 2

    def test_run_skips_cover_page_when_scanned(self, tmp_path):
        """Quando o PDF é escaneado, a página 0 (capa) é pulada no OCR."""
        pdf_path = tmp_path / "escaneado.pdf"
        _make_vector_pdf(pdf_path, pages=3)

        output_dir = tmp_path / "output"

        with patch("src.ocr_pipeline.ScannedPdfDetector.analyze",
                   return_value={"is_scanned": True, "total_pages": 3}):
            with patch("src.ocr_pipeline.LayoutOcrEngine") as mock_ocr_class:
                mock_ocr = MagicMock()
                mock_ocr.process_page.return_value = [
                    {"type": "paragraph", "text": "Conteúdo."}
                ]
                mock_ocr_class.return_value = mock_ocr

                with patch("src.ocr_pipeline.EpubBuilder") as mock_builder_class:
                    mock_builder = MagicMock()
                    mock_builder_class.return_value = mock_builder

                    with patch("src.ocr_pipeline.EpubRefiner", create=True) as mock_refiner_class:
                        mock_refiner = MagicMock()
                        mock_refiner.refine.return_value = (
                            str(output_dir / "livro_OCR.epub"),
                            {"refined_chapters": 1, "code_blocks_merged": 0},
                        )
                        mock_refiner_class.return_value = mock_refiner

                        with patch("src.ocr_pipeline.BookLibrary"):
                            pipeline = OcrToEpubPipeline(
                                pdf_path=str(pdf_path),
                                output_dir=str(output_dir),
                                lang="pt",
                            )

                            # Cria o arquivo EPUB fake para que os.path.getsize funcione
                            os.makedirs(output_dir, exist_ok=True)
                            fake_epub = output_dir / "Escaneado_OCR.epub"
                            fake_epub.write_bytes(b"fake epub content")

                            pipeline.run()

                            # start_page deve ser 1 quando escaneado (pula página 0/capa)
                            call_args = mock_ocr.process_page.call_args_list
                            page_nums = [c.kwargs["page_num"] for c in call_args]
                            assert 1 not in page_nums  # página 0 pulada

    def test_progress_callback_is_called(self, tmp_path):
        """Callback de progresso deve ser chamado durante o processamento."""
        pdf_path = tmp_path / "livro.pdf"
        _make_vector_pdf(pdf_path)

        output_dir = tmp_path / "output"

        progress_events = []

        def on_progress(percent, message):
            progress_events.append((percent, message))

        with patch("src.ocr_pipeline.ScannedPdfDetector.analyze",
                   return_value={"is_scanned": False, "total_pages": 1}):
            with patch("src.ocr_pipeline.LayoutOcrEngine") as mock_ocr_class:
                mock_ocr = MagicMock()
                mock_ocr.process_page.return_value = []
                mock_ocr_class.return_value = mock_ocr

                with patch("src.ocr_pipeline.EpubBuilder") as mock_builder_class:
                    mock_builder = MagicMock()
                    mock_builder_class.return_value = mock_builder

                    with patch("src.ocr_pipeline.EpubRefiner", create=True) as mock_refiner_class:
                        mock_refiner = MagicMock()
                        mock_refiner.refine.return_value = (
                            str(output_dir / "livro_OCR.epub"),
                            {"refined_chapters": 1, "code_blocks_merged": 0},
                        )
                        mock_refiner_class.return_value = mock_refiner

                        with patch("src.ocr_pipeline.BookLibrary"):
                            pipeline = OcrToEpubPipeline(
                                pdf_path=str(pdf_path),
                                output_dir=str(output_dir),
                                lang="pt",
                            )

                            # Cria o arquivo EPUB fake para que os.path.getsize funcione
                            os.makedirs(output_dir, exist_ok=True)
                            fake_epub = output_dir / "Livro_OCR.epub"
                            fake_epub.write_bytes(b"fake epub content")

                            pipeline.run(progress_callback=on_progress)

                            assert len(progress_events) > 0
                            assert progress_events[0][0] == 0.05
                            assert progress_events[-1][0] == 1.0

    def test_stats_include_epub_size(self, tmp_path):
        """Stats devem incluir o tamanho do EPUB em MB."""
        pdf_path = tmp_path / "livro.pdf"
        _make_vector_pdf(pdf_path)

        output_dir = tmp_path / "output"
        epub_path = output_dir / "livro_OCR.epub"

        # Criar um arquivo EPUB fake para calcular o tamanho
        os.makedirs(output_dir, exist_ok=True)
        epub_path.write_bytes(b"fake epub content " * 1000)

        with patch("src.ocr_pipeline.ScannedPdfDetector.analyze",
                   return_value={"is_scanned": False, "total_pages": 1}):
            with patch("src.ocr_pipeline.LayoutOcrEngine") as mock_ocr_class:
                mock_ocr = MagicMock()
                mock_ocr.process_page.return_value = []
                mock_ocr_class.return_value = mock_ocr

                with patch("src.ocr_pipeline.EpubBuilder") as mock_builder_class:
                    mock_builder = MagicMock()
                    mock_builder_class.return_value = mock_builder

                    with patch("src.ocr_pipeline.EpubRefiner", create=True) as mock_refiner_class:
                        mock_refiner = MagicMock()
                        mock_refiner.refine.return_value = (
                            str(epub_path),
                            {"refined_chapters": 1, "code_blocks_merged": 0},
                        )
                        mock_refiner_class.return_value = mock_refiner

                        with patch("src.ocr_pipeline.BookLibrary"):
                            pipeline = OcrToEpubPipeline(
                                pdf_path=str(pdf_path),
                                output_dir=str(output_dir),
                                lang="pt",
                            )
                            _, stats = pipeline.run()

                            assert "epub_size_mb" in stats
                            assert stats["epub_size_mb"] > 0
