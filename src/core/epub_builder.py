import os
import re
import uuid
import zipfile
import mimetypes
from datetime import datetime
from typing import List, Dict, Optional

class EpubBuilder:
    """Constructs a clean, valid, reflowable EPUB 3.0 publication from structured chapter content."""

    DEFAULT_STYLESHEET = """
@charset "utf-8";

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Georgia, serif;
    font-size: 1.05em;
    line-height: 1.65;
    color: #1e293b;
    margin: 5% 7%;
    padding: 0;
}

h1 {
    font-size: 2.0em;
    font-weight: 800;
    line-height: 1.25;
    color: #0f172a;
    margin-top: 1.5em;
    margin-bottom: 0.6em;
    page-break-before: always;
}

h2 {
    font-size: 1.45em;
    font-weight: 700;
    color: #1e293b;
    margin-top: 1.3em;
    margin-bottom: 0.5em;
}

h3 {
    font-size: 1.2em;
    font-weight: 600;
    color: #334155;
    margin-top: 1.1em;
    margin-bottom: 0.4em;
}

p {
    margin-top: 0;
    margin-bottom: 1.1em;
    text-align: justify;
    text-justify: inter-word;
    hyphens: auto;
}

blockquote {
    border-left: 4px solid #3b82f6;
    margin: 1.2em 0;
    padding: 0.6em 1.2em;
    background-color: #f8fafc;
    color: #334155;
    font-style: italic;
}

ul, ol {
    margin-top: 0;
    margin-bottom: 1.1em;
    padding-left: 1.8em;
}

li {
    margin-bottom: 0.4em;
    line-height: 1.5;
}

pre, code {
    font-family: "JetBrains Mono", "Fira Code", Consolas, "Courier New", monospace;
    font-size: 0.88em;
}

pre {
    background-color: #f1f5f9;
    border: 1px solid #e2e8f0;
    border-left: 4px solid #0284c7;
    border-radius: 6px;
    padding: 12px 14px;
    margin: 1.2em 0;
    overflow-x: auto;
    white-space: pre-wrap;
    word-wrap: break-word;
    line-height: 1.4;
}

figure {
    margin: 1.5em auto;
    text-align: center;
}

img {
    max-width: 100%;
    height: auto;
    border-radius: 4px;
}

figcaption {
    font-size: 0.85em;
    color: #64748b;
    margin-top: 0.5em;
    font-style: italic;
}

.cover-container {
    width: 100%;
    height: 100vh;
    margin: 0;
    padding: 0;
    text-align: center;
}

.cover-image {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
}
"""

    def __init__(self, title: str, author: str = "Desconhecido", lang: str = "pt", book_id: Optional[str] = None):
        self.title = title.strip() or "Livro Digitalizado"
        self.author = author.strip() or "Autor Desconhecido"
        self.lang = lang.lower().strip() or "pt"
        self.book_id = book_id or f"urn:uuid:{uuid.uuid4()}"
        self.chapters: List[Dict] = []
        self.images: Dict[str, str] = {}  # {manifest_id: local_file_path}
        self.cover_path: Optional[str] = None

    def set_cover(self, image_path: str):
        """Set cover image file path."""
        if os.path.exists(image_path):
            self.cover_path = image_path

    def add_chapter(self, title: str, blocks: List[Dict], chapter_id: Optional[str] = None) -> str:
        """Add a chapter consisting of semantic blocks."""
        chap_num = len(self.chapters) + 1
        cid = chapter_id or f"chapter_{chap_num:02d}"
        self.chapters.append({
            "id": cid,
            "title": title.strip() or f"Capítulo {chap_num}",
            "blocks": blocks,
            "filename": f"{cid}.xhtml"
        })
        return cid

    def add_image(self, local_path: str) -> str:
        """Register an image asset and return relative path for XHTML."""
        if not os.path.exists(local_path):
            return ""
        fname = os.path.basename(local_path)
        img_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', fname)
        self.images[img_id] = local_path
        return f"images/{fname}"

    def _render_blocks_to_html(self, blocks: List[Dict]) -> str:
        """Transform semantic blocks into clean XHTML elements."""
        html_parts = []
        for b in blocks:
            btype = b.get("type", "paragraph")
            text = b.get("text", "").strip()

            if btype == "heading":
                lvl = min(max(int(b.get("level", 2)), 1), 6)
                html_parts.append(f"<h{lvl}>{self._escape(text)}</h{lvl}>")

            elif btype == "paragraph":
                if text:
                    html_parts.append(f"<p>{self._escape(text)}</p>")

            elif btype == "list":
                items = b.get("items", [])
                tag = "ol" if b.get("ordered", False) else "ul"
                if items:
                    lis = "".join(f"<li>{self._escape(item)}</li>" for item in items if item.strip())
                    html_parts.append(f"<{tag}>{lis}</{tag}>")

            elif btype == "code":
                if text:
                    html_parts.append(f"<pre><code>{self._escape(text)}</code></pre>")

            elif btype == "quote":
                if text:
                    html_parts.append(f"<blockquote><p>{self._escape(text)}</p></blockquote>")

            elif btype == "image":
                src = b.get("src", "")
                caption = b.get("caption", "")
                if src:
                    cap_tag = f"<figcaption>{self._escape(caption)}</figcaption>" if caption else ""
                    html_parts.append(f'<figure><img src="{src}" alt="Figura" />{cap_tag}</figure>')

        return "\n".join(html_parts)

    def _escape(self, s: str) -> str:
        """Escape HTML special characters."""
        return (
            s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&#39;")
        )

    def build(self, output_epub_path: str) -> str:
        """Compile and package the entire EPUB 3.0 archive."""
        os.makedirs(os.path.dirname(os.path.abspath(output_epub_path)), exist_ok=True)
        date_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        with zipfile.ZipFile(output_epub_path, "w") as zout:
            # 1. Uncompressed mimetype (must be the first file in archive)
            zout.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

            # 2. META-INF/container.xml
            container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""
            zout.writestr("META-INF/container.xml", container_xml, compress_type=zipfile.ZIP_DEFLATED)

            # 3. OEBPS/styles.css
            zout.writestr("OEBPS/styles.css", self.DEFAULT_STYLESHEET, compress_type=zipfile.ZIP_DEFLATED)

            # 4. Handle Cover
            has_cover = self.cover_path and os.path.exists(self.cover_path)
            cover_img_filename = "cover.jpg"
            if has_cover:
                _, ext = os.path.splitext(self.cover_path)
                ext = ext.lower().lstrip(".")
                mime = "image/png" if ext == "png" else "image/jpeg"
                cover_img_filename = f"cover.{ext}"
                with open(self.cover_path, "rb") as fc:
                    zout.writestr(f"OEBPS/images/{cover_img_filename}", fc.read(), compress_type=zipfile.ZIP_DEFLATED)

                # Cover XHTML
                cover_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{self.lang}">
