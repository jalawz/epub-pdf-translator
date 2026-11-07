"""Testes adicionais para o EpubRefiner (cobertura de métodos auxiliares)."""

import os
import zipfile
from pathlib import Path

import pytest

from src.core.epub_refiner import EpubRefiner


def _make_epub_with_code_blocks(path: Path, title: str, author: str):
    """Cria um EPUB com blocos de código para testar o refinamento."""
    chap1 = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="pt">
<head><title>Capítulo 1</title><link rel="stylesheet" type="text/css" href="styles.css"/></head>
<body>
    <h1>Capítulo 1</h1>
    <p>public void save() {}</p>
    <p>Este é um parágrafo normal.</p>
    <pre>code block here</pre>
</body>
</html>"""

    content_opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
    <dc:creator>{author}</dc:creator>
    <dc:language>pt</dc:language>
    <dc:identifier id="BookId">urn:uuid:11111111-1111-1111-1111-111111111111</dc:identifier>
  </metadata>
  <manifest>
    <item id="css" href="styles.css" media-type="text/css"/>
    <item id="chap1" href="chap_01.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="chap1"/>
  </spine>
</package>"""

    nav = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="pt">
<head><title>Sumário</title></head>
<body>
    <nav epub:type="toc" id="toc">
        <h1>Sumário</h1>
        <ol>
            <li><a href="chap_01.xhtml">Capítulo 1</a></li>
        </ol>
    </nav>
</body>
</html>"""

    ncx = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="uuid-123"/></head>
  <docTitle><text>Título Original</text></docTitle>
  <navMap>
    <navPoint id="navPoint-1" playOrder="1"><navLabel><text>Capítulo 1</text></navLabel><content src="chap_01.xhtml"/></navPoint>
  </navMap>
</ncx>"""

    css = "body { font-family: serif; }"

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>', compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", content_opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/styles.css", css, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/chap_01.xhtml", chap1, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx", ncx, compress_type=zipfile.ZIP_DEFLATED)


class TestEpubRefinerCodeBlocks:
    def test_refiner_merges_code_blocks(self, tmp_path):
        """Blocos de código devem ser mesclados no refiner."""
        src = tmp_path / "livro_codigo.epub"
        _make_epub_with_code_blocks(src, "Livro Código", "Autor Código")

        out = tmp_path / "livro_codigo_refinado.epub"

        refiner = EpubRefiner(str(src))
        out_path, stats = refiner.refine(str(out))

        assert stats["code_blocks_merged"] >= 1
        assert out_path == str(out)

    def test_refiner_handles_missing_chapter_files(self, tmp_path):
        """Refiner deve falhar com erro claro quando não há capítulos."""
        src = tmp_path / "sem_capitulos.epub"
        # EPUB sem arquivos chap_*.xhtml
        with zipfile.ZipFile(src, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            z.writestr("META-INF/container.xml", '<container/>', compress_type=zipfile.ZIP_DEFLATED)
            z.writestr("OEBPS/content.opf", '<package/>', compress_type=zipfile.ZIP_DEFLATED)

        refiner = EpubRefiner(str(src))
        out = tmp_path / "out.epub"

        with pytest.raises(ValueError, match="Nenhum arquivo de capítulo"):
            refiner.refine(str(out))
