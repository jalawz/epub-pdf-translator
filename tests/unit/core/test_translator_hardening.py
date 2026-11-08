"""Testes de hardening do BingTranslatorEngine (Fase 1 - Opção A, grátis).

Cobre: padrões de fallback na extração de tokens (regex alternativo),
backoff exponencial nos retries e fallback automático para outro engine
(Ollama) quando o endpoint não-oficial fica indisponível.
"""

from unittest.mock import patch, MagicMock

import pytest
import requests

from src.core.translator import BingTranslatorEngine, GoogleTranslateEngine, OllamaTranslatorEngine

BING_GET_HTML = """
<html><body>
  <script>"ig":"ig-xyz"</script>
  <meta data-iid="iid-789">
  <script>params_AbusePreventionHelper = ["abc123","def456",</script>
</body></html>
"""

BING_GET_HTML_ALT = """
<html><body>
  <script>'ig':'ig-alt'</script>
  <meta data-iid='iid-alt'>
  <script>params_AbusePreventionHelper = ["altkey","alttok"]</script>
</body></html>
"""

BING_POST_OK = [{"translations": [{"text": "Olá mundo"}]}]


def _mock_get(html=BING_GET_HTML, status=200):
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.url = "https://www.bing.com/translator"
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _mock_post(status=200, json_data=None):
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.json = MagicMock(return_value=json_data or BING_POST_OK)
    return mock_resp


class TestInitFailureWithFallback:
    @patch("requests.Session.get", side_effect=requests.ConnectionError("Bing offline"))
    def test_init_failure_with_fallback_delegates_to_fallback(self, mock_get):
        """BUG CRÍTICO (code review PR #5): Bing fora do ar no __init__ não pode
        impedir a criação do objeto quando há fallback_engine."""
        fallback = MagicMock()
        fallback.translate.return_value = "Traduzido pelo fallback"

        with patch("src.core.translator.time.sleep"):
            # Não levanta RuntimeError
            t = BingTranslatorEngine(lang_in="en", lang_out="pt", fallback_engine=fallback)

        assert t.url is None and t.ig is None
        result = t.translate("Hello world")
        assert result == "Traduzido pelo fallback"
        fallback.translate.assert_called_once_with("Hello world")

    @patch("requests.Session.get", side_effect=requests.ConnectionError("Bing offline"))
    def test_init_failure_without_fallback_still_raises(self, mock_get):
        """Sem fallback, a falha de inicialização continua levantando RuntimeError."""
        with patch("src.core.translator.time.sleep"):
            with pytest.raises(RuntimeError, match="Failed to obtain Bing"):
                BingTranslatorEngine(lang_in="en", lang_out="pt")


class TestTokenExtractionFallbackPatterns:
    @patch("requests.Session.get", return_value=_mock_get(html=BING_GET_HTML_ALT))
    def test_extracts_tokens_with_alternative_patterns(self, mock_get):
        """Se o HTML mudar para aspas simples/espaços, os padrões alternativos funcionam."""
        t = BingTranslatorEngine(lang_in="en", lang_out="pt")
        assert t.ig == "ig-alt"
        assert t.iid == "iid-alt"
        assert t.key == "altkey"
        assert t.token == "alttok"

    @patch("requests.Session.get", return_value=_mock_get(html="<html>sem tokens</html>"))
    def test_missing_tokens_raise_runtime_error(self, mock_get):
        """HTML sem tokens (formato mudou) levanta RuntimeError após os retries."""
        with patch("src.core.translator.time.sleep"):
            with pytest.raises(RuntimeError, match="Failed to obtain Bing"):
                BingTranslatorEngine(lang_in="en", lang_out="pt")


class TestExponentialBackoff:
    @patch("requests.Session.get", side_effect=requests.ConnectionError("rede fora"))
    def test_refresh_backoff_is_exponential(self, mock_get):
        """Retries do refresh usam backoff 0.5, 1.0 (sem sleep após a última tentativa)."""
        with patch("src.core.translator.time.sleep") as mock_sleep:
            with pytest.raises(RuntimeError):
                BingTranslatorEngine(lang_in="en", lang_out="pt")
            delays = [c.args[0] for c in mock_sleep.call_args_list]
            assert delays == [0.5, 1.0]

    @patch("requests.Session.get", return_value=_mock_get())
    @patch("requests.Session.post", side_effect=requests.ConnectionError("conexão recusada"))
    def test_chunk_backoff_is_exponential(self, mock_post, mock_get):
        """Retries de chunk usam backoff 0.5, 1.0."""
        t = BingTranslatorEngine(lang_in="en", lang_out="pt")
        with patch("src.core.translator.time.sleep") as mock_sleep:
            result = t.translate("Hello world")
            assert result == "Hello world"  # sem fallback, retorna o original
            delays = [c.args[0] for c in mock_sleep.call_args_list]
            assert delays == [0.5, 1.0]


