import re
import time
import threading
import requests
from abc import ABC, abstractmethod

class BaseTranslatorEngine(ABC):
    """Abstract interface for translation engines."""
    
    @abstractmethod
    def translate(self, text: str) -> str:
        pass

class BingTranslatorEngine(BaseTranslatorEngine):
    """Fast, free Bing Neural Translation engine with token caching and connection pooling.

    The Bing web endpoint is unofficial (page scraping), so extraction of the
    session tokens uses multiple pattern fallbacks, retries use exponential
    backoff, and an optional fallback engine (e.g. Ollama) takes over when the
    Bing endpoint stays unavailable instead of silently returning the
    untranslated source text.
    """

    # Fallback patterns tried in order for each token (first match wins).
    _IG_PATTERNS = (r'"ig"\s*:\s*"(.*?)"', r"'ig'\s*:\s*'(.*?)'")
    _IID_PATTERNS = (r'data-iid="(.*?)"', r"data-iid='(.*?)'")
    _KEY_TOKEN_PATTERNS = (
        r'params_AbusePreventionHelper\s=\s\[(.*?),\"(.*?)\",',
        r'params_AbusePreventionHelper\s*=\s*\[\s*"(.*?)","(.*?)"',
    )

    # Exponential backoff base in seconds: 0.5, 1.0, 2.0, ...
    BACKOFF_BASE_SECONDS = 0.5
    MAX_ATTEMPTS = 3

    def __init__(
        self,
        lang_in: str = "en",
        lang_out: str = "pt",
        fallback_engine: "BaseTranslatorEngine | None" = None,
    ):
        self.lang_in = lang_in
        self.lang_out = lang_out
        self.fallback_engine = fallback_engine
        self.endpoint = "https://www.bing.com/translator"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
        }
        self.lock = threading.Lock()
        self.session = requests.Session()
        self.url = None
        self.ig = None
        self.iid = None
        self.key = None
        self.token = None
        self._refresh_token()

    @staticmethod
    def _extract_first(patterns, text: str, last: bool = False):
        """Return the first captured group of the first pattern that matches."""
        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches:
                return matches[-1] if last else matches[0]
        return None

    def _refresh_token(self):
        with self.lock:
            for attempt in range(self.MAX_ATTEMPTS):
                try:
                    r = self.session.get(self.endpoint, headers=self.headers, timeout=10)
                    r.raise_for_status()
                    self.url = r.url[:-10]
                    self.ig = self._extract_first(self._IG_PATTERNS, r.text)
                    self.iid = self._extract_first(self._IID_PATTERNS, r.text, last=True)
                    key_token = None
                    for pattern in self._KEY_TOKEN_PATTERNS:
                        found = re.findall(pattern, r.text)
                        if found:
                            key_token = found[0]
                            break
                    if not (self.ig and self.iid and key_token):
                        raise ValueError("Bing session tokens not found in page")
                    self.key, self.token = key_token
                    return
                except Exception:
                    if attempt < self.MAX_ATTEMPTS - 1:
                        time.sleep(self.BACKOFF_BASE_SECONDS * (2 ** attempt))
            raise RuntimeError("Failed to obtain Bing Translator authentication tokens.")

    def _translate_single_chunk(self, text: str) -> str:
        if not text or not text.strip():
            return text

        for attempt in range(self.MAX_ATTEMPTS):
            try:
                post_url = f"{self.url}ttranslatev3?IG={self.ig}&IID={self.iid}"
                res = self.session.post(
                    post_url,
                    data={
                        "fromLang": self.lang_in,
                        "to": self.lang_out,
                        "text": text,
                        "token": self.token,
                        "key": self.key,
                    },
                    headers=self.headers,
                    timeout=10
                )
                if res.status_code == 200:
                    data = res.json()
                    if isinstance(data, list) and len(data) > 0 and "translations" in data[0]:
                        return data[0]["translations"][0]["text"]
                    elif isinstance(data, dict) and data.get("statusCode") in (400, 401, 403):
                        self._refresh_token()
                elif res.status_code in (401, 403, 400):
                    self._refresh_token()
            except Exception:
                if attempt < self.MAX_ATTEMPTS - 1:
                    time.sleep(self.BACKOFF_BASE_SECONDS * (2 ** attempt))
                try:
                    self._refresh_token()
                except RuntimeError:
                    # Keep trying the next attempt; the fallback engine (if
                    # any) is used once all attempts are exhausted.
                    pass

        if self.fallback_engine is not None:
            try:
                print("[Bing] Endpoint unavailable; using fallback translation engine.")
                return self.fallback_engine.translate(text)
            except Exception:
                pass
        return text

    def translate(self, text: str) -> str:
        if not text or not text.strip():
            return text

        # If text is within safe Bing payload limit, translate directly
        if len(text) <= 800:
            return self._translate_single_chunk(text)

        # Split long text by sentence boundaries (periods, newlines, question marks)
        sentences = re.split(r'(?<=[.!?\n])\s+', text)
        chunks = []
        cur = ""
        for s in sentences:
            if len(cur) + len(s) + 1 <= 750:
                cur = f"{cur} {s}" if cur else s
            else:
                if cur:
                    chunks.append(cur)
                cur = s
        if cur:
            chunks.append(cur)

        translated_chunks = [self._translate_single_chunk(c) for c in chunks]
        return " ".join(translated_chunks)

