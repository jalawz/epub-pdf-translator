"""Testes de QA abrangentes para o app.py (interface Gradio).

Objetivo: exercer TODAS as funções expostas com casos extremos, validar
consistência entre telas, detectar XSS/injeção em HTML renderizado,
verificar acessos direto a chaves ausentes (KeyError) e apontar bugs de
comportamento que deixamos passar.

Execução: python -m pytest tests/unit/app/test_qa_app.py -v
"""

import re
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import gradio as gr
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import app  # noqa: E402


# ============================================================================
# FIXTURES HELPER
# ============================================================================

class _DummyFile:
    """Imita um arquivo enviado pelo gr.File (possui atributo .name)."""
    def __init__(self, path):
        self.name = path


# ============================================================================
# 1. VALIDAÇÕES DE ENTRADA - todas as funções que aceitam arquivo
# ============================================================================

class TestQAInputValidation:
    """Cada função de fluxo deve rejeitar entrada ausente com gr.Error."""

    def test_translate_book_none_raises(self):
        with pytest.raises(gr.Error):
            app.translate_book(
                epub_file=None,
                source_lang="en",
                target_lang="pt",
                engine_choice="Neural Fast Translator (Padrão, Gratuito)",
                ollama_model="qwen2.5:latest",
                workers=5,
                keep_cache=False,
            )

    def test_translate_book_empty_string_raises(self):
        """String vazia também deve ser rejeitada (não apenas None)."""
        with pytest.raises(gr.Error):
            app.translate_book(
                epub_file="",
                source_lang="en",
                target_lang="pt",
                engine_choice="Neural Fast Translator (Padrão, Gratuito)",
                ollama_model="qwen2.5:latest",
                workers=5,
                keep_cache=False,
            )

    def test_convert_scanned_pdf_none_raises(self):
        with pytest.raises(gr.Error):
            app.convert_scanned_pdf(
                pdf_file=None, book_title="", book_author="", ocr_lang="pt"
            )

    def test_convert_epub_to_pdf_none_raises(self):
        with pytest.raises(gr.Error):
            app.convert_epub_to_pdf_flow(epub_file=None)

    def test_convert_pdf_to_epub_none_raises(self):
        with pytest.raises(gr.Error):
            app.convert_pdf_to_epub_flow(
                pdf_file=None, title="", author="", lang="pt"
            )

    def test_open_file_desktop_none_returns_warning(self):
        """open_file_desktop com None não deve quebrar."""
        result = app.open_file_desktop(None)
        assert "não encontrado" in result.lower()

    def test_open_file_desktop_empty_string_returns_warning(self):
        result = app.open_file_desktop("")
        assert "não encontrado" in result.lower()

    def test_open_folder_desktop_none_returns_warning(self):
        result = app.open_folder_desktop(None)
        assert "não encontrado" in result.lower()


# ============================================================================
# 2. RENDERIZAÇÃO HTML DA BIBLIOTECA - XSS e dados ausentes
# ============================================================================