class TestFallbackEngine:
    @patch("requests.Session.get", return_value=_mock_get())
    @patch("requests.Session.post", side_effect=requests.ConnectionError("bing fora"))
    def test_fallback_used_after_exhausting_retries(self, mock_post, mock_get):
        """Com fallback configurado, textão indisponível vem do fallback, não do original."""
        fallback = MagicMock()
        fallback.translate.return_value = "Traduzido pelo fallback"
        t = BingTranslatorEngine(lang_in="en", lang_out="pt", fallback_engine=fallback)

        with patch("src.core.translator.time.sleep"):
            result = t.translate("Hello world")

        assert result == "Traduzido pelo fallback"
        fallback.translate.assert_called_once_with("Hello world")

    @patch("requests.Session.get", return_value=_mock_get())
    @patch("requests.Session.post", return_value=_mock_post())
    def test_fallback_not_used_on_success(self, mock_post, mock_get):
        """Sucesso no Bing não aciona o fallback."""
        fallback = MagicMock()
        t = BingTranslatorEngine(lang_in="en", lang_out="pt", fallback_engine=fallback)

        result = t.translate("Hello world")

        assert result == "Olá mundo"
        fallback.translate.assert_not_called()

    @patch("requests.Session.get", return_value=_mock_get())
    @patch("requests.Session.post", side_effect=requests.ConnectionError("bing fora"))
    def test_fallback_failure_returns_original(self, mock_post, mock_get):
        """Se até o fallback falhar, retorna o texto original (sem levantar)."""
        fallback = MagicMock()
        fallback.translate.side_effect = Exception("ollama fora")
        t = BingTranslatorEngine(lang_in="en", lang_out="pt", fallback_engine=fallback)

        with patch("src.core.translator.time.sleep"):
            result = t.translate("Hello world")

        assert result == "Hello world"


# ---------------------------------------------------------------------------
# GoogleTranslateEngine (fallback online e grátis, sem chave)
# ---------------------------------------------------------------------------
class TestGoogleTranslateEngine:
    @patch("requests.Session.get")
    def test_translate_returns_google_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [[["Olá mundo", "Hello world", None, None, 10]]]
        mock_get.return_value = mock_resp

        t = GoogleTranslateEngine(lang_in="en", lang_out="pt")
        result = t.translate("Hello world")

        assert result == "Olá mundo"
        params = mock_get.call_args.kwargs["params"]
        assert params["client"] == "gtx"
        assert params["sl"] == "en"
        assert params["tl"] == "pt"

    @patch("requests.Session.get", side_effect=requests.ConnectionError("sem rede"))
    def test_connection_error_returns_original(self, mock_get):
        t = GoogleTranslateEngine(lang_in="en", lang_out="pt")
        assert t.translate("Hello world") == "Hello world"

    def test_empty_text_returns_empty(self):
        t = GoogleTranslateEngine(lang_in="en", lang_out="pt")
        assert t.translate("") == ""
        assert t.translate("   ") == "   "

    @patch("requests.Session.get")
    def test_non_200_returns_original(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_get.return_value = mock_resp

        t = GoogleTranslateEngine(lang_in="en", lang_out="pt")
        assert t.translate("Hello world") == "Hello world"

    @patch("requests.Session.get")
    def test_none_segments_are_ignored(self, mock_get):
        """Segmentos com texto None não quebram o join (TypeError)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            [["Olá", "Hello", None], [None, "x", None], [" mundo", " world", None]]
        ]
        mock_get.return_value = mock_resp

        t = GoogleTranslateEngine(lang_in="en", lang_out="pt")
        assert t.translate("Hello world") == "Olá mundo"

    @patch("requests.Session.get")
    def test_long_sentence_without_punctuation_is_hard_split(self, mock_get):
        """Parágrafo longo sem pontuação é fatiado para URL segura (sem 414)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [[[" traduzido ", "x", None]]]
        mock_get.return_value = mock_resp

        t = GoogleTranslateEngine(lang_in="en", lang_out="pt")
        long_text = "palavra " * 600  # ~4800 chars, sem pontuação final
        result = t.translate(long_text.strip())

        assert isinstance(result, str) and result
        # Nenhuma chamada GET deve ter query gigante
        for call in mock_get.call_args_list:
            q = call.kwargs["params"]["q"]
            assert len(q) <= 1000
