"""Testes para as ações de desktop (abrir arquivo/pasta) do app.py."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import app  # noqa: E402


class TestOpenFileDesktop:
    def test_open_file_returns_warning_when_missing(self):
        """Arquivo inexistente deve retornar aviso."""
        with patch("app.os.path.exists", return_value=False):
            result = app.open_file_desktop("/caminho/nao/existe.txt")
        assert "não encontrado" in result.lower()

    def test_open_file_calls_startfile(self):
        """Arquivo existente deve chamar os.startfile."""
        with patch("app.os.path.exists", return_value=True):
            with patch("app.os.path.normpath", side_effect=lambda x: x):
                with patch("app.os.startfile") as mock_startfile:
                    result = app.open_file_desktop("/tmp/teste.pdf")
                    mock_startfile.assert_called_once_with("/tmp/teste.pdf")
                    assert "leitor" in result.lower() or "startfile" in result.lower()

    def test_open_file_handles_exception(self):
        """Exceção ao abrir arquivo deve retornar mensagem de erro."""
        with patch("app.os.path.exists", return_value=True):
            with patch("app.os.path.normpath", side_effect=lambda x: x):
                with patch("app.os.startfile", side_effect=Exception("erro")):
                    result = app.open_file_desktop("/tmp/teste.pdf")
                    assert "Erro ao abrir arquivo" in result


class TestOpenFolderDesktop:
    def test_open_folder_calls_startfile(self):
        """Pasta existente deve chamar os.startfile."""
        with patch("app.os.path.exists", return_value=True):
            with patch("app.os.path.normpath", side_effect=lambda x: x):
                with patch("app.os.path.isdir", return_value=True):
                    with patch("app.os.startfile") as mock_startfile:
                        result = app.open_folder_desktop("/tmp/minha_pasta")
                        mock_startfile.assert_called_once_with("/tmp/minha_pasta")

    def test_open_folder_file_uses_explorer_select(self):
        """Arquivo (não pasta) deve abrir explorer com /select."""
        with patch("app.os.path.exists", return_value=True):
            with patch("app.os.path.normpath", side_effect=lambda x: x):
                with patch("app.os.path.isdir", return_value=False):
                    with patch("app.subprocess.Popen") as mock_popen:
                        app.open_folder_desktop("/tmp/arquivo.pdf")
                        mock_popen.assert_called_once()
                        args = mock_popen.call_args[0][0]
                        assert "/select," in args[1]

    def test_open_folder_missing_returns_warning(self):
        """Pasta inexistente deve retornar aviso."""
        with patch("app.os.path.exists", return_value=False):
            result = app.open_folder_desktop("/caminho/nao/existe")
        assert "não encontrado" in result.lower()


class TestOpenParentFolderDesktop:
    """CORREÇÃO QA-3/U1-U4: botões 'Abrir Pasta' abrem a pasta do arquivo."""

    def test_missing_file_returns_warning(self):
        """Arquivo inexistente deve retornar aviso."""
        with patch("app.os.path.exists", return_value=False):
            result = app.open_parent_folder_desktop("/caminho/nao/existe.pdf")
        assert "não encontrado" in result.lower()

    def test_file_opens_parent_dir(self):
        """Arquivo existente abre a pasta-pai, não o arquivo em si."""
        with patch("app.os.path.exists", return_value=True), \
             patch("app.os.path.normpath", side_effect=lambda x: x), \
             patch("app.os.path.isdir", side_effect=lambda p: p == "/tmp"), \
             patch("app.os.startfile") as mock_startfile:
            result = app.open_parent_folder_desktop("/tmp/livro.pdf")
            mock_startfile.assert_called_once_with("/tmp")
            assert "Pasta aberta" in result

    def test_folder_opens_itself(self):
        """Se já for pasta, abre-a diretamente."""
        with patch("app.os.path.exists", return_value=True), \
             patch("app.os.path.normpath", side_effect=lambda x: x), \
             patch("app.os.path.isdir", return_value=True), \
             patch("app.os.startfile") as mock_startfile:
            result = app.open_parent_folder_desktop("/tmp/minha_pasta")
            mock_startfile.assert_called_once_with("/tmp/minha_pasta")
            assert "Pasta aberta" in result