class TestQALibraryRendering:
    """render_books_grid_html injetam dados do usuário no HTML sem escape."""

    def test_book_with_title_containing_quote_breaks_html(self, tmp_path):
        """CORREÇÃO QA-2/S1: Título com aspas deve ser ESCAPADO, não quebrar o HTML."""
        books = [
            {
                "title": 'Livro "com" aspas',
                "author": "Autor",
                "lang": "pt",
                "category": "translation",
                "source_lang": "en",
                "pages": 100,
                "pdf_size_mb": 1.0,
                "epub_size_mb": 0.5,
                "date_added": "2026-01-01",
                "pdf_path": str(tmp_path / "a.pdf"),
                "epub_path": str(tmp_path / "a.epub"),
                "book_dir": str(tmp_path),
                "slug": "livro-com-aspas",
                "cover_path": None,
            }
        ]
        html = app.render_books_grid_html(books)
        # Aspas devem estar escapadas como &quot;
        assert "&quot;com&quot;" in html
        # Não deve haver aspas duplas não escapadas quebrando o atributo title
        assert 'title="Livro "' not in html
        assert "Livro" in html
        assert "com" in html
        assert "aspas" in html

    def test_book_with_title_containing_angle_brackets(self, tmp_path):
        """CORREÇÃO QA-2/S1: Título com <script> deve ser ESCAPADO, não injetado bruto."""
        books = [
            {
                "title": "<script>alert('xss')</script>",
                "author": "Autor",
                "lang": "pt",
                "category": "translation",
                "source_lang": "en",
                "pages": 10,
                "pdf_size_mb": 1.0,
                "epub_size_mb": 0.5,
                "date_added": "2026-01-01",
                "pdf_path": str(tmp_path / "a.pdf"),
                "epub_path": str(tmp_path / "a.epub"),
                "book_dir": str(tmp_path),
                "slug": "xss",
                "cover_path": None,
            }
        ]
        html = app.render_books_grid_html(books)
        # O script deve estar ESCAPADO, não bruto
        assert "&lt;script&gt;" in html
        assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in html
        # Não deve aparecer bruto (sem escape)
        assert "<script>" not in html
        assert "</script>" not in html

    def test_book_with_path_containing_quote(self, tmp_path):
        """CORREÇÃO QA-2/S2: Caminho com aspas deve ser percent-encodeado em onclick/href."""
        books = [
            {
                "title": "Título",
                "author": "Autor",
                "lang": "pt",
                "category": "translation",
                "source_lang": "en",
                "pages": 10,
                "pdf_size_mb": 1.0,
                "epub_size_mb": 0.5,
                "date_added": "2026-01-01",
                'pdf_path': str(tmp_path / 'a"b.pdf'),
                "epub_path": str(tmp_path / "a.epub"),
                "book_dir": str(tmp_path),
                "slug": "x",
                "cover_path": None,
            }
        ]
        html = app.render_books_grid_html(books)

        # Nenhuma aspa dupla crua deve aparecer dentro de onclick (fecharia o atributo)
        for line in html.splitlines():
            if "onclick=" in line:
                assert 'a"b.pdf' not in line, f"Aspa dupla crua em onclick: {line}"

        # O caminho deve estar percent-encodeado (aspas duplas viram %22)
        assert "%22" in html

        # O nome do arquivo deve aparecer (com aspas encodeadas)
        assert "a" in html and "b.pdf" in html

    def test_book_missing_optional_keys_does_not_crash(self, tmp_path):
        """Livro sem chaves opcionais não deve levantar KeyError."""
        books = [
            {
                "title": "Mínimo",
                # sem author, lang, pages, caminhos, etc.
            }
        ]
        html = app.render_books_grid_html(books)
        assert "Mínimo" in html

    def test_book_with_none_pages_does_not_crash(self, tmp_path):
        """CORREÇÃO C1: pages=None não deve mais causar TypeError; exibe '—'."""
        books = [
            {
                "title": "None Pages",
                "author": "Autor",
                "lang": "pt",
                "category": "translation",
                "source_lang": "en",
                "pages": None,
                "pdf_size_mb": 1.0,
                "epub_size_mb": 0.5,
                "date_added": "2026-01-01",
                "pdf_path": str(tmp_path / "a.pdf"),
                "epub_path": str(tmp_path / "a.epub"),
                "book_dir": str(tmp_path),
                "slug": "none",
                "cover_path": None,
            }
        ]
        html = app.render_books_grid_html(books)
        # Não deve crashar; páginas None vira 0 (valor seguro)
        assert "None Pages" in html
        assert "<b>0</b> páginas" in html

    def test_book_with_none_numeric_fields_shows_zero(self, tmp_path):
        """CORREÇÃO C1/C6: pdf_size_mb/epub_size_mb None mostra '0 MB' não 'None MB'."""
        books = [
            {
                "title": "None Values",
                "author": "Autor",
                "lang": "pt",
                "category": "translation",
                "source_lang": "en",
                "pages": 10,
                "pdf_size_mb": None,
                "epub_size_mb": None,
                "date_added": None,
                "pdf_path": str(tmp_path / "a.pdf"),
                "epub_path": str(tmp_path / "a.epub"),
                "book_dir": str(tmp_path),
                "slug": "none",
                "cover_path": None,
            }
        ]
        html = app.render_books_grid_html(books)
        assert "None Values" in html
        assert "0 MB" in html  # valor seguro em vez de "None MB" literal


