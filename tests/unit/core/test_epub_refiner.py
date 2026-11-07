"""Testes unitários para o EpubRefiner (refinamento pós-OCR).

Inclui teste que verifica que o refiner NÃO hardcodeia título/autor fixos
("Código Limpo" / "Robert C. Martin") — bug conhecido a ser corrigido.
"""

import zipfile
from pathlib import Path

import pytest

from src.core.epub_refiner import EpubRefiner


def _make_epub_for_refiner(path: Path, title: str, author: str, lang: str = "pt"):
    """Cria um EPUB mínimo com capítulos chap_ para o refiner processar."""
    chap1 = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="pt">
<head><title>Capítulo 1: Início</title><link rel="stylesheet" type="text/css" href="styles.css"/></head>
<body>
    <h1>Capítulo 1: Início</h1>
    <p>Este é o primeiro capítulo do livro.</p>
</body>
</html>"""

    chap2 = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="pt">
<head><title>Capítulo 2: Meio</title><link rel="stylesheet" type="text/css" href="styles.css"/></head>
<body>
    <h1>Capítulo 2: Meio</h1>
    <p>Este é o segundo capítulo.</p>
</body>
</html>"""

    content_opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
    <dc:creator>{author}</dc:creator>
    <dc:language>{lang}</dc:language>
    <dc:identifier id="BookId">urn:uuid:11111111-1111-1111-1111-111111111111</dc:identifier>
  </metadata>
  <manifest>
    <item id="css" href="styles.css" media-type="text/css"/>
    <item id="chap1" href="chap_01.xhtml" media-type="application/xhtml+xml"/>
    <item id="chap2" href="chap_02.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="chap1"/>
    <itemref idref="chap2"/>
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
            <li><a href="chap_01.xhtml">Capítulo 1: Início</a></li>
            <li><a href="chap_02.xhtml">Capítulo 2: Meio</a></li>
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
    <navPoint id="navPoint-2" playOrder="2"><navLabel><text>Capítulo 2</text></navLabel><content src="chap_02.xhtml"/></navPoint>
  </navMap>
</ncx>"""

    css = "body { font-family: serif; }"

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>', compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", content_opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/styles.css", css, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/chap_01.xhtml", chap1, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/chap_02.xhtml", chap2, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx", ncx, compress_type=zipfile.ZIP_DEFLATED)


def _read_opf_title_author(epub_path: Path):
    with zipfile.ZipFile(epub_path, "r") as z:
        opf = z.read("OEBPS/content.opf").decode("utf-8")
    # Extrair título e autor do OPF de forma simples
    import re

    title_match = re.search(r"<dc:title>(.*?)</dc:title>", opf)
    creator_match = re.search(r"<dc:creator>(.*?)</dc:creator>", opf)
    return (
        title_match.group(1) if title_match else None,
        creator_match.group(1) if creator_match else None,
    )


class TestEpubRefinerPreservesMetadata:
    def test_refiner_preserves_original_title_and_author(self, tmp_path):
        """O refiner NÃO deve hardcodear 'Código Limpo' / 'Robert C. Martin'.

        Este teste documenta o bug atual: o EpubRefiner.refine() reescreve
        content.opf com valores fixos independentemente do livro de entrada.
        """
        src = tmp_path / "livro_original.epub"
        _make_epub_for_refiner(src, "Meu Livro Real", "Autor Real")

        out = tmp_path / "livro_refinado.epub"

        refiner = EpubRefiner(str(src))
        refiner.refine(str(out))

        title, author = _read_opf_title_author(out)

        # O título e autor originais devem ser preservados
        assert title == "Meu Livro Real", f"Esperado 'Meu Livro Real', obtido '{title}'"
        assert author == "Autor Real", f"Esperado 'Autor Real', obtido '{author}'"

    def test_refiner_does_not_hardcode_codigo_limpo(self, tmp_path):
        """O EPUB de saída não deve conter 'Código Limpo' nem 'Robert C. Martin'."""
        src = tmp_path / "outro_livro.epub"
        _make_epub_for_refiner(src, "Qualquer Outro Título", "Qualquer Outro Autor")

        out = tmp_path / "outro_refinado.epub"

        refiner = EpubRefiner(str(src))
        refiner.refine(str(out))

        title, author = _read_opf_title_author(out)

        assert title != "Código Limpo"
        assert author != "Robert C. Martin"

    def test_refiner_returns_stats(self, tmp_path):
        src = tmp_path / "stats_livro.epub"
        _make_epub_for_refiner(src, "Stats", "Stats Author")

        out = tmp_path / "stats_out.epub"

        refiner = EpubRefiner(str(src))
        out_path, stats = refiner.refine(str(out))

        assert out_path == str(out)
        assert "refined_chapters" in stats
        assert "original_chapters" in stats
        assert stats["refined_chapters"] >= 1