<head>
    <title>Capa</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body style="margin:0; padding:0; text-align:center;">
    <div class="cover-container">
        <img class="cover-image" src="images/{cover_img_filename}" alt="Capa do Livro"/>
    </div>
</body>
</html>"""
                zout.writestr("OEBPS/cover.xhtml", cover_xhtml, compress_type=zipfile.ZIP_DEFLATED)

            # 5. Handle Embedded Images
            for img_id, img_path in self.images.items():
                if os.path.exists(img_path):
                    with open(img_path, "rb") as fi:
                        zout.writestr(f"OEBPS/images/{os.path.basename(img_path)}", fi.read(), compress_type=zipfile.ZIP_DEFLATED)

            # 6. Chapters XHTML
            for chap in self.chapters:
                body_content = self._render_blocks_to_html(chap["blocks"])
                chap_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{self.lang}">
<head>
    <title>{self._escape(chap["title"])}</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
    <h1>{self._escape(chap["title"])}</h1>
    {body_content}
</body>
</html>"""
                zout.writestr(f"OEBPS/{chap['filename']}", chap_xhtml, compress_type=zipfile.ZIP_DEFLATED)

            # 7. Navigation document (EPUB 3: nav.xhtml)
            nav_links = "".join(f'<li><a href="{c["filename"]}">{self._escape(c["title"])}</a></li>\n' for c in self.chapters)
            nav_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{self.lang}">
<head>
    <title>Sumário</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
    <nav epub:type="toc" id="toc">
        <h1>Sumário</h1>
        <ol>
            {nav_links}
        </ol>
    </nav>
</body>
</html>"""
            zout.writestr("OEBPS/nav.xhtml", nav_xhtml, compress_type=zipfile.ZIP_DEFLATED)

            # 8. Legacy NCX (EPUB 2 backward compatibility: toc.ncx)
            nav_points = []
            for idx, c in enumerate(self.chapters, start=1):
                nav_points.append(f"""    <navPoint id="navPoint-{idx}" playOrder="{idx}">
      <navLabel><text>{self._escape(c["title"])}</text></navLabel>
      <content src="{c["filename"]}"/>
    </navPoint>""")
            toc_ncx = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{self.book_id}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{self._escape(self.title)}</text></docTitle>
  <docAuthor><text>{self._escape(self.author)}</text></docAuthor>
  <navMap>
{chr(10).join(nav_points)}
  </navMap>
</ncx>"""
            zout.writestr("OEBPS/toc.ncx", toc_ncx, compress_type=zipfile.ZIP_DEFLATED)

            # 9. Package Manifest (OEBPS/content.opf)
            manifest_items = [
                '<item id="style" href="styles.css" media-type="text/css"/>',
                '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
            ]
            spine_items = []

            if has_cover:
                _, ext = os.path.splitext(self.cover_path)
                ext = ext.lower().lstrip(".")
                mime = "image/png" if ext == "png" else "image/jpeg"
                manifest_items.append(f'<item id="cover-image" href="images/{cover_img_filename}" media-type="{mime}" properties="cover-image"/>')
                manifest_items.append('<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>')
                spine_items.append('<itemref idref="cover" linear="no"/>')

            for c in self.chapters:
                manifest_items.append(f'<item id="{c["id"]}" href="{c["filename"]}" media-type="application/xhtml+xml"/>')
                spine_items.append(f'<itemref idref="{c["id"]}"/>')

            for img_id, img_path in self.images.items():
                fname = os.path.basename(img_path)
                m_type, _ = mimetypes.guess_type(fname)
                m_type = m_type or "image/png"
                manifest_items.append(f'<item id="{img_id}" href="images/{fname}" media-type="{m_type}"/>')

            content_opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{self._escape(self.title)}</dc:title>
    <dc:creator>{self._escape(self.author)}</dc:creator>
    <dc:language>{self.lang}</dc:language>
    <dc:identifier id="BookId">{self.book_id}</dc:identifier>
    <meta property="dcterms:modified">{date_str}</meta>
  </metadata>
  <manifest>
    {chr(10).join(f"    {item}" for item in manifest_items)}
  </manifest>
  <spine toc="ncx">
    {chr(10).join(f"    {item}" for item in spine_items)}
  </spine>
  <guide>
    <reference type="toc" title="Sumário" href="nav.xhtml"/>
    {"<reference type='cover' title='Capa' href='cover.xhtml'/>" if has_cover else ""}
  </guide>
</package>"""
            zout.writestr("OEBPS/content.opf", content_opf, compress_type=zipfile.ZIP_DEFLATED)

        return output_epub_path
