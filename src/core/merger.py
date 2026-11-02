import os
import zipfile
from typing import List, Dict
import pypdf

class DocumentMerger:
    """Merges individual chapter outputs into unified book publications (PDF and EPUB)."""

    @staticmethod
    def merge_pdfs(pdf_paths: List[str], output_pdf_path: str, chapter_titles: List[str] = None) -> bool:
        """Combine multiple chapter PDFs into a single comprehensive master PDF."""
        os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
        merger = pypdf.PdfMerger()

        for i, pdf_path in enumerate(pdf_paths):
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                title = chapter_titles[i] if chapter_titles and i < len(chapter_titles) else f"Chapter {i+1}"
                merger.append(pdf_path, outline_item=title)

        with open(output_pdf_path, "wb") as f_out:
            merger.write(f_out)
        merger.close()

        return os.path.exists(output_pdf_path) and os.path.getsize(output_pdf_path) > 0

    @staticmethod
    def pack_epub(original_epub_path: str, translated_files: Dict[str, str], output_epub_path: str) -> bool:
        """Re-pack translated chapter files into a clean standard .epub package."""
        os.makedirs(os.path.dirname(output_epub_path), exist_ok=True)
        
        with zipfile.ZipFile(original_epub_path, "r") as zin:
            with zipfile.ZipFile(output_epub_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename in translated_files:
                        # Write translated content
                        content = translated_files[item.filename].encode("utf-8")
                        zout.writestr(item, content)
                    else:
                        # Copy original assets (images, css, fonts, metadata)
                        zout.writestr(item, zin.read(item.filename))

        return os.path.exists(output_epub_path) and os.path.getsize(output_epub_path) > 0
