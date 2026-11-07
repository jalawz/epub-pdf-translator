"""Testes de UI para o app Gradio (handlers de evento, endpoints e renderização).

Cobre comportamentos da interface: validações de entrada, renderização da
biblioteca, seleção/deleção de livros e endpoints /api/open-file e
/api/open-folder. Usa mocks para não acionar tradução/OCR reais nem abrir
arquivos no Windows.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import gradio as gr
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import app  # noqa: E402

# Nota: as rotas /api/open-file e /api/open-folder só são registradas no
# demo.app quando app.py é executado diretamente (bloco if __name__ == "__main__").
# Elas já são cobertas por tests/unit/app/test_endpoints_security.py, que testa
# as funções de endpoint diretamente. Portanto, não as testamos aqui via TestClient
# para evitar acionar o servidor Gradio em tempo de teste.


# ---------------------------------------------------------------------------
# Validações de entrada das funções da UI
# ---------------------------------------------------------------------------

class TestUITranslateValidation:
    def test_translate_book_raises_without_file(self):
        """translate_book deve levantar gr.Error quando nenhum EPUB é enviado."""
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

    def test_convert_scanned_pdf_raises_without_file(self):
        """convert_scanned_pdf deve levantar gr.Error sem PDF."""
        with pytest.raises(gr.Error):
            app.convert_scanned_pdf(
                pdf_file=None,
                book_title="",
                book_author="",
                ocr_lang="pt",
            )

    def test_convert_epub_to_pdf_raises_without_file(self):
        """convert_epub_to_pdf_flow deve levantar gr.Error sem EPUB."""
        with pytest.raises(gr.Error):
            app.convert_epub_to_pdf_flow(epub_file=None)

    def test_convert_pdf_to_epub_raises_without_file(self):
        """convert_pdf_to_epub_flow deve levantar gr.Error sem PDF."""
        with pytest.raises(gr.Error):
            app.convert_pdf_to_epub_flow(
                pdf_file=None,
                title="",
                author="",
                lang="pt",
            )


# ---------------------------------------------------------------------------
# Renderização da biblioteca (HTML)
# ---------------------------------------------------------------------------

class TestUILibraryRendering:
    def test_render_books_grid_empty(self):
        """Biblioteca vazia deve renderizar HTML com mensagem 'nenhum livro'."""
        html = app.render_books_grid_html([])
        assert "Nenhum livro encontrado nesta seleção" in html
        assert "📭" in html

    def test_render_books_grid_with_book_no_cover(self, tmp_path):
        """Livro sem capa deve renderizar ícone de livro (📖)."""
        books = [
            {
                "title": "Código Limpo",
                "author": "Robert C. Martin",
                "lang": "pt",
                "category": "translation",
                "source_lang": "en",
                "pages": 400,
                "pdf_size_mb": 2.5,
                "epub_size_mb": 1.2,
                "date_added": "2026-01-15T10:00:00",
                "pdf_path": str(tmp_path / "book.pdf"),
                "epub_path": str(tmp_path / "book.epub"),
                "book_dir": str(tmp_path),
                "slug": "codigo-limpo",
                "cover_path": None,
            }
        ]
        html = app.render_books_grid_html(books)
        assert "Código Limpo" in html
        assert "Robert C. Martin" in html
        assert "📄 Abrir PDF" in html
        assert "📱 Abrir EPUB" in html
        assert "📂 Abrir Pasta" in html
        assert "⬇️ PDF" in html
        assert "⬇️ EPUB" in html

    def test_update_library_view_empty_returns_defaults(self, tmp_path):
        """update_library_view com biblioteca vazia retorna padrões seguros."""
        with patch.object(app.BookLibrary, "list_books", return_value=[]):
            grid, choices_update, info, feedback = app.update_library_view("Todos", "Todos")
            assert "Nenhum livro encontrado nesta seleção" in grid
            # gr.update retorna um dict com as chaves do componente
            assert isinstance(choices_update, dict)
            assert choices_update.get("choices") == []
            assert "Nenhum livro encontrado com os filtros selecionados" in info


# ---------------------------------------------------------------------------
# Seleção e exclusão de livros na UI
# ---------------------------------------------------------------------------

class TestUIBookSelection:
    def test_on_select_book_invalid_label(self):
        """on_select_book com label inválido retorna mensagem de nenhum livro."""
        info, feedback = app.on_select_book("qualquer coisa")
        assert "Nenhum livro selecionado" in info

    def test_on_select_book_missing_slug(self):
        """on_select_book sem '| slug:' retorna aviso."""
        info, feedback = app.on_select_book("[PT] Título")
        assert "Nenhum livro selecionado" in info

    def test_delete_book_without_selection_returns_current_view(self, tmp_path):
        """delete_book_from_library sem seleção retorna a view atual inalterada."""
        grid, choices, info, feedback = app.update_library_view("Todos", "Todos")
        result = app.delete_book_from_library(None, "Todos", "Todos")
        assert result == (grid, choices, info, feedback)


# ---------------------------------------------------------------------------
# Toggle de visibilidade do Ollama
# ---------------------------------------------------------------------------

class TestUIOllamaToggle:
    def test_toggle_ollama_visible_when_ollama_selected(self):
        """Ollama input deve ficar visível apenas quando 'Ollama' está na escolha."""
        update = app.toggle_ollama("Ollama (IA Local Offline)")
        assert isinstance(update, dict)
        assert update.get("visible") is True

    def test_toggle_ollama_hidden_when_neural_selected(self):
        """Ollama input deve ficar oculto quando não é Ollama."""
        update = app.toggle_ollama("Neural Fast Translator (Padrão, Gratuito)")
        assert isinstance(update, dict)
        assert update.get("visible") is False


# ---------------------------------------------------------------------------
# Ações de desktop da UI (abrir PDF/EPUB/pasta)
# ---------------------------------------------------------------------------

class TestUIDesktopActions:
    def test_action_open_selected_pdf_no_selection(self):
        """action_open_selected_pdf sem seleção retorna aviso."""
        result = app.action_open_selected_pdf(None)
        assert "Selecione um livro" in result

    def test_action_open_selected_epub_no_selection(self):
        """action_open_selected_epub sem seleção retorna aviso."""
        result = app.action_open_selected_epub(None)
        assert "Selecione um livro" in result

    def test_action_open_selected_folder_no_selection(self):
        """action_open_selected_folder sem seleção retorna aviso."""
        result = app.action_open_selected_folder(None)
        assert "Selecione um livro" in result
