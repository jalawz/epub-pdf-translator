import os
import re
import posixpath
import shutil
import logging
from typing import Callable, Optional, Tuple, Dict
import fitz

from src.core.epub_parser import EpubParser
from src.core.pdf_renderer import PdfRenderer
from src.core.merger import DocumentMerger
from src.core.scanned_detector import ScannedPdfDetector
from src.core.epub_builder import EpubBuilder
from src.core.epub_refiner import EpubRefiner
from src.ocr_pipeline import OcrToEpubPipeline
from src.core.library import BookLibrary

logger = logging.getLogger(__name__)

class FormatConverter:
    """Universal bidirectional format converter between EPUB and PDF."""

    @staticmethod
    def epub_to_pdf(
        epub_path: str,
        output_dir: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> str:
        """Converts an EPUB into a high-resolution, print-ready A4 PDF without translating."""
        if not os.path.exists(epub_path):
            raise FileNotFoundError(f"EPUB not found: {epub_path}")

        os.makedirs(output_dir, exist_ok=True)
        parser = EpubParser(epub_path)
        safe_title = re.sub(r'[^a-zA-Z0-9_\-]', '_', parser.metadata.get("title", "book"))
        safe_title = re.sub(r'_+', '_', safe_title).strip('_')

        cache_dir = os.path.join(output_dir, "cache", f"convert_{safe_title}")
        html_dir = os.path.join(cache_dir, "html")
        pdf_dir = os.path.join(cache_dir, "pdfs")
        assets_dir = os.path.join(cache_dir, "assets")
        os.makedirs(html_dir, exist_ok=True)
        os.makedirs(pdf_dir, exist_ok=True)
        os.makedirs(assets_dir, exist_ok=True)

        if progress_callback:
            progress_callback(0.05, "Extraindo ativos e mídias do EPUB...")
        parser.extract_assets(assets_dir)

        renderer = PdfRenderer()
        generated_pdfs = []
        chapter_titles = []
        spine_items = parser.spine
        total = len(spine_items)

        rel_assets = os.path.relpath(assets_dir, html_dir).replace("\\", "/")

        for idx, chapter_path in enumerate(spine_items):
            chap_name = os.path.basename(chapter_path)
            chapter_id = os.path.splitext(chap_name)[0]
            pct = 0.10 + 0.75 * (idx / max(total, 1))
            if progress_callback:
                progress_callback(pct, f"Diagramando capítulo [{idx + 1}/{total}]: {chapter_id}...")

            raw_html = parser.get_chapter_content(chapter_path)

            chapter_dir_in_zip = posixpath.dirname(chapter_path)
            def fix_asset_url(match):
                attr, quote, url = match.groups()
                if url.startswith(("http://", "https://", "data:", "#")):
                    return match.group(0)
                clean_url = url.lstrip("/\\")
                norm_url = posixpath.normpath(posixpath.join(chapter_dir_in_zip, clean_url)) if chapter_dir_in_zip else clean_url
                return f'{attr}={quote}{rel_assets}/{norm_url}{quote}'

            raw_html = re.sub(r'(src|href)=([\'\"])([^\'\"]+)\2', fix_asset_url, raw_html)

            is_cover = ("cover" in chapter_id.lower())
            printable_html = renderer.inject_print_style(raw_html, is_cover=is_cover)

            chapter_html_path = os.path.join(html_dir, f"{chapter_id}.html")
            with open(chapter_html_path, "w", encoding="utf-8") as fp:
                fp.write(printable_html)

            chapter_pdf_path = os.path.join(pdf_dir, f"{chapter_id}.pdf")
            renderer.render_to_pdf(chapter_html_path, chapter_pdf_path)
            generated_pdfs.append(chapter_pdf_path)
            chapter_titles.append(f"Capítulo {idx + 1}")

        if progress_callback:
            progress_callback(0.92, "Consolidando PDF mestre A4...")

        final_pdf_path = os.path.join(output_dir, f"{safe_title}.pdf")
        DocumentMerger.merge_pdfs(generated_pdfs, final_pdf_path, chapter_titles, spine_items)

        # Cleanup cache
        shutil.rmtree(cache_dir, ignore_errors=True)

        try:
            lib = BookLibrary(output_dir)
            lib.add_book(
                pdf_path=final_pdf_path,
                epub_path=epub_path,
                metadata={
                    "title": parser.metadata.get("title", safe_title),
                    "author": parser.metadata.get("author", "Autor Desconhecido"),
                    "category": "conversion"
                },
                lang="pt",
                source_lang="pt"
            )
        except Exception as e:
            logger.warning(f"Failed to auto-register converted PDF in library: {e}")

        if progress_callback:
            progress_callback(1.0, f"Conversão concluída! PDF gerado em {final_pdf_path}")

        return final_pdf_path

    @staticmethod
    def pdf_to_epub(
        pdf_path: str,
        output_dir: str,
        title: Optional[str] = None,
        author: Optional[str] = None,
        lang: str = "pt",
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[str, Dict]:
        """Converts a PDF (either vector-digital or scanned) into a clean, reflowable EPUB 3.0."""
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        os.makedirs(output_dir, exist_ok=True)
        if progress_callback:
            progress_callback(0.05, "Analisando estrutura do PDF...")

        analysis = ScannedPdfDetector.analyze(pdf_path)
        is_scanned = analysis["is_scanned"]

        if is_scanned:
            # Run OCR pipeline for scanned PDF
            ocr_pipe = OcrToEpubPipeline(
                pdf_path=pdf_path,
                output_dir=output_dir,
                lang=lang,
                title=title,
                author=author
            )
            return ocr_pipe.run(progress_callback=progress_callback)

        # Vector PDF: native fast extraction
        if progress_callback:
            progress_callback(0.20, "Extraindo texto vetorial digital e estrutura...")

        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        derived_title = title or os.path.splitext(os.path.basename(pdf_path))[0].replace("_", " ").title()
        derived_author = author or "Autor Desconhecido"
        safe_slug = re.sub(r'[^a-zA-Z0-9_\-]', '_', derived_title).strip('_')

        epub_builder = EpubBuilder(title=derived_title, author=derived_author, lang=lang)
        cover_path = os.path.join(output_dir, "cache", f"temp_{safe_slug}_cover.png")
        os.makedirs(os.path.dirname(cover_path), exist_ok=True)
        
        # Page 0 cover
        if total_pages > 0:
            p0 = doc[0].get_pixmap(dpi=150)
            p0.save(cover_path)
            epub_builder.set_cover(cover_path)

        chapters = []
        current_blocks = []
        current_chap_title = "Início"

        for pno in range(total_pages):
            pct = 0.25 + 0.65 * (pno / max(total_pages, 1))
            if progress_callback:
                progress_callback(pct, f"Processando página digital [{pno + 1}/{total_pages}]...")

            page = doc[pno]
            text = page.get_text()
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            for line in lines:
                m_chap = re.match(r'^(Cap[ií]tulo|Chapter)\s+\d+.*', line, re.IGNORECASE)
                if m_chap:
                    if current_blocks:
                        chapters.append({"title": current_chap_title, "blocks": current_blocks})
                        current_blocks = []
                    current_chap_title = line
                else:
                    current_blocks.append({"type": "paragraph", "text": line})

        if current_blocks:
            chapters.append({"title": current_chap_title, "blocks": current_blocks})
        doc.close()

        for idx, chap in enumerate(chapters, start=1):
            epub_builder.add_chapter(title=chap["title"], blocks=chap["blocks"], chapter_id=f"chap_{idx:02d}")

        final_epub_path = os.path.join(output_dir, f"{safe_slug}.epub")
        epub_builder.build(final_epub_path)

        # Refine
        refiner = EpubRefiner(final_epub_path)
        refiner.refine(final_epub_path)

        try:
            os.remove(cover_path)
        except Exception:
            pass

        try:
            lib = BookLibrary(output_dir)
            lib.add_book(
                pdf_path=pdf_path,
                epub_path=final_epub_path,
                metadata={
                    "title": derived_title,
                    "author": derived_author,
                    "category": "conversion",
                    "pages": total_pages
                },
                lang=lang,
                source_lang=lang
            )
        except Exception as e:
            logger.warning(f"Failed to auto-register converted EPUB in library: {e}")

        stats = {
            "title": derived_title,
            "author": derived_author,
            "total_pages": total_pages,
            "chapters_created": len(chapters),
            "is_scanned": False,
            "epub_path": final_epub_path,
            "epub_size_mb": round(os.path.getsize(final_epub_path) / (1024 * 1024), 2)
        }
        return final_epub_path, stats
