import os
import re
import statistics
from typing import List, Dict, Tuple, Optional
import fitz
from PIL import Image

try:
    from rapidocr_onnxruntime import RapidOCR
except ImportError:
    RapidOCR = None

class LayoutOcrEngine:
    """Extracts text, preserves reading order, detects semantic elements (headings, paragraphs, lists, code) and figures from scanned page images."""

    @staticmethod
    def _ensure_models(models_dir: str):
        """Automatically fetch lightweight Latin OCR models if not present."""
        os.makedirs(models_dir, exist_ok=True)
        latin_model = os.path.join(models_dir, "latin_PP-OCRv3_rec_infer.onnx")
        latin_dict = os.path.join(models_dir, "latin_dict.txt")

        if not os.path.exists(latin_model):
            try:
                import urllib.request
                url = "https://huggingface.co/breezedeus/cnocr-ppocr-latin_PP-OCRv3/resolve/main/latin_PP-OCRv3_rec_infer.onnx"
                urllib.request.urlretrieve(url, latin_model)
            except Exception:
                pass

        if not os.path.exists(latin_dict):
            try:
                import urllib.request
                url = "https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/release/2.7/ppocr/utils/dict/latin_dict.txt"
                urllib.request.urlretrieve(url, latin_dict)
            except Exception:
                pass

    def __init__(self, lang: str = "pt", models_dir: Optional[str] = None):
        self.lang = lang.lower().strip()
        models_dir = models_dir or os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
        self._ensure_models(models_dir)

        latin_model = os.path.join(models_dir, "latin_PP-OCRv3_rec_infer.onnx")
        latin_dict = os.path.join(models_dir, "latin_dict.txt")

        # Use Latin specialized OCR engine for Romance/Germanic languages if available
        if self.lang in ["pt", "es", "en", "fr", "de", "it"] and os.path.exists(latin_model) and os.path.exists(latin_dict):
            self.engine = RapidOCR(
                rec_model_path=latin_model,
                rec_keys_path=latin_dict
            )
        else:
            self.engine = RapidOCR() if RapidOCR else None

    def process_page(
        self,
        page: fitz.Page,
        page_num: int,
        assets_output_dir: str,
        dpi: int = 150
    ) -> List[Dict]:
        """Perform OCR on a single PDF page and reconstruct semantic blocks."""
        if not self.engine:
            raise RuntimeError("RapidOCR engine is not initialized or not installed.")

        page_rect = page.rect
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")

        ocr_results, _ = self.engine(img_bytes)
        if not ocr_results:
            return []

        # 1. Parse boxes and filter low-confidence noise
        valid_boxes = []
        for box, text, score in ocr_results:
            text = text.strip()
            if not text or score < 0.40:
                continue

            xs = [pt[0] for pt in box]
            ys = [pt[1] for pt in box]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            h = y_max - y_min
            w = x_max - x_min

            valid_boxes.append({
                "x_min": x_min,
                "x_max": x_max,
                "y_min": y_min,
                "y_max": y_max,
                "height": h,
                "width": w,
                "text": text,
                "score": score
            })

        if not valid_boxes:
            return []

        # 2. Compute page layout statistics (median height, median left margin)
        heights = [b["height"] for b in valid_boxes]
        median_height = statistics.median(heights) if heights else 20.0
        
        # Sort boxes primarily in top-to-bottom reading order
        valid_boxes.sort(key=lambda b: (b["y_min"]))

        # 3. Filter out running headers and footers (page numbers, running chapter title)
        page_h_pixels = pix.height
        filtered_boxes = []
        for b in valid_boxes:
            is_top_margin = b["y_min"] < (page_h_pixels * 0.05)
            is_bottom_margin = b["y_max"] > (page_h_pixels * 0.95)
            # If line is just a number (page number) in margin
            if (is_top_margin or is_bottom_margin) and (b["text"].isdigit() or len(b["text"]) < 6):
                continue
            filtered_boxes.append(b)

        if not filtered_boxes:
            filtered_boxes = valid_boxes

        # 4. Check for embedded illustrations/figures
        figure_blocks = self._extract_page_figures(page, page_num, assets_output_dir)

        # 5. Semantic grouping: headings, lists, code blocks, paragraphs
        blocks: List[Dict] = []
        current_paragraph_lines: List[str] = []
        current_list_items: List[str] = []
        current_code_lines: List[str] = []

        def flush_paragraph():
            nonlocal current_paragraph_lines
            if current_paragraph_lines:
                # Merge hyphenated line breaks: "cons- \ntitui" -> "constitui"
                merged_text = " ".join(current_paragraph_lines)
                merged_text = re.sub(r'(\b\w+)-\s+(\w+\b)', r'\1\2', merged_text)
                merged_text = re.sub(r'\s{2,}', ' ', merged_text).strip()
                if merged_text:
                    blocks.append({"type": "paragraph", "text": merged_text})
                current_paragraph_lines = []

        def flush_list():
            nonlocal current_list_items
            if current_list_items:
                blocks.append({"type": "list", "items": list(current_list_items), "ordered": False})
                current_list_items = []

        def flush_code():
            nonlocal current_code_lines
            if current_code_lines:
                blocks.append({"type": "code", "text": "\n".join(current_code_lines)})
                current_code_lines = []

        prev_box = None
        for b in filtered_boxes:
            txt = b["text"]
            h = b["height"]

            # Code line detector
            is_code_marker = bool(
                re.match(r'^((\$|#|>>>)\s+|import\s+|class\s+|def\s+|public\s+|void\s+|SELECT\s+|curl\s+)', txt) or
                ("{" in txt and "}" in txt) or
                (txt.endswith(";") and ("(" in txt or "=" in txt))
            )

            # Bullet / List item detector
            is_bullet = bool(re.match(r'^([\u2022\u25cf\u25cb\u25aa\*\-\–\—]|\d+[\.\)])\s+', txt))

            # Heading detector (h1, h2, h3)
            is_large_font = h >= (1.35 * median_height)
            is_chapter_title = bool(re.match(r'^(Cap[ií]tulo|Chapter|Se[cç][aã]o|Parte)\s+\d+', txt, re.IGNORECASE))

            if is_chapter_title or (is_large_font and len(txt) < 80):
                flush_paragraph()
                flush_list()
                flush_code()
                level = 1 if (h >= 1.6 * median_height or is_chapter_title) else 2
                blocks.append({"type": "heading", "level": level, "text": txt})
                prev_box = b
                continue

            if is_code_marker:
                flush_paragraph()
                flush_list()
                current_code_lines.append(txt)
                prev_box = b
                continue
            elif current_code_lines:
                flush_code()

            if is_bullet:
                flush_paragraph()
                flush_code()
                clean_bullet_txt = re.sub(r'^([\u2022\u25cf\u25cb\u25aa\*\-\–\—]|\d+[\.\)])\s*', '', txt)
                current_list_items.append(clean_bullet_txt)
                prev_box = b
                continue
            elif current_list_items and prev_box and (b["y_min"] - prev_box["y_max"]) > (1.8 * median_height):
                flush_list()

            # Normal Prose Paragraph
            if prev_box is not None:
                vertical_gap = b["y_min"] - prev_box["y_max"]
                # New paragraph threshold: gap > 1.65 line heights
                if vertical_gap > (1.65 * median_height):
                    flush_paragraph()

            current_paragraph_lines.append(txt)
            prev_box = b

        flush_paragraph()
        flush_list()
        flush_code()

        # Add detected figures at end of page blocks (or interspersed if positions match)
        for fig in figure_blocks:
            blocks.append(fig)

        return blocks

    def _extract_page_figures(self, page: fitz.Page, page_num: int, output_dir: str) -> List[Dict]:
        """Extract embedded image illustrations if any exist beyond full-page background scans."""
        figures = []
        os.makedirs(output_dir, exist_ok=True)
        images = page.get_images(full=True)
        doc = page.parent

        for img_idx, img in enumerate(images):
            xref = img[0]
            try:
                base_img = doc.extract_image(xref)
                if not base_img:
                    continue
                w = base_img["width"]
                h = base_img["height"]
                ext = base_img["ext"]

                # Exclude full-page scanned backgrounds (which cover the entire text)
                page_rect = page.rect
                if w >= (page_rect.width * 0.8) and h >= (page_rect.height * 0.8):
                    continue

                # Filter out tiny icon noise (< 60px)
                if w < 60 or h < 60:
                    continue

                fig_filename = f"fig_p{page_num:03d}_{img_idx+1}.{ext}"
                fig_path = os.path.join(output_dir, fig_filename)
                with open(fig_path, "wb") as f_img:
                    f_img.write(base_img["image"])

                figures.append({
                    "type": "image",
                    "src": f"images/{fig_filename}",
                    "caption": f"Figura {page_num}.{img_idx+1}",
                    "local_path": fig_path
                })
            except Exception:
                continue

        return figures