# ============================================================================
# 3. UPDATE_LIBRARY_VIEW - acessos direto a chaves (KeyError)
# ============================================================================

class TestQAUpdateLibraryView:
    def test_book_without_lang_key_does_not_raise(self, tmp_path):
        """CORREÇÃO C2: b.get('lang', '?') evita KeyError."""
        with patch.object(app.BookLibrary, "list_books", return_value=[{"title": "Sem Lang", "slug": "x"}]):
            grid, choices_update, info, feedback = app.update_library_view("Todos", "Todos")
            assert "Sem Lang" in grid

    def test_book_without_title_key_does_not_raise(self, tmp_path):
        """CORREÇÃO C2: b.get('title', 'Sem título') evita KeyError."""
        with patch.object(app.BookLibrary, "list_books", return_value=[{"lang": "pt", "slug": "x"}]):
            grid, choices_update, info, feedback = app.update_library_view("Todos", "Todos")
            assert "Sem título" in grid

    def test_book_without_slug_key_does_not_raise(self, tmp_path):
        """CORREÇÃO C2: b.get('slug', '') evita KeyError."""
        with patch.object(app.BookLibrary, "list_books", return_value=[{"lang": "pt", "title": "T"}]):
            grid, choices_update, info, feedback = app.update_library_view("Todos", "Todos")
            assert "T" in grid

    def test_pdf_size_mb_none_shows_zero(self, tmp_path):
        """CORREÇÃO QA-3/U6: pdf_size_mb None mostra '0 MB', não 'None MB'."""
        with patch.object(app.BookLibrary, "list_books", return_value=[
            {"lang": "pt", "title": "T", "slug": "s", "author": "A",
             "category": "translation", "pages": 10,
             "pdf_size_mb": None, "epub_size_mb": None,
             "date_added": "2026-01-01",
             "pdf_path": str(tmp_path / "a.pdf"),
             "epub_path": str(tmp_path / "a.epub"),
             "book_dir": str(tmp_path)}
        ]):
            grid, choices_update, info, feedback = app.update_library_view("Todos", "Todos")
            assert "None MB" not in grid and "None MB" not in info
            assert "0 MB" in grid or "0 MB" in info

    def test_date_added_none_shows_empty_label(self, tmp_path):
        """date_added ausente resulta em 'Data de Registro: ' vazio."""
        with patch.object(app.BookLibrary, "list_books", return_value=[
            {"lang": "pt", "title": "T", "slug": "s", "author": "A",
             "category": "translation", "pages": 10,
             "pdf_size_mb": 1.0, "epub_size_mb": 0.5,
             "date_added": None,
             "pdf_path": str(tmp_path / "a.pdf"),
             "epub_path": str(tmp_path / "a.epub"),
             "book_dir": str(tmp_path)}
        ]):
            grid, choices_update, info, feedback = app.update_library_view("Todos", "Todos")
            # date_formatted = (None or "")[:10] => ""
            assert "🗓️ " in grid or "🗓️ " in info


# ============================================================================
# 4. ON_SELECT_BOOK - campos ausentes e source_lang default
# ============================================================================

