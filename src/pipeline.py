import os
import re
import posixpath
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional, Tuple, Dict
from lxml import html as lxml_html

from src.core.epub_parser import EpubParser
from src.core.code_shield import CodeShield
from src.core.translator import BaseTranslatorEngine, BingTranslatorEngine
from src.core.pdf_renderer import PdfRenderer
from src.core.merger import DocumentMerger
from src.core.quality_auditor import QualityAuditor
from src.core.library import BookLibrary

class TranslationPipeline:
    """Orchestrates end-to-end EPUB translation and PDF generation with checkpointing."""

    TAGS_TO_TRANSLATE = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "td", "th", "figcaption"]

    def __init__(
        self,
        epub_path: str,
        output_dir: str = "output",
        lang_in: str = "en",
        lang_out: str = "pt",
        translator: Optional[BaseTranslatorEngine] = None,
        max_workers: int = 5
    ):
        self.epub_path = epub_path
        self.output_dir = output_dir
        self.lang_in = lang_in
        self.lang_out = lang_out
        self.max_workers = max_workers
        self.translator = translator or BingTranslatorEngine(lang_in, lang_out)
        self.parser = EpubParser(epub_path)
        self.renderer = PdfRenderer()

        # Generate slug for cache
        book_title = self.parser.metadata.get("title", "book")
        self.safe_title = re.sub(r'[^a-zA-Z0-9_\-]', '_', book_title).strip('_')
        self.cache_dir = os.path.join(output_dir, "cache", self.safe_title)
        self.assets_dir = os.path.join(self.cache_dir, "assets")
        self.chapters_dir = os.path.join(self.cache_dir, "chapters")
        self.pdfs_dir = os.path.join(self.cache_dir, "pdfs")

        os.makedirs(self.assets_dir, exist_ok=True)
        os.makedirs(self.chapters_dir, exist_ok=True)
        os.makedirs(self.pdfs_dir, exist_ok=True)

    def _translate_chapter_content(self, raw_html: str, chapter_zip_path: str) -> str:
        """Parse, shield, and translate the text nodes of a chapter."""
        tree = lxml_html.fromstring(raw_html.encode("utf-8"))
        elements_to_process = []

        is_toc = "TOC" in chapter_zip_path
        if is_toc:
            # For TOC files, translate all navigation anchor links directly
            for a_el in tree.xpath("//a"):
                text = a_el.text_content().strip()
                if text and len(text) > 1 and not text.isdigit():
                    elements_to_process.append(a_el)
        else:
            for tag in self.TAGS_TO_TRANSLATE:
                for el in tree.xpath(f"//{tag}"):
                    # Skip source code blocks
                    if el.xpath("ancestor::pre"):
                        continue
                    # Skip container tags that contain child block tags UNLESS they have direct content before the first child block
                    child_blocks = el.xpath("./p | ./li | ./blockquote | ./ul | ./ol | ./table")
                    if child_blocks:
                        first_block_idx = el.index(child_blocks[0])
                        has_direct_content = bool((el.text or "").strip() or el[:first_block_idx])
                        if not has_direct_content:
                            continue
                    # Skip pure link wrappers (where the container has no content other than a link)
                    is_pure_link = (
                        el.tag in ["li", "ol", "ul"] and
                        len(el) == 1 and el[0].tag == "a" and
                        not (el.text or "").strip() and
                        not (el[0].tail or "").strip()
                    )
                    if is_pure_link:
                        continue
                    text = el.text_content().strip()
                    if text and len(text) > 1 and not text.isdigit():
                        elements_to_process.append(el)

            # Also process standalone navigation links not inside paragraphs
            for a_el in tree.xpath("//li/a | //nav//a | //ol//a | //ul//a"):
                if a_el.xpath("ancestor::p"):
                    continue
                text = a_el.text_content().strip()
                if text and len(text) > 1 and not text.isdigit() and a_el not in elements_to_process:
                    elements_to_process.append(a_el)

        def process_item(item):
            idx, el = item
            if el.tag == "a":
                txt = el.text_content().strip()
                return idx, el, self.translator.translate(txt)

            child_blocks = el.xpath("./p | ./li | ./blockquote | ./ul | ./ol | ./table")
            if child_blocks:
                first_block_idx = el.index(child_blocks[0])
                direct_parts = []
                if el.text:
                    direct_parts.append(el.text)
                for child in el[:first_block_idx]:
                    direct_parts.append(lxml_html.tostring(child, encoding="unicode"))
                inner_html = "".join(direct_parts).strip()
            else:
                inner_html = (el.text or "") + "".join(lxml_html.tostring(c, encoding="unicode") for c in el)
                inner_html = inner_html.strip()

            if not inner_html:
                return idx, el, None

            # First shield full code blocks (<pre>...</pre>)
            pre_masked, code_placeholders = CodeShield.mask_code_blocks(inner_html)
            # Then shield inline HTML tags (<code>, <a>, <em>, <strong>, etc.)
            tag_masked, tag_placeholders = CodeShield.mask_html_tags(pre_masked)

            translated = self.translator.translate(tag_masked)

            # Restore tags and code blocks
            restored_tags = CodeShield.unmask_html_tags(translated, tag_placeholders)
            restored_all = CodeShield.unmask_code_blocks(restored_tags, code_placeholders)
            return idx, el, restored_all

        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(process_item, (i, el)) for i, el in enumerate(elements_to_process)]
            for future in as_completed(futures):
                idx, el, translated_inner = future.result()
                if translated_inner:
                    results.append((el, translated_inner))

        # Update DOM nodes
        for el, translated_inner in results:
            if el.tag == "a":
                el.text = translated_inner
                continue

            child_blocks = el.xpath("./p | ./li | ./blockquote | ./ul | ./ol | ./table")
            if child_blocks:
                try:
                    dummy = lxml_html.fragment_fromstring(f"<div>{translated_inner}</div>")
                    el.text = dummy.text
                    first_block_idx = el.index(child_blocks[0])
                    for old_child in list(el[:first_block_idx]):
                        el.remove(old_child)
                    for i, new_child in enumerate(dummy):
                        el.insert(i, new_child)
                except Exception:
                    el.text = re.sub(r'<[^>]+>', '', translated_inner)
            else:
                try:
                    dummy = lxml_html.fragment_fromstring(f"<div>{translated_inner}</div>")
                    el.clear()
                    el.text = dummy.text
                    for child in dummy:
                        el.append(child)
                except Exception:
                    el.clear()
                    el.text = re.sub(r'<[^>]+>', '', translated_inner)

        # Fix relative paths to extracted assets
        chapter_dir_in_zip = posixpath.dirname(chapter_zip_path)
        html_str = lxml_html.tostring(tree, encoding="utf-8").decode("utf-8")

        # Resolve asset paths (Images, Styles, Fonts)
        # Point them to the extracted assets folder
        rel_assets_path = os.path.relpath(self.assets_dir, self.chapters_dir).replace("\\", "/")
        
        # Replace relative hrefs and srcs with absolute or correct relative paths
        def fix_asset_url(match):
            attr, quote, url = match.groups()
            if url.startswith(("http://", "https://", "data:", "#")):
                return match.group(0)
            clean_url = url.lstrip("/\\")
            norm_url = posixpath.normpath(posixpath.join(chapter_dir_in_zip, clean_url)) if chapter_dir_in_zip else clean_url
            return f'{attr}={quote}{rel_assets_path}/{norm_url}{quote}'

        html_str = re.sub(r'(src|href)=([\'\"])([^\'\"]+)\2', fix_asset_url, html_str)
        return html_str

    def run(
        self,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        force_recompile: bool = False,
        keep_cache: bool = False
    ) -> Tuple[str, str]:
        """Execute translation across all spine chapters with checkpointing."""
        # Step 1: Extract assets
        if progress_callback:
            progress_callback(0.05, "Extracting book styles and media assets...")
        self.parser.extract_assets(self.assets_dir)

        spine_items = self.parser.spine
        total_items = len(spine_items)
        generated_pdfs = []
        translated_files_for_epub: Dict[str, str] = {}
        chapter_titles = []

        # Helper to clean code and terminal blocks
        def fix_pre(match):
            c = match.group(0).replace("\r\n", "\n").replace("\r", "\n")
            c = re.sub(r'\n{2,}', '\n', c)
            return c

        # Step 2: Translate and compile chapters
        for i, chapter_path in enumerate(spine_items):
            step_progress = 0.05 + 0.85 * (i / total_items)
            chap_name = os.path.basename(chapter_path)
            chapter_id = os.path.splitext(chap_name)[0]
            chapter_titles.append(chapter_id.replace("_", " ").title())

            if progress_callback:
                progress_callback(step_progress, f"Processing [{i+1}/{total_items}]: {chapter_id}...")

            cached_html_file = os.path.join(self.chapters_dir, f"{chapter_id}.html")
            cached_pdf_file = os.path.join(self.pdfs_dir, f"{chapter_id}.pdf")

            # Check cache
            if os.path.exists(cached_html_file):
                with open(cached_html_file, "r", encoding="utf-8") as f:
                    chapter_html = f.read()

                is_cover = (chapter_id.lower() == "cover")
                if force_recompile or not os.path.exists(cached_pdf_file):
                    # Clean code blocks and apply print styles
                    chapter_html = re.sub(r'<pre[^>]*>.*?</pre>', fix_pre, chapter_html, flags=re.DOTALL)
                    printable_html = self.renderer.inject_print_style(chapter_html, is_cover=is_cover)
                    with open(cached_html_file, "w", encoding="utf-8", newline="\n") as f:
                        f.write(printable_html)
                    self.renderer.render_to_pdf(cached_html_file, cached_pdf_file)

                translated_files_for_epub[chapter_path] = chapter_html
                generated_pdfs.append(cached_pdf_file)
                continue

            # Translate
            raw_html = self.parser.get_chapter_content(chapter_path)
            translated_html = self._translate_chapter_content(raw_html, chapter_path)
            translated_files_for_epub[chapter_path] = translated_html

            # Clean up excessive blank lines in code blocks and terminal commands
            translated_html = re.sub(r'<pre[^>]*>.*?</pre>', fix_pre, translated_html, flags=re.DOTALL)

            # Inject printable style
            is_cover = (chapter_id.lower() == "cover")
            printable_html = self.renderer.inject_print_style(translated_html, is_cover=is_cover)
            with open(cached_html_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(printable_html)

            # Render PDF for chapter
            self.renderer.render_to_pdf(cached_html_file, cached_pdf_file)
            generated_pdfs.append(cached_pdf_file)

        # Step 3: Automated Quality Gate Audit
        audit_results = {}
        total_suspicious = 0
        for chap_path, chap_html in translated_files_for_epub.items():
            chap_id = os.path.splitext(os.path.basename(chap_path))[0]
            flagged = QualityAuditor.audit_html(chap_html)
            if flagged:
                audit_results[chap_id] = flagged
                total_suspicious += len(flagged)

        import json
        audit_report_path = os.path.join(self.output_dir, "translation_quality_report.json")
        with open(audit_report_path, "w", encoding="utf-8") as f_aud:
            json.dump({
                "book": self.safe_title,
                "total_chapters": len(translated_files_for_epub),
                "untranslated_prose_count": total_suspicious,
                "quality_certified": (total_suspicious == 0),
                "flagged_elements": audit_results
            }, f_aud, indent=2, ensure_ascii=False)

        # Step 4: Merge into master documents
        if progress_callback:
            progress_callback(0.92, "Consolidating master PDF publication...")

        final_pdf_path = os.path.join(self.output_dir, f"{self.safe_title}_{self.lang_out.upper()}.pdf")
        final_epub_path = os.path.join(self.output_dir, f"{self.safe_title}_{self.lang_out.upper()}.epub")

        DocumentMerger.merge_pdfs(generated_pdfs, final_pdf_path, chapter_titles, spine_items)

        if progress_callback:
            progress_callback(0.97, "Packaging translated EPUB package...")

        DocumentMerger.pack_epub(self.epub_path, translated_files_for_epub, final_epub_path)

        # Step 5: Register publication in self-hosted BookLibrary
        try:
            library = BookLibrary(self.output_dir)
            library.add_book(
                pdf_path=final_pdf_path,
                epub_path=final_epub_path,
                metadata={
                    "title": self.parser.metadata.get("title") or self.safe_title,
                    "author": self.parser.metadata.get("creator") or "Autor Desconhecido",
                    "quality_certified": (total_suspicious == 0)
                },
                lang=self.lang_out,
                source_lang=self.lang_in
            )
        except Exception as e:
            print(f"Warning: Failed to auto-register in library: {e}")

        # Step 6: Cleanup intermediate broken/split chapter PDFs if keep_cache is False
        if not keep_cache and os.path.exists(self.pdfs_dir):
            for pdf_f in os.listdir(self.pdfs_dir):
                p = os.path.join(self.pdfs_dir, pdf_f)
                try:
                    if os.path.isfile(p):
                        os.remove(p)
                except Exception:
                    pass

        if progress_callback:
            progress_callback(1.0, f"Complete! Output ready in {self.output_dir}")

        return final_pdf_path, final_epub_path
