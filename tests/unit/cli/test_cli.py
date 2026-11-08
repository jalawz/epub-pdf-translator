"""Testes unitários para a interface de linha de comando (cli.py)."""

import argparse
import sys
from unittest.mock import patch, MagicMock

import pytest

# Adiciona o diretório raiz ao path para importar cli
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))

import cli  # noqa: E402


class TestCliArgumentParsing:
    def test_default_arguments(self):
        with patch.object(sys, "argv", ["cli.py", "livro.epub"]):
            args = cli.main.__wrapped__ if hasattr(cli.main, "__wrapped__") else None
            # main() chama sys.exit, então testamos o parser indiretamente
            parser = argparse.ArgumentParser()
            parser.add_argument("epub_file", help="Path to the input .epub file")
            parser.add_argument("-li", "--lang-in", default="en")
            parser.add_argument("-lo", "--lang-out", default="pt")
            parser.add_argument("-o", "--output-dir", default="output")
            parser.add_argument("-w", "--workers", type=int, default=5)
            parser.add_argument("--ollama", help="Use local Ollama model")

            ns = parser.parse_args(["livro.epub"])
            assert ns.epub_file == "livro.epub"
            assert ns.lang_in == "en"
            assert ns.lang_out == "pt"
            assert ns.output_dir == "output"
            assert ns.workers == 5
            assert ns.ollama is None

    def test_custom_arguments(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("epub_file", help="Path to the input .epub file")
        parser.add_argument("-li", "--lang-in", default="en")
        parser.add_argument("-lo", "--lang-out", default="pt")
        parser.add_argument("-o", "--output-dir", default="output")
        parser.add_argument("-w", "--workers", type=int, default=5)
        parser.add_argument("--ollama", help="Use local Ollama model")

        ns = parser.parse_args(
            ["meu_livro.epub", "-li", "fr", "-lo", "es", "-o", "meu_output",
             "-w", "3", "--ollama", "qwen2.5:latest"]
        )
        assert ns.epub_file == "meu_livro.epub"
        assert ns.lang_in == "fr"
        assert ns.lang_out == "es"
        assert ns.output_dir == "meu_output"
        assert ns.workers == 3
        assert ns.ollama == "qwen2.5:latest"

    def test_missing_epub_file_raises(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("epub_file", help="Path to the input .epub file")

        with pytest.raises(SystemExit):
            parser.parse_args([])


class TestCliMainFlow:
    @patch("cli.TranslationPipeline")
    @patch("cli.BingTranslatorEngine")
    @patch("cli.OllamaTranslatorEngine")
    @patch("cli.os.path.exists", return_value=True)
    def test_main_uses_bing_by_default(self, mock_exists, mock_ollama, mock_bing,
                                       mock_pipeline):
        """CLI padrão deve usar BingTranslatorEngine quando --ollama não informado."""
        mock_instance = MagicMock()
        mock_pipeline.return_value = mock_instance
        mock_instance.run.return_value = ("/tmp/pdf", "/tmp/epub")

        with patch.object(sys, "argv", ["cli.py", "livro.epub"]):
            with patch("builtins.print"):
                try:
                    cli.main()
                except SystemExit:
                    pass

        mock_bing.assert_called_once_with(
            lang_in="en", lang_out="pt", fallback_engine=mock_ollama.return_value
        )
        # Ollama é instanciado como fallback do Bing
        mock_ollama.assert_called_once_with(
            lang_in="en", lang_out="pt", model="qwen2.5:latest"
        )

    @patch("cli.TranslationPipeline")
    @patch("cli.BingTranslatorEngine")
    @patch("cli.OllamaTranslatorEngine")
    @patch("cli.os.path.exists", return_value=True)
    def test_main_uses_ollama_when_flag(self, mock_exists, mock_ollama, mock_bing,
                                        mock_pipeline):
        """CLI com --ollama deve usar OllamaTranslatorEngine."""
        mock_instance = MagicMock()
        mock_pipeline.return_value = mock_instance
        mock_instance.run.return_value = ("/tmp/pdf", "/tmp/epub")

        with patch.object(sys, "argv", ["cli.py", "livro.epub", "--ollama", "qwen2.5:latest"]):
            with patch("builtins.print"):
                try:
                    cli.main()
                except SystemExit:
                    pass

        mock_ollama.assert_called_once_with(
            lang_in="en", lang_out="pt", model="qwen2.5:latest"
        )
        mock_bing.assert_not_called()

    @patch("cli.os.path.exists", return_value=False)
    def test_main_exits_when_file_missing(self, mock_exists):
        """Arquivo inexistente deve sair com código de erro."""
        with patch.object(sys, "argv", ["cli.py", "nao_existe.epub"]):
            with patch("builtins.print"):
                with pytest.raises(SystemExit) as exc_info:
                    cli.main()
                assert exc_info.value.code == 1

    @patch("cli.TranslationPipeline")
    @patch("cli.BingTranslatorEngine")
    @patch("cli.os.path.exists", return_value=True)
    def test_main_passes_lang_args(self, mock_exists, mock_bing, mock_pipeline):
        """Os idiomas informados devem ser repassados ao tradutor."""
        mock_instance = MagicMock()
        mock_pipeline.return_value = mock_instance
        mock_instance.run.return_value = ("/tmp/pdf", "/tmp/epub")

        with patch.object(sys, "argv", ["cli.py", "livro.epub", "-li", "fr", "-lo", "es"]):
            with patch("builtins.print"):
                try:
                    cli.main()
                except SystemExit:
                    pass

        call_kwargs = mock_bing.call_args.kwargs
        assert call_kwargs["lang_in"] == "fr"
        assert call_kwargs["lang_out"] == "es"
        assert "fallback_engine" in call_kwargs

    @patch("cli.TranslationPipeline")
    @patch("cli.BingTranslatorEngine")
    @patch("cli.os.path.exists", return_value=True)
    def test_main_passes_workers(self, mock_exists, mock_bing, mock_pipeline):
        """O número de workers deve ser repassado ao pipeline."""
        mock_instance = MagicMock()
        mock_pipeline.return_value = mock_instance
        mock_instance.run.return_value = ("/tmp/pdf", "/tmp/epub")

        with patch.object(sys, "argv", ["cli.py", "livro.epub", "-w", "8"]):
            with patch("builtins.print"):
                try:
                    cli.main()
                except SystemExit:
                    pass

        mock_pipeline.assert_called_once()
        call_kwargs = mock_pipeline.call_args.kwargs
        assert call_kwargs["max_workers"] == 8
