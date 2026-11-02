import os
import zipfile
from typing import List, Dict
import pypdf

class DocumentMerger:
    """Merges individual chapter outputs into unified book publications (PDF and EPUB)."""

    @staticmethod
    def merge_pdfs(
        pdf_paths: List[str],
        output_pdf_path: str,
        chapter_titles: List[str] = None,
        chapter_keys: List[str] = None
    ) -> bool:
        """Combine multiple chapter PDFs into a single master PDF and convert external chapter links to internal GoTo page jumps."""
        os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
        writer = pypdf.PdfWriter()

        chapter_start_pages = {}
        current_page_idx = 0

        for i, pdf_path in enumerate(pdf_paths):
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                title = chapter_titles[i] if chapter_titles and i < len(chapter_titles) else f"Chapter {i+1}"
                reader = pypdf.PdfReader(pdf_path)
                page_count = len(reader.pages)

                if chapter_keys and i < len(chapter_keys):
                    key = chapter_keys[i]
                    chapter_start_pages[key] = current_page_idx
                    chapter_start_pages[os.path.basename(key)] = current_page_idx
                    base_id = os.path.splitext(os.path.basename(key))[0]
                    chapter_start_pages[f"{base_id}.xhtml"] = current_page_idx
                    chapter_start_pages[f"{base_id}.html"] = current_page_idx

                writer.append(reader, outline_item=title)
                current_page_idx += page_count

        # Convert external URI links targeting chapters into internal PDF page jumps
        from pypdf.generic import DictionaryObject, NameObject, ArrayObject
        for page in writer.pages:
            annots = page.get(NameObject("/Annots"))
            if not annots:
                continue
            for annot_ref in annots:
                try:
                    annot = annot_ref.get_object()
                    if annot.get(NameObject("/Subtype")) != NameObject("/Link"):
                        continue
                    action = annot.get(NameObject("/A"))
                    if not action or action.get(NameObject("/S")) != NameObject("/URI"):
                        continue
                    uri = action.get(NameObject("/URI"), "")

                    for chap_key, target_idx in chapter_start_pages.items():
                        if chap_key in uri:
                            target_page = writer.pages[target_idx]
                            annot[NameObject("/A")] = DictionaryObject({
                                NameObject("/S"): NameObject("/GoTo"),
                                NameObject("/D"): ArrayObject([target_page.indirect_reference, NameObject("/Fit")])
                            })
                            break
                except Exception:
                    continue

        with open(output_pdf_path, "wb") as f_out:
            writer.write(f_out)
        writer.close()

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
