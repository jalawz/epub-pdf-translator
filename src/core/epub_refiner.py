import os
import re
import uuid
import zipfile
import shutil
import logging
import html as pyhtml
from typing import Dict, List, Optional, Tuple
from lxml import html as h

logger = logging.getLogger(__name__)


def _xml_escape(text: str) -> str:
    """Escapa caracteres reservados XML (&, <, >) em texto de conteúdo."""
    if text is None:
        return ""
    return pyhtml.escape(str(text), quote=False)

PROSE_STOPWORDS = {
    'de', 'a', 'o', 'que', 'e', 'do', 'da', 'em', 'um', 'para', 'com', 'nao', 'não',
    'uma', 'os', 'no', 'se', 'na', 'por', 'mais', 'as', 'dos', 'como', 'mas', 'foi',
    'ao', 'ele', 'das', 'tem', 'seu', 'sua', 'ou', 'quando', 'muito', 'nos',
    'ja', 'já', 'eu', 'tambem', 'também', 'so', 'só', 'pelo', 'pela', 'ate', 'até',
    'isso', 'ela', 'entre', 'depois', 'sem', 'mesmo', 'aos', 'seus', 'quem', 'nas',
    'me', 'esse', 'eles', 'voce', 'você', 'essa', 'num', 'nem', 'suas', 'meu',
    'minha', 'numa', 'pelos', 'elas', 'qual', 'nós', 'lhe', 'deles', 'essas',
    'esses', 'pelas', 'este', 'dele', 'tu', 'te', 'voces', 'vocês', 'vos', 'lhes',
    'meus', 'minhas', 'teu', 'tua', 'teus', 'tuas', 'nosso', 'nossa', 'nossos', 'nossas',
    'dela', 'delas', 'esta', 'está', 'estes', 'estas', 'aquele', 'aquela', 'aqueles',
    'aquelas', 'isto', 'aquilo', 'cada', 'apenas', 'coisa', 'consulte', 'pagina', 'página',
    'ordem', 'importante', 'note', 'exemplo', 'onde', 'portanto', 'costumam', 'necessarios'
}

CODE_KEYWORDS = re.compile(
    r'^(for\b|if\b|while\b|else\b|return\b|throw\b|new\b|try\b|catch\b|finally\b|'
    r'private\b|public\b|protected\b|static\b|final\b|abstract\b|class\b|interface\b|'
    r'void\b|int\b|boolean\b|double\b|float\b|long\b|char\b|byte\b|short\b|'
    r'String\b|List<|Map<|Set<|Collection<|ArrayList<|HashMap<|var\b|val\b|def\b|'
    r'@\w+|\$|#|>>>|//|/\*|\*|\}|Gradient|Money|reticulate|saturate|dive|public\s+void|'
    r'payIfNecessary|calculateAndDeliverPay)',
    re.IGNORECASE
)

