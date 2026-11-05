import os
import fitz
from typing import Dict

class ScannedPdfDetector:
    """Analyzes a PDF document to determine if it consists of scanned images/photos rather than digital text."""

    @staticmethod
    def analyze(pdf_path: str, max_sample_pages: int = 10) -> Dict:
        """Inspect the initial pages of a PDF to detect raster/scanned content.
        
        Returns a dictionary with detection metrics:
          - is_scanned: bool
          - total_pages: int
          - avg_text_chars: float
          - raster_page_ratio: float
          - confidence: float
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        sample_count = min(max_sample_pages, total_pages)

        if sample_count == 0:
            doc.close()
            return {"is_scanned": False, "total_pages": 0, "confidence": 0.0}

        total_chars = 0
        pages_with_large_image = 0

        for i in range(sample_count):
            page = doc.load_page(i)
            text = page.get_text("text").strip()
            total_chars += len(text)

            page_rect = page.rect
            page_area = page_rect.width * page_rect.height

            images = page.get_images(full=True)
            has_dominant_image = False
            for img in images:
                xref = img[0]
                try:
                    bbox = page.get_image_bbox(img)
                    img_area = bbox.width * bbox.height
                    # Image covers at least 50% of the page area
                    if page_area > 0 and (img_area / page_area) >= 0.5:
                        has_dominant_image = True
                        break
                except Exception:
                    # Fallback: if at least one image exists and text is nearly empty
                    if len(images) > 0 and len(text) < 100:
                        has_dominant_image = True
                        break

            if has_dominant_image or (len(images) > 0 and len(text) < 80):
                pages_with_large_image += 1

        doc.close()

        avg_chars = total_chars / sample_count
        raster_ratio = pages_with_large_image / sample_count

        # A document is classified as scanned if average vector text is very low (< 120 chars)
        # and most pages contain dominant raster images
        is_scanned = (avg_chars < 150 and raster_ratio >= 0.6) or (avg_chars < 40)
        confidence = raster_ratio if is_scanned else (1.0 - raster_ratio)

        return {
            "is_scanned": is_scanned,
            "total_pages": total_pages,
            "sample_pages": sample_count,
            "avg_text_chars": round(avg_chars, 1),
            "raster_page_ratio": round(raster_ratio, 2),
            "confidence": round(confidence, 2)
        }
