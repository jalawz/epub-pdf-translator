import os
import re
import json
import shutil
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class BookLibrary:
    """Manages translated and converted books organized by target language in a self-hosted repository."""

    def __init__(self, root_dir: str = "output"):
        self.root_dir = os.path.abspath(root_dir)
        self.library_dir = os.path.join(self.root_dir, "library")
        os.makedirs(self.library_dir, exist_ok=True)

    @staticmethod
    def slugify(title: str) -> str:
        """Create a filesystem-friendly slug for book folders."""
        slug = re.sub(r'[^a-zA-Z0-9_\-]', '_', title)
        slug = re.sub(r'_+', '_', slug).strip('_')
        return slug or "unnamed_book"

    def add_book(
        self,
        pdf_path: str,
        epub_path: str,
        metadata: Optional[Dict] = None,
        cover_image_path: Optional[str] = None,
        lang: str = "pt",
        source_lang: str = "en"
    ) -> Dict:
        """Store a translated or converted book into output/library/{lang}/{book_slug}/."""
        metadata = metadata or {}
        lang_code = lang.lower().strip()
        title = metadata.get("title") or os.path.splitext(os.path.basename(pdf_path))[0]
        slug = self.slugify(title)

        book_dir = os.path.join(self.library_dir, lang_code, slug)
        os.makedirs(book_dir, exist_ok=True)

        dest_pdf = os.path.join(book_dir, "book.pdf")
        dest_epub = os.path.join(book_dir, "book.epub")
        dest_cover = os.path.join(book_dir, "cover.png")
        dest_meta = os.path.join(book_dir, "metadata.json")

        # Copy or update PDF
        if os.path.abspath(pdf_path) != os.path.abspath(dest_pdf):
            shutil.copy2(pdf_path, dest_pdf)

        # Copy or update EPUB
        if os.path.abspath(epub_path) != os.path.abspath(dest_epub):
            shutil.copy2(epub_path, dest_epub)

        # Handle Cover Image Thumbnail
        if cover_image_path and os.path.exists(cover_image_path):
            if os.path.abspath(cover_image_path) != os.path.abspath(dest_cover):
                shutil.copy2(cover_image_path, dest_cover)
        else:
            self._generate_cover_thumbnail(dest_pdf, dest_cover)

        # Compute page count and file sizes
        page_count = self._count_pdf_pages(dest_pdf)
        pdf_size_mb = round(os.path.getsize(dest_pdf) / (1024 * 1024), 2)
        epub_size_mb = round(os.path.getsize(dest_epub) / (1024 * 1024), 2)

        record = {
            "title": title,
            "author": metadata.get("author") or "Autor Desconhecido",
            "slug": slug,
            "lang": lang_code,
            "source_lang": source_lang.lower().strip(),
            "pages": page_count,
            "pdf_size_mb": pdf_size_mb,
            "epub_size_mb": epub_size_mb,
            "date_added": metadata.get("date_added") or datetime.now().isoformat(),
            "quality_certified": metadata.get("quality_certified", True),
            "pdf_path": dest_pdf,
            "epub_path": dest_epub,
            "cover_path": dest_cover if os.path.exists(dest_cover) else None
        }

        with open(dest_meta, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)

        logger.info(f"Book registered in library: [{lang_code}] {title} -> {book_dir}")
        return record

    def list_books(self, lang: Optional[str] = None) -> List[Dict]:
        """List all books in the library, optionally filtered by language, ordered by date_added desc."""
        books = []
        if not os.path.exists(self.library_dir):
            return books

        target_langs = []
        if lang and lang.lower() not in ["todos", "all", ""]:
            lang_dir = os.path.join(self.library_dir, lang.lower().strip())
            if os.path.exists(lang_dir):
                target_langs = [lang_dir]
        else:
            target_langs = [
                os.path.join(self.library_dir, d)
                for d in os.listdir(self.library_dir)
                if os.path.isdir(os.path.join(self.library_dir, d))
            ]

        for l_dir in target_langs:
            lang_code = os.path.basename(l_dir)
            for item in os.listdir(l_dir):
                book_dir = os.path.join(l_dir, item)
                if not os.path.isdir(book_dir):
                    continue
                meta_file = os.path.join(book_dir, "metadata.json")
                if os.path.exists(meta_file):
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        data["book_dir"] = book_dir
                        data["pdf_path"] = os.path.join(book_dir, "book.pdf")
                        data["epub_path"] = os.path.join(book_dir, "book.epub")
                        cover_candidate = os.path.join(book_dir, "cover.png")
                        data["cover_path"] = cover_candidate if os.path.exists(cover_candidate) else None
                        books.append(data)
                    except Exception as e:
                        logger.error(f"Error reading metadata from {meta_file}: {e}")

        # Sort by date added descending
        books.sort(key=lambda x: x.get("date_added", ""), reverse=True)
        return books

    def get_book(self, lang: str, slug: str) -> Optional[Dict]:
        """Retrieve single book record by language and slug."""
        book_dir = os.path.join(self.library_dir, lang.lower().strip(), slug)
        meta_file = os.path.join(book_dir, "metadata.json")
        if os.path.exists(meta_file):
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["book_dir"] = book_dir
            data["pdf_path"] = os.path.join(book_dir, "book.pdf")
            data["epub_path"] = os.path.join(book_dir, "book.epub")
            cover_candidate = os.path.join(book_dir, "cover.png")
            data["cover_path"] = cover_candidate if os.path.exists(cover_candidate) else None
            return data
        return None

    def delete_book(self, lang: str, slug: str) -> bool:
        """Safely delete a book and its files from the library."""
        book_dir = os.path.join(self.library_dir, lang.lower().strip(), slug)
        if os.path.exists(book_dir) and os.path.isdir(book_dir):
            shutil.rmtree(book_dir, ignore_errors=True)
            return True
        return False

    def scan_and_migrate_legacy(self) -> List[Dict]:
        """Automatically detect legacy translated books in output/ and register them in the library."""
        migrated = []
        if not os.path.exists(self.root_dir):
            return migrated

        # Find .pdf and matching .epub in output root
        for fname in os.listdir(self.root_dir):
            if fname.lower().endswith(".pdf") and not fname.startswith("test_"):
                pdf_path = os.path.join(self.root_dir, fname)
                base_name = os.path.splitext(fname)[0]
                epub_candidate = os.path.join(self.root_dir, f"{base_name}.epub")

                if not os.path.exists(epub_candidate):
                    # Check if there is an epub matching pattern
                    for ep in os.listdir(self.root_dir):
                        if ep.lower().endswith(".epub") and ep.startswith(base_name.split("_for_")[0]):
                            epub_candidate = os.path.join(self.root_dir, ep)
                            break

                if os.path.exists(epub_candidate):
                    # Determine target language from filename or default to 'pt'
                    lang = "pt"
                    if "_for_pt" in fname.lower() or "_pt" in fname.lower():
                        lang = "pt"
                    elif "_for_es" in fname.lower() or "_es" in fname.lower():
                        lang = "es"
                    elif "_for_en" in fname.lower() or "_en" in fname.lower():
                        lang = "en"

                    clean_title = re.sub(r'__for_[a-zA-Z]+', '', base_name)
                    clean_title = re.sub(r'_[A-Z]{2}$', '', clean_title).replace('_', ' ')

                    slug = self.slugify(clean_title)
                    existing = self.get_book(lang, slug)
                    if not existing:
                        logger.info(f"Migrating legacy book '{clean_title}' to library [{lang}]...")
                        record = self.add_book(
                            pdf_path=pdf_path,
                            epub_path=epub_candidate,
                            metadata={
                                "title": clean_title,
                                "author": "Magnus Larsson" if "Microservices" in clean_title else "Desconhecido",
                                "quality_certified": True
                            },
                            lang=lang,
                            source_lang="en"
                        )
                        migrated.append(record)
        return migrated

    def _generate_cover_thumbnail(self, pdf_path: str, output_image_path: str) -> bool:
        """Render page 0 of the PDF as a high-quality thumbnail image."""
        try:
            import fitz
            doc = fitz.open(pdf_path)
            if len(doc) > 0:
                page = doc.load_page(0)
                # 150 DPI provides crisp thumbnail without huge file size
                pix = page.get_pixmap(dpi=150)
                pix.save(output_image_path)
                doc.close()
                return True
            doc.close()
        except Exception as e:
            logger.warning(f"Failed to generate cover thumbnail with PyMuPDF: {e}")
        return False

    def _count_pdf_pages(self, pdf_path: str) -> int:
        """Count total pages in the PDF file."""
        try:
            import fitz
            doc = fitz.open(pdf_path)
            count = len(doc)
            doc.close()
            return count
        except Exception:
            try:
                import pypdf
                reader = pypdf.PdfReader(pdf_path)
                return len(reader.pages)
            except Exception:
                return 0
