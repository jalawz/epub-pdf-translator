"""Testes unitários para os motores de tradução (Bing + Ollama)."""

import json
from unittest.mock import patch, MagicMock

import pytest
import requests

from src.core.translator import (
    BaseTranslatorEngine,
    BingTranslatorEngine,
    OllamaTranslatorEngine,
)


# ---------------------------------------------------------------------------
# Fake translator para testar a interface abstrata
# ---------------------------------------------------------------------------
class FakeTranslator(BaseTranslatorEngine):
    def translate(self, text: str) -> str:
        return text.upper()


class TestBaseTranslatorEngine:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseTranslatorEngine()


class TestFakeTranslator:
    def test_translate_returns_uppercase(self):
        t = FakeTranslator()
        assert t.translate("hello world") == "HELLO WORLD"


# ---------------------------------------------------------------------------
# BingTranslatorEngine
# ---------------------------------------------------------------------------
BING_GET_HTML = """
<html>
  <head></head>
  <body>
    <script>"ig":"ig-xyz"</script>
    <meta data-iid="iid-789">
    <script>params_AbusePreventionHelper = ["abc123","def456",</script>
  </body>
</html>
"""

BING_POST_OK = [{"translations": [{"text": "Olá mundo"}]}]


def _mock_session_get(html=BING_GET_HTML, status=200):
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.url = "https://www.bing.com/translator"
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _mock_session_post(status=200, json_data=None, side_effect=None):
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.json = MagicMock(return_value=json_data or BING_POST_OK)
    return mock_resp


class TestBingTranslatorEngine:
    @patch("requests.Session.get", return_value=_mock_session_get())
    def test_init_refreshes_tokens(self, mock_get):
        t = BingTranslatorEngine(lang_in="en", lang_out="pt")

        assert t.url == "https://www.bing.com/translator"[:-10]
        assert t.ig == "ig-xyz"
        assert t.iid == "iid-789"
        # O regex do código captura as aspas na key mas não na token
        assert t.key == '"abc123"'
        assert t.token == 'def456'
        mock_get.assert_called()

    @patch("requests.Session.get", return_value=_mock_session_get())
    @patch("requests.Session.post", return_value=_mock_session_post())
    def test_translate_short_text(self, mock_post, mock_get):
        t = BingTranslatorEngine(lang_in="en", lang_out="pt")
        result = t.translate("Hello world")

        assert result == "Olá mundo"
        mock_post.assert_called()

    @patch("requests.Session.get", return_value=_mock_session_get())
    def test_translate_empty_text_returns_empty(self, mock_get):
        t = BingTranslatorEngine(lang_in="en", lang_out="pt")
        assert t.translate("") == ""
        assert t.translate("   ") == "   "
        # Nenhum POST deve ser feito para texto vazio
        with patch("requests.Session.post") as mock_post:
            t.translate("")
            mock_post.assert_not_called()

    @patch("requests.Session.get", return_value=_mock_session_get())
    @patch("requests.Session.post", return_value=_mock_session_post())
    def test_translate_long_text_is_chunked(self, mock_post, mock_get):
        long_text = "Sentence one. " * 80  # ~1040 chars

        t = BingTranslatorEngine(lang_in="en", lang_out="pt")
        result = t.translate(long_text)

        assert result is not None
        assert isinstance(result, str)
        # Deve haver pelo menos 2 chamadas POST (chunking)
        assert mock_post.call_count >= 2

    @patch("requests.Session.get", return_value=_mock_session_get())
    @patch("requests.Session.post", side_effect=[
        _mock_session_post(status=401, json_data={"statusCode": 401}),
        _mock_session_post(status=200, json_data=BING_POST_OK),
    ])
    def test_translate_401_triggers_token_refresh_and_retry(self, mock_post, mock_get):
        t = BingTranslatorEngine(lang_in="en", lang_out="pt")
        result = t.translate("Hello world")

        assert result == "Olá mundo"
        assert mock_post.call_count == 2

    @patch("requests.Session.get", side_effect=requests.ConnectionError("rede fora"))
    def test_refresh_token_failure_raises_runtime_error(self, mock_get):
        with pytest.raises(RuntimeError, match="Failed to obtain Bing"):
            BingTranslatorEngine(lang_in="en", lang_out="pt")

    @patch("requests.Session.get", return_value=_mock_session_get())
    @patch("requests.Session.post", side_effect=requests.ConnectionError("conexão recusada"))
    def test_network_error_in_single_chunk_returns_original_text(self, mock_post, mock_get):
        t = BingTranslatorEngine(lang_in="en", lang_out="pt")
        result = t.translate("Hello world")

        # Quando tudo falha, retorna o texto original
        assert result == "Hello world"


# ---------------------------------------------------------------------------
# OllamaTranslatorEngine
# ---------------------------------------------------------------------------
class TestOllamaTranslatorEngine:
    @patch("requests.post")
    def test_translate_returns_ollama_response(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "Olá mundo"}
        mock_post.return_value = mock_resp

        t = OllamaTranslatorEngine(
            lang_in="en", lang_out="pt", model="qwen2.5:latest"
        )
        result = t.translate("Hello world")

        assert result == "Olá mundo"
        mock_post.assert_called_once()

    @patch("requests.post", side_effect=requests.ConnectionError("sem ollama"))
    def test_translate_connection_error_returns_original(self, mock_post):
        t = OllamaTranslatorEngine(
            lang_in="en", lang_out="pt", model="qwen2.5:latest"
        )
        result = t.translate("Hello world")

        assert result == "Hello world"

    def test_translate_empty_text_returns_empty(self):
        t = OllamaTranslatorEngine(
            lang_in="en", lang_out="pt", model="qwen2.5:latest"
        )
        assert t.translate("") == ""
        assert t.translate("   ") == "   "

    @patch("requests.post")
    def test_prompt_contains_languages_and_model(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "ok"}
        mock_post.return_value = mock_resp

        t = OllamaTranslatorEngine(
            lang_in="en", lang_out="pt", model="llama3.1:latest"
        )
        t.translate("Texto de teste")

        # Verifica o payload enviado
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        assert payload["model"] == "llama3.1:latest"
        assert "en" in payload["prompt"]
        assert "pt" in payload["prompt"]
        assert "Texto de teste" in payload["prompt"]
        assert payload["stream"] is False