class GoogleTranslateEngine(BaseTranslatorEngine):
    """Free online fallback translator (no API key required).

    Uses the public Google Translate web endpoint. This is an unofficial
    endpoint (no SLA), so it is used only as a fallback when the primary
    engine is unavailable. Returns the original text on failure.
    """

    def __init__(self, lang_in: str = "en", lang_out: str = "pt"):
        self.lang_in = lang_in
        self.lang_out = lang_out
        self.endpoint = "https://translate.googleapis.com/translate_a/single"
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
        }

    def _translate_single_chunk(self, text: str) -> str:
        try:
            res = self.session.get(
                self.endpoint,
                params={
                    "client": "gtx",
                    "sl": self.lang_in,
                    "tl": self.lang_out,
                    "dt": "t",
                    "q": text,
                },
                headers=self.headers,
                timeout=10,
            )
            if res.status_code == 200:
                data = res.json()
                # data[0] is a list of segments: [[translated, original, ...], ...]
                if isinstance(data, list) and data and isinstance(data[0], list):
                    return "".join(segment[0] for segment in data[0] if segment)
        except Exception as e:
            print(f"[GoogleTranslate Error] {e}")
        return text

    def translate(self, text: str) -> str:
        if not text or not text.strip():
            return text
        if len(text) <= 1000:
            return self._translate_single_chunk(text)
        # Split long text by sentence boundaries, like the Bing engine.
        sentences = re.split(r'(?<=[.!?\n])\s+', text)
        chunks = []
        cur = ""
        for s in sentences:
            if len(cur) + len(s) + 1 <= 900:
                cur = f"{cur} {s}" if cur else s
            else:
                if cur:
                    chunks.append(cur)
                cur = s
        if cur:
            chunks.append(cur)
        return " ".join(self._translate_single_chunk(c) for c in chunks)


class OllamaTranslatorEngine(BaseTranslatorEngine):
    """Local offline translator via Ollama."""

    def __init__(self, lang_in: str = "en", lang_out: str = "pt", model: str = "qwen2.5:latest", endpoint: str = "http://localhost:11434"):
        self.lang_in = lang_in
        self.lang_out = lang_out
        self.model = model
        self.endpoint = f"{endpoint}/api/generate"

    def translate(self, text: str) -> str:
        if not text or not text.strip():
            return text

        prompt = (
            f"You are a professional technical translator. Translate the following text from {self.lang_in} to {self.lang_out}. "
            "Keep technical terms, programming identifiers, and placeholders like [[_TAG_X_]] exactly as they are without modifying them. "
            "Output ONLY the translated text without explanations:\n\n"
            f"{text}"
        )

        try:
            res = requests.post(
                self.endpoint,
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=60
            )
            if res.status_code == 200:
                return res.json().get("response", "").strip()
        except Exception as e:
            print(f"[Ollama Error] {e}")
        return text
