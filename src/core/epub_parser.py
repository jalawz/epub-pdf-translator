import os
import zipfile
import posixpath
from typing import List, Dict, Tuple
from lxml import etree

class EpubParser:
    """Universal parser for EPUB publications based on IDPF/W3C standards."""
    
    def __init__(self, epub_path: str):
        if not os.path.exists(epub_path):
            raise FileNotFoundError(f"EPUB file not found: {epub_path}")
        self.epub_path = epub_path
        self.zip_ref = zipfile.ZipFile(epub_path, "r")
        self.opf_path = self._find_opf()
        self.opf_dir = posixpath.dirname(self.opf_path)
        self.metadata, self.manifest, self.spine = self._parse_opf()

    def _find_opf(self) -> str:
        """Find the path to the main .opf file via META-INF/container.xml."""
        try:
            container_xml = self.zip_ref.read("META-INF/container.xml")
            tree = etree.fromstring(container_xml)
            ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
            rootfile = tree.xpath("//c:rootfile/@full-path", namespaces=ns)
            if rootfile:
                return rootfile[0]
        except Exception:
            pass
        
        # Fallback: scan for any .opf file in the archive
        for name in self.zip_ref.namelist():
            if name.endswith(".opf"):
                return name
        raise ValueError("Invalid EPUB: No package document (.opf) found.")

    def _parse_opf(self) -> Tuple[Dict[str, str], Dict[str, str], List[str]]:
        """Parse OPF document for metadata, manifest items and spine reading order."""
        opf_data = self.zip_ref.read(self.opf_path)
        tree = etree.fromstring(opf_data)
        ns = {
            "opf": "http://www.idpf.org/2007/opf",
            "dc": "http://purl.org/dc/elements/1.1/"
        }
        
        # Metadata
        title_el = tree.xpath("//dc:title/text()", namespaces=ns)
        creator_el = tree.xpath("//dc:creator/text()", namespaces=ns)
        metadata = {
            "title": title_el[0] if title_el else os.path.splitext(os.path.basename(self.epub_path))[0],
            "creator": creator_el[0] if creator_el else "Unknown Author"
        }
        
        # Manifest
        manifest = {}
        for item in tree.xpath("//opf:item", namespaces=ns):
            item_id = item.get("id")
            href = item.get("href")
            # Resolve relative to OPF location inside zip
            full_href = posixpath.normpath(posixpath.join(self.opf_dir, href)) if self.opf_dir else href
            manifest[item_id] = full_href
            
        # Spine
        spine = []
        for itemref in tree.xpath("//opf:itemref", namespaces=ns):
            idref = itemref.get("idref")
            if idref in manifest:
                spine.append(manifest[idref])
                
        return metadata, manifest, spine

    def extract_assets(self, target_dir: str):
        """Extract CSS styles and images required for proper visual rendering."""
        os.makedirs(target_dir, exist_ok=True)
        for name in self.zip_ref.namelist():
            lower = name.lower()
            if lower.endswith((".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ttf", ".woff", ".woff2")):
                dest_path = os.path.join(target_dir, os.path.normpath(name))
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                with open(dest_path, "wb") as f:
                    f.write(self.zip_ref.read(name))

    def get_chapter_content(self, chapter_path: str) -> str:
        """Read and decode the content of a chapter file."""
        return self.zip_ref.read(chapter_path).decode("utf-8", errors="replace")

    def close(self):
        self.zip_ref.close()