class EpubRefiner:
    """Refines scanned EPUBs by consolidating fragmented pages into real chapters,
    removing repetitive running headers and page numbers, and merging fragmented code blocks."""

    def __init__(self, epub_path: str):
        self.epub_path = os.path.abspath(epub_path)
        if not os.path.exists(self.epub_path):
            raise FileNotFoundError(f"EPUB file not found: {self.epub_path}")

    @staticmethod
    def is_prose_sentence(text: str) -> bool:
        """Determines if a text line is standard natural language prose."""
        text = text.strip()
        words = [re.sub(r'[^a-zA-ZáéíóúãõâêîôûçÁÉÍÓÚÃÕÂÊÎÔÛÇ]', '', w).lower() for w in text.split()]
        words = [w for w in words if len(w) >= 2]
        if len(words) >= 4:
            stop_count = sum(1 for w in words if w in PROSE_STOPWORDS)
            if stop_count >= 2:
                return True
        return False

    @staticmethod
    def is_code_line(text: str) -> bool:
        """Determines if a line is part of a code snippet."""
        text = text.strip()
        if not text:
            return False
        if EpubRefiner.is_prose_sentence(text):
            return False
        if CODE_KEYWORDS.match(text):
            return True
        if text.endswith((';', '{', '}', '(', ')', ':')):
            return True
        if re.search(r'\b[a-zA-Z_]\w*\.[a-zA-Z_]\w*\(', text) or ('<' in text and '>' in text):
            return True
        if re.match(r'^\s*[\w\<\>\[\]]+\s+[\w]+\s*(=|;|\()', text):
            return True
        return False

    @staticmethod
    def repair_code_syntax(code_text: str) -> str:
        """Fixes common OCR misrecognitions of programming tokens (Java, C#, etc.)."""
        lines = code_text.splitlines()
        repaired = []
        for line in lines:
            l = line.rstrip()
            # OCR 'payi f' or 'pay) f' or 'pay f' -> 'pay() {'
            l = re.sub(r'(\b\w+)\s*i\s*f\s*$', r'\1() {', l)
            l = re.sub(r'(\b\w+)\s*\)\s*f\s*$', r'\1() {', l)
            if re.search(r'\b(void|int|String|class)\s+\w+\s*f\s*$', l):
                l = re.sub(r'\s*f\s*$', r'() {', l)
            # OCR method signature missing opening brace
            if re.match(r'^\s*(public|private|protected)\s+(void|[\w\<\>\[\]]+)\s+\w+\([^\)]*\)\s*$', l):
                l = l + " {"
            # OCR parameters followed by '{ if(': '(Employee e { if(e.isPayday(' -> '(Employee e) { if (e.isPayday())'
            l = re.sub(r'\(([A-Z]\w+)\s+(\w+)\s*\{\s*if\s*\(([\w\.]+)\(', r'(\1 \2) { if (\3()', l)
            # OCR parameter followed by '(' instead of '{': '(Employee e) (' -> '(Employee e) {'
            l = re.sub(r'\(([A-Z]\w+)\s+(\w+)\)\s*\(', r'(\1 \2) {', l)
            # OCR method call ending with ');': 'Money pay=e.calculatePay);' -> 'Money pay = e.calculatePay();'
            l = re.sub(r'(\w+)\s*=\s*(\w+)\.([a-zA-Z_]\w+)\);', r'\1 = \2.\3();', l)
            # OCR call ending with colon instead of semicolon: 'reticulateSplines():' -> 'reticulateSplines();'
            l = re.sub(r'(\w+)\(\):', r'\1();', l)
            # OCR space around equals in variable declaration
            l = re.sub(r'(\b[A-Za-z0-9_]+)\s*=\s*([A-Za-z0-9_]+)', r'\1 = \2', l)
            repaired.append(l)
        return "\n".join(repaired)

    @staticmethod
    def fix_portuguese_ocr_typos(text: str) -> str:
        """Fixes common OCR glyph misrecognitions in Portuguese technical books."""
        text = re.sub(r'\bO C6digo\b', 'O Código', text)
        text = re.sub(r'\bC6digo\b', 'Código', text)
        text = re.sub(r'\bc6digo\b', 'código', text)
        text = re.sub(r'\bC6digos\b', 'Códigos', text)
        text = re.sub(r'\bc6digos\b', 'códigos', text)
        text = re.sub(r'\bFunces\b', 'Funções', text)
        return text

    def refine(self, output_epub_path: Optional[str] = None) -> Tuple[str, Dict]:
        """Refines the EPUB structure and returns the new EPUB path and statistics."""
        out_path = os.path.abspath(output_epub_path or self.epub_path)
        temp_dir = self.epub_path + "_refine_temp"
        os.makedirs(temp_dir, exist_ok=True)

        try:
            with zipfile.ZipFile(self.epub_path, 'r') as z:
                z.extractall(temp_dir)

            oebps_dir = os.path.join(temp_dir, "OEBPS")
            if not os.path.exists(oebps_dir):
                oebps_dir = temp_dir

            # --- Ler metadados originais do content.opf para preservá-los ---
            original_title = _xml_escape(os.path.splitext(os.path.basename(self.epub_path))[0])
            original_author = _xml_escape("Autor Desconhecido")
            original_lang = _xml_escape("pt")
            original_uid = _xml_escape(f"urn:uuid:{uuid.uuid4()}")
            opf_path_orig = os.path.join(oebps_dir, "content.opf")
            if os.path.exists(opf_path_orig):
                try:
                    with open(opf_path_orig, "r", encoding="utf-8", errors="ignore") as fp:
                        opf_orig = fp.read()
                    m_title = re.search(r"<dc:title[^>]*>(.*?)</dc:title>", opf_orig, re.IGNORECASE | re.DOTALL)
                    m_creator = re.search(r"<dc:creator[^>]*>(.*?)</dc:creator>", opf_orig, re.IGNORECASE | re.DOTALL)
                    m_lang = re.search(r"<dc:language[^>]*>(.*?)</dc:language>", opf_orig, re.IGNORECASE | re.DOTALL)
                    m_uid = re.search(r'<dc:identifier[^>]*>(.*?)</dc:identifier>', opf_orig, re.IGNORECASE | re.DOTALL)
                    if m_title:
                        original_title = _xml_escape(re.sub(r'<[^>]+>', '', m_title.group(1)).strip())
                    if m_creator:
                        original_author = _xml_escape(re.sub(r'<[^>]+>', '', m_creator.group(1)).strip())
                    if m_lang:
                        original_lang = _xml_escape(m_lang.group(1).strip())
                    if m_uid:
                        original_uid = _xml_escape(re.sub(r'<[^>]+>', '', m_uid.group(1)).strip())
                except Exception:
                    pass

            # 1. Identify all chapter files sorted numerically
            chap_files = [
                f for f in os.listdir(oebps_dir)
                if f.startswith("chap_") and f.endswith(".xhtml")
            ]
            chap_files.sort(key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0)

            if not chap_files:
                raise ValueError("Nenhum arquivo de capítulo encontrado no EPUB.")

            # 2. Group page-files into real major chapters
            major_sections = []
            for f in chap_files:
                file_path = os.path.join(oebps_dir, f)
                with open(file_path, "r", encoding="utf-8", errors="ignore") as fp:
                    content = fp.read()
                tree = h.fromstring(content.encode("utf-8"))
                h1_elements = tree.xpath("//h1")
                h1_text = h1_elements[0].text_content().strip() if h1_elements else ""

                m = re.match(r'^(Cap[ií]tulo\s+(\d+)[:\s]*(.*))', h1_text, re.IGNORECASE)
                if m:
                    num = int(m.group(2))
                    sub = m.group(3).strip().strip(': ')
                    # Clean up common OCR glitches in chapter names
                    sub = re.sub(r'Funces', 'Funções', sub)
                    sub = re.sub(r'Objetos c Estruturas', 'Objetos e Estruturas', sub)
                    sub = re.sub(r'Formatacao', 'Formatação', sub)
                    sub = re.sub(r'Emergencia', 'Emergência', sub)
                    sub = re.sub(r'Concorrencia', 'Concorrência', sub)
                    chap_name = f"Capítulo {num}: {sub}" if sub else f"Capítulo {num}"

                    if not major_sections or major_sections[-1]["type"] != "chapter" or major_sections[-1]["num"] != num:
                        major_sections.append({"type": "chapter", "num": num, "title": chap_name, "files": [f]})
                    else:
                        major_sections[-1]["files"].append(f)
                elif any(k in h1_text.lower() for k in ["prefacio", "prefácio"]):
                    major_sections.append({"type": "front", "num": 0, "title": "Prefácio", "files": [f]})
                elif any(k in h1_text.lower() for k in ["introducao", "introdução"]):
                    major_sections.append({"type": "front", "num": 0, "title": "Introdução", "files": [f]})
                elif any(k in h1_text.lower() for k in ["apendice", "apêndice"]):
                    m_ap = re.match(r'^(Ap[eê]ndice\s+([A-Z]))', h1_text, re.IGNORECASE)
                    ap_name = m_ap.group(1) if m_ap else h1_text
                    major_sections.append({"type": "appendix", "num": 0, "title": ap_name, "files": [f]})
                elif any(k in h1_text.lower() for k in ["epilogo", "epílogo"]):
                    major_sections.append({"type": "back", "num": 0, "title": "Epílogo", "files": [f]})
                else:
                    if major_sections:
                        major_sections[-1]["files"].append(f)
                    else:
                        major_sections.append({"type": "front", "num": 0, "title": h1_text or "Início", "files": [f]})

            # 3. Read and combine body nodes from sub-files BEFORE deleting old files
            major_sections_data = []
            for sec in major_sections:
                combined_nodes = []
                for sub_f in sec["files"]:
                    sub_path = os.path.join(oebps_dir, sub_f)
                    if not os.path.exists(sub_path):
                        continue
                    with open(sub_path, "r", encoding="utf-8", errors="ignore") as fp:
                        raw = fp.read()
                    stree = h.fromstring(raw.encode("utf-8"))
                    
                    for child in stree.body.iterchildren():
                        txt = child.text_content().strip()
                        # Filter out repetitive running headers inside the body
                        if child.tag in ("h1", "p"):
                            # Chapter repetition
                            if re.match(r'^Cap[ií]tulo\s+\d+', txt, re.IGNORECASE):
                                continue
                            # Running author name or short artifact
                            if txt.lower() in ("kohnke", "robert c. martin", "uncle bob", "clean code", "codigo limpo"):
                                continue
                            # Isolated page number: purely digits <= 4 chars
                            if txt.isdigit() and len(txt) <= 4:
                                continue
                        combined_nodes.append(child)
                major_sections_data.append((sec["title"], combined_nodes))

            # Delete old chap_*.xhtml files
            for f in chap_files:
                try:
                    os.remove(os.path.join(oebps_dir, f))
                except Exception:
                    pass

            # 4. Write unified HTML content for each major section
            new_chap_files = []
            code_blocks_merged = 0

            for idx, (sec_title, combined_nodes) in enumerate(major_sections_data, start=1):
                new_filename = f"chap_{idx:02d}.xhtml"
                new_chap_files.append((new_filename, sec_title))

                # Process code blocks merging
                cleaned_body_elements = []
                in_code = False
                code_lines = []

                for el in combined_nodes:
                    txt = el.text_content().strip()
                    if el.tag == "pre":
                        in_code = True
                        code_lines.append(txt)
                    elif el.tag == "p" and in_code and self.is_code_line(txt):
                        code_lines.append(txt)
                    elif el.tag == "p" and not in_code and (CODE_KEYWORDS.match(txt) or (txt.endswith(";") and ("=" in txt or "(" in txt))):
                        in_code = True
                        code_lines.append(txt)
                    else:
                        if in_code:
                            code_str = "\n".join(code_lines)
                            code_str = self.repair_code_syntax(code_str)
                            escaped = pyhtml.escape(code_str)
                            cleaned_body_elements.append(f'<pre><code>{escaped}</code></pre>')
                            code_blocks_merged += 1
                            code_lines = []
                            in_code = False
                        
                        # Add non-code element
                        if el.tag in ("h1", "h2", "h3", "p", "ul", "ol", "figure"):
                            txt_fixed = self.fix_portuguese_ocr_typos(txt)
                            cleaned_text = pyhtml.escape(txt_fixed)
                            if el.tag == "p":
                                p_txt = re.sub(r'(\b\w+)-\s+(\w+\b)', r'\1\2', txt_fixed)
                                cleaned_body_elements.append(f'<p>{pyhtml.escape(p_txt)}</p>')
                            elif el.tag == "h2":
                                cleaned_body_elements.append(f'<h2>{cleaned_text}</h2>')
                            elif el.tag == "h3":
                                cleaned_body_elements.append(f'<h3>{cleaned_text}</h3>')
                            elif el.tag in ("ul", "ol"):
                                cleaned_body_elements.append(h.tostring(el, encoding="unicode"))
                            elif el.tag == "figure":
                                cleaned_body_elements.append(h.tostring(el, encoding="unicode"))

                if in_code:
                    code_str = "\n".join(code_lines)
                    code_str = self.repair_code_syntax(code_str)
                    escaped = pyhtml.escape(code_str)
                    cleaned_body_elements.append(f'<pre><code>{escaped}</code></pre>')
                    code_blocks_merged += 1

                # Assemble HTML for this major chapter
                chap_html = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="pt">