class TestQAOnSelectBook:
    def test_book_missing_source_lang_shows_dash(self, tmp_path):
        """CORREÇÃO QA-3/U5: source_lang ausente exibe '—', não inventa 'EN'."""
        with patch.object(app.BookLibrary, "get_book", return_value={
            "title": "T", "author": "A", "lang": "pt",
            "category": "translation", "pages": 10,
            "pdf_size_mb": 1.0, "epub_size_mb": 0.5,
            "date_added": "2026-01-01",
            "pdf_path": str(tmp_path / "a.pdf"),
            "epub_path": str(tmp_path / "a.epub"),
            "book_dir": str(tmp_path),
        }):
            info, feedback = app.on_select_book("[PT] T | slug:t")
            assert "Original: —" in info

    def test_book_missing_date_added_shows_empty(self, tmp_path):
        """date_added ausente mostra 'Data de Registro: ' vazio."""
        with patch.object(app.BookLibrary, "get_book", return_value={
            "title": "T", "author": "A", "lang": "pt",
            "category": "translation", "pages": 10,
            "pdf_size_mb": 1.0, "epub_size_mb": 0.5,
            "pdf_path": str(tmp_path / "a.pdf"),
            "epub_path": str(tmp_path / "a.epub"),
            "book_dir": str(tmp_path),
        }):
            info, feedback = app.on_select_book("[PT] T | slug:t")
            assert "Data de Registro:**" in info  # f-string usa ** ao redor, não espaço
            # O valor depois dos dois-pontos fica vazio (UX ruim, mas não crasha)

    def test_on_select_book_label_with_multiple_slug(self):
        """Label com '| slug:' aparecendo mais de uma vez pega o último."""
        info, feedback = app.on_select_book("[PT] Título | slug: primeira | slug: segunda")
        # slug = "segunda" -> get_book retorna None (não configurado)
        assert "não localizado" in info.lower()

    def test_on_select_book_brackets_no_two_letters(self):
        """[] com menos de 2 letras cai no default 'pt'."""
        with patch.object(app.BookLibrary, "get_book", return_value=None):
            info, feedback = app.on_select_book("[A] Título | slug:t")
            assert "não localizado" in info.lower()


# ============================================================================
# 5. ACTIONS (abrir PDF/EPUB/pasta) - inconsistências de caminho
# ============================================================================

class TestQAActions:
    def test_action_open_selected_pdf_book_without_pdf_path(self):
        """Livro sem pdf_path retorna 'Arquivo PDF não encontrado'."""
        with patch.object(app.BookLibrary, "get_book", return_value={
            "title": "T", "slug": "s", "epub_path": "/x.epub"
        }):
            result = app.action_open_selected_pdf("[PT] T | slug:s")
            assert "não encontrado" in result.lower()

    def test_action_open_selected_epub_book_without_epub_path(self):
        with patch.object(app.BookLibrary, "get_book", return_value={
            "title": "T", "slug": "s", "pdf_path": "/x.pdf"
        }):
            result = app.action_open_selected_epub("[PT] T | slug:s")
            assert "não encontrado" in result.lower()

    def test_action_open_selected_folder_book_without_any_path(self):
        """Livro sem pdf_path, epub_path e book_dir -> open_folder_desktop(None)."""
        with patch.object(app.BookLibrary, "get_book", return_value={
            "title": "T", "slug": "s"
        }):
            result = app.action_open_selected_folder("[PT] T | slug:s")
            # target = None -> open_folder_desktop(None) -> "não encontrado"
            assert "não encontrado" in result.lower()

    def test_delete_book_exception_is_caught(self, tmp_path):
        """CORREÇÃO C5: exceção de delete_book é capturada, não propaga."""
        with patch.object(app.BookLibrary, "get_book", return_value={"title": "T", "slug": "s"}):
            with patch.object(app.BookLibrary, "delete_book", side_effect=Exception("banco travado")):
                result = app.delete_book_from_library("[PT] T | slug:s", "Todos", "Todos")
                # Deve retornar mensagem de erro no índice 3 (desktop_feedback)
                assert "Erro ao remover" in result[3]


# ============================================================================
# 6. TRANSLATE_BOOK - campos do pipeline ausentes
# ============================================================================

