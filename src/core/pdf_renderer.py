import os
import shutil
import subprocess
from typing import Optional

class PdfRenderer:
    """Renders HTML+CSS chapters into print-ready A4 PDF documents using a headless browser."""

    PRINT_STYLESHEET = """
<style>
@page {
    size: A4;
    margin: 20mm 15mm 20mm 15mm;
    @bottom-center {
        content: counter(page);
    }
}
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.6;
    color: #24292e;
    background: #ffffff;
    max-width: 900px;
    margin: 0 auto;
    padding: 20px;
}
img {
    max-width: 100% !important;
    height: auto !important;
    display: block;
    margin: 20px auto;
}
/* Modern IDE Code Styling */
#book-content #sbo-rt-content pre,
pre {
    font-family: 'Consolas', 'Cascadia Code', 'Fira Code', 'JetBrains Mono', 'Courier New', monospace !important;
    font-size: 0.83rem !important;
    line-height: 1.25 !important;
    background-color: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-left: 3px solid #3b82f6 !important;
    border-radius: 6px !important;
    padding: 10px 14px !important;
    margin: 12px 0 !important;
    white-space: pre-wrap !important;
    word-break: break-all !important;
    overflow: visible !important;
}
#book-content #sbo-rt-content pre code,
pre code {
    font-family: inherit !important;
    font-size: inherit !important;
    line-height: inherit !important;
    background: transparent !important;
    padding: 0 !important;
}
code.inlineCode,
:not(pre) > code {
    font-family: 'Consolas', 'Cascadia Code', monospace !important;
    font-size: 0.86em !important;
    background-color: #f1f5f9 !important;
    color: #0f172a !important;
    padding: 2px 5px !important;
    border-radius: 4px !important;
    border: 1px solid #e2e8f0 !important;
}
span.code-highlight {
    background-color: #e0e7ff !important;
    color: #3730a3 !important;
    padding: 1px 4px !important;
    border-radius: 3px !important;
}
::-webkit-scrollbar {
    display: none !important;
    height: 0 !important;
}
h1, h2, h3 {
    color: #1a1f2c;
    page-break-after: avoid;
}
h1 {
    font-size: 2.2rem;
    border-bottom: 2px solid #eaecef;
    padding-bottom: 0.3em;
    margin-top: 1.5em;
}
h2 {
    font-size: 1.5rem;
    border-bottom: 1px solid #eaecef;
    padding-bottom: 0.3em;
    margin-top: 1.3em;
}
blockquote {
    border-left: 4px solid #0366d6;
    background-color: #f1f8ff;
    padding: 10px 15px;
    margin: 15px 0;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 15px 0;
}
th, td {
    border: 1px solid #dfe2e5;
    padding: 8px 12px;
}
th {
    background-color: #f6f8fa;
}
</style>
"""

    def __init__(self, browser_path: Optional[str] = None):
        self.browser_path = browser_path or self._find_browser()
        if not self.browser_path:
            raise RuntimeError(
                "No Chromium-based browser found (Edge, Chrome, Chromium). "
                "Please install Microsoft Edge or Google Chrome to enable PDF compilation."
            )

    def _find_browser(self) -> Optional[str]:
        """Auto-detect Chromium / Edge on Windows, Linux, and macOS."""
        candidates = [
            # Windows
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            # Linux
            shutil.which("microsoft-edge-stable"),
            shutil.which("google-chrome"),
            shutil.which("chromium-browser"),
            shutil.which("chromium"),
            # macOS
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
        for path in candidates:
            if path and os.path.exists(path):
                return path
        return None

    def inject_print_style(self, html_content: str) -> str:
        """Inject print stylesheet into HTML content."""
        if "<head>" in html_content:
            return html_content.replace("<head>", f"<head>{self.PRINT_STYLESHEET}")
        return f"{self.PRINT_STYLESHEET}\n{html_content}"

    def render_to_pdf(self, html_file_path: str, output_pdf_path: str) -> bool:
        """Compile an HTML file into a PDF document."""
        os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
        
        cmd = [
            self.browser_path,
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={output_pdf_path}",
            html_file_path
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return os.path.exists(output_pdf_path) and os.path.getsize(output_pdf_path) > 0
        except Exception as e:
            print(f"[Renderer Error] {e}")
            return False