<head>
    <title>{pyhtml.escape(sec_title)}</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
    <h1>{pyhtml.escape(sec_title)}</h1>
    {''.join(cleaned_body_elements)}
</body>
</html>"""
                with open(os.path.join(oebps_dir, new_filename), "w", encoding="utf-8") as fp:
                    fp.write(chap_html)

            # 5. Rebuild nav.xhtml
            nav_items_html = "\n".join([
                f'            <li><a href="{fname}">{pyhtml.escape(title)}</a></li>'
                for fname, title in new_chap_files
            ])
            nav_html = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>Sumário</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
    <nav epub:type="toc" id="toc">
        <h1>Sumário</h1>
        <ol>
{nav_items_html}
        </ol>
    </nav>
</body>
</html>"""
            with open(os.path.join(oebps_dir, "nav.xhtml"), "w", encoding="utf-8") as fp:
                fp.write(nav_html)

            # 6. Rebuild toc.ncx (EPUB 2 compatibility)
            navpoints = []
            for order, (fname, title) in enumerate(new_chap_files, start=1):
                navpoints.append(f"""    <navPoint id="navPoint-{order}" playOrder="{order}">
        <navLabel><text>{pyhtml.escape(title)}</text></navLabel>
        <content src="{fname}"/>
    </navPoint>""")
            ncx_html = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
    <head>
        <meta name="dtb:uid" content="{original_uid}"/>
        <meta name="dtb:depth" content="1"/>
        <meta name="dtb:totalPageCount" content="0"/>
        <meta name="dtb:maxPageNumber" content="0"/>
    </head>
    <docTitle><text>{original_title}</text></docTitle>
    <navMap>
{''.join(navpoints)}
    </navMap>