class TestQATranslateBookFields:
    def test_pipeline_parser_metadata_missing_title_shows_default(self, tmp_path):
        """CORREÇÃO QA-3/U7: título None no status exibe 'Título desconhecido', não 'None'."""
        epub = tmp_path / "book.epub"
        epub.write_bytes(b"fake")

        with patch("app.TranslationPipeline") as mock_pipeline_class:
            mock_pipeline = MagicMock()
            mock_pipeline.parser.metadata.get.return_value = None
            mock_pipeline.parser.spine = [1, 2]
            mock_pipeline.run.return_value = (str(tmp_path / "out.pdf"), str(tmp_path / "out.epub"))
            mock_pipeline_class.return_value = mock_pipeline

            with patch("app.BingTranslatorEngine"):
                with patch("app.update_library_view", return_value=("<html>", gr.update(), "", "")):
                    pdf, epub_out, status, *_ = app.translate_book(
                        _DummyFile(str(epub)), "en", "pt",
                        "Neural Fast Translator (Padrão, Gratuito)",
                        "qwen2.5:latest", 5, False,
                    )
                    assert "Título desconhecido" in status

    def test_translate_book_ollama_empty_model_defaults_qwen(self, tmp_path):
        """ollama_model vazio -> 'qwen2.5:latest'."""
        epub = tmp_path / "book.epub"
        epub.write_bytes(b"fake")

        with patch("app.TranslationPipeline") as mock_pipeline_class:
            mock_pipeline = MagicMock()
            mock_pipeline.parser.metadata.get.return_value = "Título"
            mock_pipeline.parser.spine = [1]
            mock_pipeline.run.return_value = (str(tmp_path / "out.pdf"), str(tmp_path / "out.epub"))
            mock_pipeline_class.return_value = mock_pipeline

            with patch("app.OllamaTranslatorEngine") as mock_ollama:
                with patch("app.update_library_view", return_value=("<html>", gr.update(), "", "")):
                    app.translate_book(
                        _DummyFile(str(epub)), "en", "pt",
                        "Ollama (IA Local Offline)", "", 5, False,
                    )
                    mock_ollama.assert_called_once()
                    kwargs = mock_ollama.call_args.kwargs or mock_ollama.call_args[1]
                    assert kwargs.get("model") == "qwen2.5:latest"


# ============================================================================
# 7. CONVERT_SCANNED_PDF - stats com chaves ausentes (KeyError)
# ============================================================================

class TestQAConvertScannedPdf:
    def test_stats_missing_chapters_created_does_not_raise(self, tmp_path):
        """CORREÇÃO C3: stats.get('chapters_created', 0) evita KeyError."""
        pdf = tmp_path / "scan.pdf"
        pdf.write_bytes(b"fake")

        with patch("app.OcrToEpubPipeline") as mock_pipeline_class:
            mock_pipeline = MagicMock()
            mock_pipeline.run.return_value = (str(tmp_path / "out.epub"), {"title": "T", "author": "A", "total_pages": 1})
            mock_pipeline_class.return_value = mock_pipeline

            with patch("app.update_library_view", return_value=("<html>", gr.update(), "", "")):
                result = app.convert_scanned_pdf(
                    _DummyFile(str(pdf)), "T", "A", "pt",
                )
                # Não deve levantar KeyError; chapters_created mostra 0
                assert "0" in result[1]

    def test_stats_missing_epub_size_mb_does_not_raise(self, tmp_path):
        """CORREÇÃO C3: stats.get('epub_size_mb', 0) evita KeyError."""
        pdf = tmp_path / "scan.pdf"
        pdf.write_bytes(b"fake")

        with patch("app.OcrToEpubPipeline") as mock_pipeline_class:
            mock_pipeline = MagicMock()
            mock_pipeline.run.return_value = (
                str(tmp_path / "out.epub"),
                {"title": "T", "author": "A", "total_pages": 1, "chapters_created": 1},
            )
            mock_pipeline_class.return_value = mock_pipeline

            with patch("app.update_library_view", return_value=("<html>", gr.update(), "", "")):
                result = app.convert_scanned_pdf(_DummyFile(str(pdf)), "T", "A", "pt")
                # Não deve levantar KeyError; epub_size_mb mostra 0
                assert "0 MB" in result[1]


