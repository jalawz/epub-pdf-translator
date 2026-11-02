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
    """Fast, free Bing Neural Translation engine with token caching and connection pooling."""

    def __init__(self, lang_in: str = "en", lang_out: str = "pt"):
        self.lang_in = lang_in
        self.lang_out = lang_out
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

    def _refresh_token(self):
        with self.lock:
            for _ in range(3):
                try:
                    r = self.session.get(self.endpoint, headers=self.headers, timeout=10)
                    r.raise_for_status()
                    self.url = r.url[:-10]
                    self.ig = re.findall(r'\"ig\":\"(.*?)\"', r.text)[0]
                    self.iid = re.findall(r'data-iid=\"(.*?)\"', r.text)[-1]
                    self.key, self.token = re.findall(r'params_AbusePreventionHelper\s=\s\[(.*?),\"(.*?)\",', r.text)[0]
                    return
                except Exception:
                    time.sleep(1)
            raise RuntimeError("Failed to obtain Bing Translator authentication tokens.")

    def _translate_single_chunk(self, text: str) -> str:
        if not text or not text.strip():
            return text

        for attempt in range(3):
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
                time.sleep(0.5)
                self._refresh_token()

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