</ncx>"""
            with open(os.path.join(oebps_dir, "toc.ncx"), "w", encoding="utf-8") as fp:
                fp.write(ncx_html)

            # 7. Rebuild content.opf (manifest and spine)
            manifest_items = [
                '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
                '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                '    <item id="css" href="styles.css" media-type="text/css"/>'
            ]
            spine_items = []

            # Check cover
            if os.path.exists(os.path.join(oebps_dir, "cover.xhtml")):
                manifest_items.append('    <item id="cover_page" href="cover.xhtml" media-type="application/xhtml+xml"/>')
                spine_items.append('    <itemref idref="cover_page"/>')

            images_dir = os.path.join(oebps_dir, "images")
            if os.path.exists(images_dir):
                for img in os.listdir(images_dir):
                    ext = os.path.splitext(img)[1].lower()
                    mtype = "image/png" if ext == ".png" else "image/jpeg"
                    props = ' properties="cover-image"' if "cover" in img.lower() else ''
                    safe_id = re.sub(r'[^a-zA-Z0-9_]', '_', img)
                    manifest_items.append(f'    <item id="img_{safe_id}" href="images/{img}" media-type="{mtype}"{props}/>')

            for idx, (fname, _) in enumerate(new_chap_files, start=1):
                cid = f"chap_{idx:02d}"
                manifest_items.append(f'    <item id="{cid}" href="{fname}" media-type="application/xhtml+xml"/>')
                spine_items.append(f'    <itemref idref="{cid}"/>')

            opf_content = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">{original_uid}</dc:identifier>
    <dc:title>{original_title}</dc:title>
    <dc:creator>{original_author}</dc:creator>
    <dc:language>{original_lang}</dc:language>
  </metadata>
  <manifest>
{chr(10).join(manifest_items)}
  </manifest>
  <spine toc="ncx">
{chr(10).join(spine_items)}
  </spine>
</package>"""
            with open(os.path.join(oebps_dir, "content.opf"), "w", encoding="utf-8") as fp:
                fp.write(opf_content)

            # 8. Pack into final EPUB zip
            if os.path.exists(out_path):
                try:
                    os.remove(out_path)
                except Exception:
                    pass

            with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                # Mimetype first, uncompressed
                mimetype_path = os.path.join(temp_dir, "mimetype")
                if os.path.exists(mimetype_path):
                    zout.write(mimetype_path, "mimetype", compress_type=zipfile.ZIP_STORED)
                else:
                    zout.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        full_p = os.path.join(root, file)
                        rel_p = os.path.relpath(full_p, temp_dir)
                        if rel_p == "mimetype":
                            continue
                        zout.write(full_p, rel_p)

            stats = {
                "original_chapters": len(chap_files),
                "refined_chapters": len(new_chap_files),
                "code_blocks_merged": code_blocks_merged,
                "output_epub": out_path,
                "size_mb": round(os.path.getsize(out_path) / (1024 * 1024), 2)
            }
            return out_path, stats

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
