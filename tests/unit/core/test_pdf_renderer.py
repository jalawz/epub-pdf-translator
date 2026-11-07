"""Testes unitários para o PdfRenderer (HTML -> PDF via Chromium headless)."""

import os
from unittest.mock import patch, MagicMock

import pytest

from src.core.pdf_renderer import PdfRenderer


# ---------------------------------------------------------------------------
# Fake browser path para não depender de Chrome/Edge instalado
# ---------------------------------------------------------------------------
FAKE_BROWSER = "/fake/path/to/chrome.exe"


def _make_renderer():
    with patch.object(PdfRenderer, "_find_browser", return_value=FAKE_BROWSER):
        return PdfRenderer()


class TestPdfRendererInit:
    def test_find_browser_returns_path(self):
        with patch.object(
            PdfRenderer, "_find_browser", return_value=FAKE_BROWSER
        ):
            r = PdfRenderer()
            assert r.browser_path == FAKE_BROWSER

    def test_no_browser_raises_runtime_error(self):
        with patch.object(
            PdfRenderer, "_find_browser", return_value=None
        ):
            with pytest.raises(RuntimeError, match="No Chromium"):
                PdfRenderer()

    def test_browser_detection_includes_windows_paths(self):
        # Verifica que o método _find_browser conhece caminhos do Windows
        r = _make_renderer()
        assert r.browser_path == FAKE_BROWSER


class TestPrintStylesheetInjection:
    def test_inject_print_style_adds_a4_page(self):
        r = _make_renderer()
        html = "<html><head></head><body><p>hello</p></body></html>"
        result = r.inject_print_style(html, is_cover=False)

        assert "@page" in result
        assert "size: A4" in result
        assert "margin: 20mm 15mm" in result

    def test_inject_print_style_cover_uses_zero_margin(self):
        r = _make_renderer()
        html = "<html><head></head><body><p>cover</p></body></html>"
        result = r.inject_print_style(html, is_cover=True)

        assert "margin: 0" in result or "margin:0" in result
        assert "100vw" in result or "100vh" in result

    def test_inject_print_style_replaces_existing_print_block(self):
        r = _make_renderer()
        html = """<html><head>
        <!-- PRINT_STYLE_START -->
        <style>old style</style>
        <!-- PRINT_STYLE_END -->
        </head><body><p>x</p></body></html>"""
        result = r.inject_print_style(html, is_cover=False)

        assert "old style" not in result
        assert "@page" in result

    def test_inject_print_style_inserts_into_head(self):
        r = _make_renderer()
        html = "<html><head><title>T</title></head><body><p>x</p></body></html>"
        result = r.inject_print_style(html, is_cover=False)

        assert "<head>" in result
        assert "@page" in result
        # O estilo deve estar dentro do head
        head_end = result.index("</head>")
        assert "@page" in result[:head_end]

    def test_inject_print_style_prepends_when_no_head(self):
        r = _make_renderer()
        html = "<body><p>no head</p></body>"
        result = r.inject_print_style(html, is_cover=False)

        assert "@page" in result
        assert result.startswith("<style") or "<!-- PRINT_STYLE_START" in result


class TestRenderToPdf:
    @patch("subprocess.run")
    def test_render_command_is_correct(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)

        r = _make_renderer()
        html_path = "/tmp/chapter.html"
        pdf_path = "/tmp/chapter.pdf"

        with patch("os.path.abspath", side_effect=lambda x: x):
            with patch("os.makedirs"):
                with patch("os.path.exists", return_value=True):
                    with patch("os.path.getsize", return_value=1024):
                        r.render_to_pdf(html_path, pdf_path)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == FAKE_BROWSER
        assert "--headless" in args
        assert "--disable-gpu" in args
        assert "--no-pdf-header-footer" in args
        assert f"--print-to-pdf={pdf_path}" in args
        assert html_path in args

    @patch("subprocess.run")
    def test_render_returns_true_on_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)

        r = _make_renderer()
        with patch("os.path.abspath", side_effect=lambda x: x):
            with patch("os.makedirs"):
                with patch("os.path.exists", return_value=True):
                    with patch("os.path.getsize", return_value=1024):
                        result = r.render_to_pdf("/tmp/a.html", "/tmp/b.pdf")

        assert result is True

    @patch("subprocess.run")
    def test_render_returns_false_when_pdf_missing(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)

        r = _make_renderer()
        with patch("os.path.abspath", side_effect=lambda x: x):
            with patch("os.makedirs"):
                with patch("os.path.exists", return_value=False):
                    result = r.render_to_pdf("/tmp/a.html", "/tmp/b.pdf")

        assert result is False

    @patch("subprocess.run", side_effect=Exception("browser crashed"))
    def test_render_handles_exception(self, mock_run):
        r = _make_renderer()
        with patch("os.path.abspath", side_effect=lambda x: x):
            with patch("os.makedirs"):
                result = r.render_to_pdf("/tmp/a.html", "/tmp/b.pdf")

        assert result is False
