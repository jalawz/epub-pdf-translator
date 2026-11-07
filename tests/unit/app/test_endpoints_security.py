"""Testes de segurança para os endpoints /api/open-file e /api/open-folder do app.py.

Testa os handlers reais expostos no escopo do módulo (_api_open_file_handler,
_api_open_folder_handler), incluindo validação de contenção de caminho
(OUTPUT_DIR) e prevenção de path traversal.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import app  # noqa: E402


class TestOpenFileEndpoint:
    """Testa o handler _api_open_file_handler."""

    def test_opens_existing_file(self):
        """Arquivo existente dentro do OUTPUT_DIR deve retornar sucesso."""
        test_file = Path(app.OUTPUT_DIR) / "teste_endpoint.txt"
        test_file.write_text("conteudo de teste")
        try:
            with patch("app.os.path.exists", return_value=True), \
                 patch("app.os.startfile") as mock_startfile:
                result = app._api_open_file_handler(str(test_file))
                assert result.status_code == 200
                mock_startfile.assert_called_once_with(str(test_file))
        finally:
            test_file.unlink(missing_ok=True)

    def test_returns_404_for_nonexistent_file(self):
        """Arquivo inexistente deve retornar 404."""
        with patch("app.os.path.exists", return_value=False):
            nonexistent = str(Path(app.OUTPUT_DIR) / "nao_existe.txt")
            result = app._api_open_file_handler(nonexistent)
            assert result.status_code == 404

    def test_rejects_path_traversal(self):
        """Tentativas de path traversal devem ser rejeitadas com 403."""
        dangerous_paths = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32\\config\\sam",
            "/etc/shadow",
        ]
        for dangerous in dangerous_paths:
            result = app._api_open_file_handler(dangerous)
            assert result.status_code == 403, f"Caminho perigoso não bloqueado: {dangerous}"

    def test_absolute_path_outside_output_is_rejected(self):
        """Caminho absoluto fora de OUTPUT_DIR deve ser rejeitado."""
        result = app._api_open_file_handler("/etc/passwd")
        assert result.status_code == 403

    def test_returns_500_on_exception(self):
        """Exceção inesperada deve retornar 500."""
        with patch("app.os.path.exists", side_effect=Exception("erro inesperado")):
            result = app._api_open_file_handler(str(Path(app.OUTPUT_DIR) / "qualquer.txt"))
            assert result.status_code == 500


class TestOpenFolderEndpoint:
    """Testa o handler _api_open_folder_handler."""

    def test_opens_existing_folder(self):
        """Pasta existente dentro do OUTPUT_DIR deve retornar sucesso."""
        test_folder = Path(app.OUTPUT_DIR) / "pasta_endpoint"
        test_folder.mkdir(exist_ok=True)
        try:
            with patch("app.os.path.exists", return_value=True), \
                 patch("app.os.path.isdir", return_value=True), \
                 patch("app.os.startfile") as mock_startfile:
                result = app._api_open_folder_handler(str(test_folder))
                assert result.status_code == 200
                mock_startfile.assert_called_once_with(str(test_folder))
        finally:
            test_folder.rmdir()

    def test_returns_404_for_nonexistent_folder(self):
        """Pasta inexistente dentro do OUTPUT_DIR deve retornar 404."""
        nonexistent = str(Path(app.OUTPUT_DIR) / "nao_existe")
        with patch("app.os.path.exists", return_value=False):
            result = app._api_open_folder_handler(nonexistent)
            assert result.status_code == 404

    def test_rejects_path_traversal(self):
        """Tentativas de path traversal em pasta devem ser rejeitadas com 403."""
        dangerous_paths = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
        ]
        for dangerous in dangerous_paths:
            result = app._api_open_folder_handler(dangerous)
            assert result.status_code == 403, f"Caminho perigoso não bloqueado: {dangerous}"


class TestIsSafePath:
    """Testes dedicados à função _is_safe_path."""

    def test_same_directory_is_safe(self, tmp_path):
        """Caminho dentro do diretório base é seguro."""
        base = str(tmp_path)
        target = str(tmp_path / "sub" / "arquivo.txt")
        assert app._is_safe_path(target, base) is True

    def test_traversal_outside_base_is_unsafe(self):
        """../ para fora do base é inseguro."""
        assert app._is_safe_path("../../../etc/passwd", "/tmp/output") is False

    def test_absolute_outside_base_is_unsafe(self):
        """Caminho absoluto fora do base é inseguro."""
        assert app._is_safe_path("/etc/passwd", "/tmp/output") is False

    def test_base_itself_is_safe(self, tmp_path):
        """O próprio diretório base é seguro."""
        base = str(tmp_path)
        assert app._is_safe_path(base, base) is True

    def test_none_path_is_unsafe(self):
        """Caminho None deve ser tratado como inseguro."""
        assert app._is_safe_path(None, "/tmp/output") is False
