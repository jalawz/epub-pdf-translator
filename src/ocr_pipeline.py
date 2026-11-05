import os
import re
import shutil
import logging
from typing import Callable, Optional, Tuple, Dict, List
import fitz

from src.core.scanned_detector import ScannedPdfDetector
from src.core.layout_ocr import LayoutOcrEngine
from src.core.epub_builder import EpubBuilder
from src.core.library import BookLibrary

logger = logging.getLogger(__name__)

class OcrToEpubPipeline:
    """End-to-end pipeline to convert scanned/photographed PDFs into clean, reflowable EPUB 3.0 publications."""

    def __init__(
        self,
        pdf_path: str,
        output_dir: str = "output",
        lang: str = "pt",
        title: Optional[str] = None,
        author: Optional[str] = None
    ):
        self.pdf_path = os.path.abspath(pdf_path)
        self.output_dir = os.path.abspath(output_dir)
        self.lang = lang.lower().strip() or "pt"
        
        # Derive title and slug
        default_title = os.path.splitext(os.path.basename(pdf_path))[0].replace("_", " ").title()
        self.title = (title or "").strip() or default_title
        self.author = (author or "").strip() or "Autor Desconhecido"
        
        self.safe_slug = re.sub(r'[^a-zA-Z0-9_\-]', '_', self.title)
        self.safe_slug = re.sub(r'_+', '_', self.safe_slug).strip('_')

        self.cache_dir = os.path.join(self.output_dir, "cache", f"ocr_{self.safe_slug}")
        self.assets_dir = os.path.join(self.cache_dir, "assets")
        os.makedirs(self.assets_dir, exist_ok=True)

    def run(self, progress_callback: Optional[Callable[[float, str], None]] = None) -> Tuple[str, Dict]:
        """Execute OCR extraction, layout reconstruction, and EPUB 3.0 packaging."""
        if not os.path.exists(self.pdf_path):
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")

        # Step 1: Analyze PDF
        if progress_callback:
            progress_callback(0.05, "Analisando estrutura e digitalização do PDF...")

        analysis = ScannedPdfDetector.analyze(self.pdf_path)
        doc = fitz.open(self.pdf_path)
        total_pages = len(doc)

        if total_pages == 0:
            doc.close()
            raise ValueError("O arquivo PDF fornecido está vazio (0 páginas).")

        # Step 2: Extract Cover from Page 1
        if progress_callback:
            progress_callback(0.10, "Extraindo e otimizando capa da publicação...")

        cover_path = os.path.join(self.cache_dir, "cover.png")
        page_0 = doc.load_page(0)
        pix_cover = page_0.get_pixmap(dpi=150)
        pix_cover.save(cover_path)

        # Step 3: Initialize OCR Layout Engine
        layout_engine = LayoutOcrEngine(lang=self.lang)

        # Step 4: Process Pages with OCR
        all_page_blocks: List[Tuple[int, List[Dict]]] = []
        
        # We start OCR from page 0 or page 1 (if page 0 is solely a full cover photo)
        start_page = 1 if (total_pages > 1 and analysis["is_scanned"]) else 0
        pages_to_process = list(range(start_page, total_pages))
        num_process_pages = len(pages_to_process)

        for idx, p_num in enumerate(pages_to_process):
            current_progress = 0.12 + 0.73 * (idx / max(num_process_pages, 1))
            if progress_callback:
                progress_callback(
                    current_progress,
                    f"OCR e Segmentação de Layout [Página {p_num + 1}/{total_pages}]..."
                )

            page = doc.load_page(p_num)
            blocks = layout_engine.process_page(
                page=page,
                page_num=p_num + 1,
                assets_output_dir=self.assets_dir,
                dpi=150
            )
            if blocks:
                all_page_blocks.append((p_num + 1, blocks))

        doc.close()

        # Step 5: Partition Blocks into Semantic Chapters
        if progress_callback:
            progress_callback(0.88, "Estruturando capítulos semânticos e sumário...")

        chapters: List[Dict] = []
        current_chap_title = "Prefácio" if start_page > 0 else "Início"
        current_chap_blocks: List[Dict] = []

        for p_num, blocks in all_page_blocks:
            for b in blocks:
                # If a major heading (H1) or chapter marker is encountered, start a new chapter
                if b.get("type") == "heading" and (b.get("level") == 1 or re.match(r'^(Cap[ií]tulo|Chapter)\s+\d+', b.get("text", ""), re.IGNORECASE)):
                    if current_chap_blocks:
                        chapters.append({
                            "title": current_chap_title,
                            "blocks": list(current_chap_blocks)
                        })
                        current_chap_blocks = []
                    current_chap_title = b.get("text", "").strip() or f"Capítulo {len(chapters) + 1}"
                else:
                    current_chap_blocks.append(b)

        if current_chap_blocks:
            chapters.append({
                "title": current_chap_title,
                "blocks": current_chap_blocks
            })

        # Fallback if no headings were detected (e.g. single long article)
        if not chapters:
            flattened = [b for _, blist in all_page_blocks for b in blist]
            chapters.append({
                "title": self.title,
                "blocks": flattened
            })

        # Step 6: Construct EPUB 3.0 Reflowable Package
        if progress_callback:
            progress_callback(0.93, "Empacotando EPUB 3.0 refluxável...")

        epub_builder = EpubBuilder(
            title=self.title,
            author=self.author,
            lang=self.lang
        )

        if os.path.exists(cover_path):
            epub_builder.set_cover(cover_path)

        for idx, chap in enumerate(chapters, start=1):
            chap_id = f"chap_{idx:02d}"
            # Register any figure images inside the chapter
            for b in chap["blocks"]:
                if b.get("type") == "image" and b.get("local_path"):
                    img_rel = epub_builder.add_image(b["local_path"])
                    b["src"] = img_rel

            epub_builder.add_chapter(
                title=chap["title"],
                blocks=chap["blocks"],
                chapter_id=chap_id
            )

        final_epub_path = os.path.join(self.output_dir, f"{self.safe_slug}_OCR.epub")
        epub_builder.build(final_epub_path)

        # Step 7: Post-refine semantic chapters, unify code blocks and polish TOC
        refine_stats = {}
        try:
            if progress_callback:
                progress_callback(0.96, "Refinando estrutura, unificando blocos de código e consolidando sumário...")
            from src.core.epub_refiner import EpubRefiner
            refiner = EpubRefiner(final_epub_path)
            _, refine_stats = refiner.refine(final_epub_path)
        except Exception as e:
            logger.warning(f"Could not post-refine OCR epub: {e}")

        # Step 8: Auto-register in BookLibrary
        if progress_callback:
            progress_callback(0.98, "Catalogando na Biblioteca Digital...")

        try:
            lib = BookLibrary(self.output_dir)
            lib.add_book(
                pdf_path=self.pdf_path,
                epub_path=final_epub_path,
                metadata={
                    "title": self.title,
                    "author": self.author,
                    "quality_certified": True
                },
                cover_image_path=cover_path if os.path.exists(cover_path) else None,
                lang=self.lang,
                source_lang=self.lang
            )
        except Exception as e:
            logger.warning(f"Could not auto-register OCR book in library: {e}")

        # Cleanup intermediate cache assets
        try:
            shutil.rmtree(self.cache_dir, ignore_errors=True)
        except Exception:
            pass

        if progress_callback:
            progress_callback(1.0, f"Conversão concluída! EPUB pronto em {final_epub_path}")

        stats = {
            "title": self.title,
            "author": self.author,
            "total_pages": total_pages,
            "processed_pages": len(all_page_blocks),
            "chapters_created": refine_stats.get("refined_chapters", len(chapters)),
            "code_blocks_merged": refine_stats.get("code_blocks_merged", 0),
            "epub_path": final_epub_path,
            "epub_size_mb": round(os.path.getsize(final_epub_path) / (1024 * 1024), 2)
        }
        return final_epub_path, stats