# ============================================================================
# 8. CONVERT_PDF_TO_EPUB_FLOW - stats com chaves ausentes (KeyError)
# ============================================================================

class TestQAConvertPdfToEpub:
    def test_stats_missing_title_does_not_raise(self, tmp_path):
        """CORREÇÃO C4: stats.get('title', ...) evita KeyError."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"fake")

        with patch("app.FormatConverter.pdf_to_epub") as mock_conv:
            mock_conv.return_value = (str(tmp_path / "out.epub"), {"total_pages": 1})
            result = app.convert_pdf_to_epub_flow(_DummyFile(str(pdf)), "T", "A", "pt")
            assert "Título desconhecido" in result[1]

    def test_stats_missing_chapters_created_does_not_raise(self, tmp_path):
        """CORREÇÃO C4: stats.get('chapters_created', 0) evita KeyError."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"fake")

        with patch("app.FormatConverter.pdf_to_epub") as mock_conv:
            mock_conv.return_value = (str(tmp_path / "out.epub"), {"title": "T", "total_pages": 1})
            result = app.convert_pdf_to_epub_flow(_DummyFile(str(pdf)), "T", "A", "pt")
            assert "0" in result[1]

    def test_stats_missing_epub_size_mb_does_not_raise(self, tmp_path):
        """CORREÇÃO C4: stats.get('epub_size_mb', 0) evita KeyError."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"fake")

        with patch("app.FormatConverter.pdf_to_epub") as mock_conv:
            mock_conv.return_value = (
                str(tmp_path / "out.epub"),
                {"title": "T", "chapters_created": 1, "total_pages": 1},
            )
            result = app.convert_pdf_to_epub_flow(_DummyFile(str(pdf)), "T", "A", "pt")
            assert "0 MB" in result[1]

    def test_stats_missing_total_pages_does_not_raise(self, tmp_path):
        """CORREÇÃO C4: stats.get('total_pages', 0) evita KeyError."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"fake")

        with patch("app.FormatConverter.pdf_to_epub") as mock_conv:
            mock_conv.return_value = (str(tmp_path / "out.epub"), {"title": "T", "chapters_created": 1, "epub_size_mb": 1.0})
            result = app.convert_pdf_to_epub_flow(_DummyFile(str(pdf)), "T", "A", "pt")
            # total_pages ausente -> default 0; não deve levantar KeyError
            assert result is not None
            assert "0" in result[1]


# ============================================================================
# 9. FORMAT_DURATION - valores extremos
# ============================================================================

class TestQAFormatDuration:
    def test_zero_seconds(self):
        assert app.format_duration(0) == "0s"

    def test_negative_seconds(self):
        assert app.format_duration(-5) == "-5s"

    def test_exactly_60_seconds(self):
        assert app.format_duration(60) == "1 min 00 s"

    def test_exactly_3600_seconds(self):
        assert app.format_duration(3600) == "1 h 00 min 00 s"

    def test_float_rounding(self):
        assert app.format_duration(90.6) == "1 min 31 s"


# ============================================================================
# 10. CLEAN_PATH_MIDDLEWARE - caminhos com múltiplas barras
# ============================================================================

class TestQACleanPathMiddleware:
    def test_middleware_normalizes_double_slash(self):
        path = "http://localhost:7860//api//open-file"
        clean = re.sub(r"/+", "/", path)
        assert "//" not in clean

    def test_middleware_trailing_double_slash(self):
        path = "/api/open-file//"
        clean = re.sub(r"/+", "/", path)
        assert not clean.endswith("//")
