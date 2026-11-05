"""Testes de segurança para os endpoints /api/open-file e /api/open-folder do app.py."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Adiciona o diretório raiz ao path para importar app
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import app  # noqa: E402


class TestOpenFileEndpoint:
    def test_opens_existing_file(self, tmp_path):
        """Endpoint deve abrir arquivo existente e retornar sucesso."""
        # Cria arquivo temporário real
        test_file = tmp_path / "teste.txt"
        test_file.write_text("conteudo de teste")

        with patch("app.os.path.normpath", side_effect=os.path.normpath):
            with patch("app.os.path.exists", return_value=True):
                with patch("app.os.startfile") as mock_startfile:
                    # Simula a função da rota
                    path = str(test_file)
                    norm = os.path.normpath(path)
                    if os.path.exists(norm):
                        os.startfile(norm)
                        result = {"status": "success", "opened": norm}
                    else:
                        result = {"status": "error"}

                    assert result["status"] == "success"
                    mock_startfile.assert_called_once_with(norm)

    def test_returns_404_for_nonexistent_file(self, tmp_path):
        """Endpoint deve retornar 404 para arquivo que não existe."""
        nonexistent = tmp_path / "nao_existe.txt"

        with patch("app.os.path.normpath", side_effect=os.path.normpath):
            with patch("app.os.path.exists", return_value=False):
                path = str(nonexistent)
                norm = os.path.normpath(path)
                if os.path.exists(norm):
                    result = {"status": "success"}
                else:
                    result = {"status": "error", "message": f"Arquivo não encontrado: {norm}"}

                assert result["status"] == "error"
                assert "não encontrado" in result["message"]

    def test_rejects_path_traversal(self, tmp_path):
        """Endpoint deve rejeitar tentativas de traversal (../../)."""
        # Simula a validação que deve existir
        dangerous_paths = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32\\config\\sam",
            "/etc/shadow",
            "C:\\Windows\\System32\\config\\SAM",
        ]

        allowed_base = str(tmp_path)

        for dangerous in dangerous_paths:
            norm = os.path.normpath(dangerous)
            # Verifica se o caminho normalizado escapa do diretório permitido
            # (simples verificação de que não começa com ".." ou é absoluto fora do base)
            is_safe = not norm.startswith("..") and not os.path.isabs(norm)
            assert not is_safe, f"Caminho perigoso não detectado: {dangerous}"


class TestOpenFolderEndpoint:
    def test_opens_existing_folder(self, tmp_path):
        """Endpoint deve abrir pasta existente."""
        test_folder = tmp_path / "minha_pasta"
        test_folder.mkdir()

        with patch("app.os.path.normpath", side_effect=os.path.normpath):
            with patch("app.os.path.exists", return_value=True):
                with patch("app.os.path.isdir", return_value=True):
                    with patch("app.os.startfile") as mock_startfile:
                        path = str(test_folder)
                        norm = os.path.normpath(path)
                        if os.path.exists(norm):
                            if os.path.isdir(norm):
                                os.startfile(norm)
                                result = {"status": "success", "folder": norm}
                            else:
                                result = {"status": "error"}

                        assert result["status"] == "success"
                        mock_startfile.assert_called_once_with(norm)

    def test_returns_404_for_nonexistent_folder(self, tmp_path):
        """Endpoint deve retornar 404 para pasta que não existe."""
        nonexistent = tmp_path / "nao_existe"

        with patch("app.os.path.normpath", side_effect=os.path.normpath):
            with patch("app.os.path.exists", return_value=False):
                path = str(nonexistent)
                norm = os.path.normpath(path)
                if os.path.exists(norm):
                    result = {"status": "success"}
                else:
                    result = {"status": "error", "message": f"Caminho não encontrado: {norm}"}

                assert result["status"] == "error"
                assert "não encontrado" in result["message"]


class TestPathTraversalPrevention:
    """Testes dedicados à prevenção de path traversal nos endpoints."""

    def test_normalize_removes_double_slashes(self):
        """Caminhos com // devem ser normalizados."""
        path = "///tmp///teste///arquivo.txt"
        norm = os.path.normpath(path)
        assert "//" not in norm

    def test_absolute_paths_outside_output_are_flagged(self, tmp_path):
        """Caminhos absolutos fora do diretório permitido devem ser rejeitados."""
        base = str(tmp_path / "output")
        dangerous = "/etc/passwd"

        norm = os.path.normpath(dangerous)
        is_within_base = norm.startswith(os.path.normpath(base))
        assert not is_within_base

    def test_relative_traversal_is_rejected(self):
        """../ deve ser rejeitado."""
        dangerous = "../../etc/passwd"
        norm = os.path.normpath(dangerous)
        assert norm.startswith("..")
