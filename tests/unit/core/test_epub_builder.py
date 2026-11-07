"""Testes unitários para o EpubBuilder (construtor de EPUB 3.0)."""

import zipfile
from pathlib import Path

import pytest

from src.core.epub_builder import EpubBuilder


class TestEpubBuilderInit:
    def test_default_values(self):
        builder = EpubBuilder(title="Meu Livro")
        assert builder.title == "Meu Livro"
        assert builder.author == "Desconhecido"
        assert builder.lang == "pt"
        assert builder.book_id.startswith("urn:uuid:")
        assert builder.chapters == []
        assert builder.images == {}
        assert builder.cover_path is None

    def test_custom_values(self):
        builder = EpubBuilder(
            title="Título Custom",
            author="Autor Custom",
            lang="en",
            book_id="urn:uuid:fixed-id",
        )
        assert builder.title == "Título Custom"
        assert builder.author == "Autor Custom"
        assert builder.lang == "en"
        assert builder.book_id == "urn:uuid:fixed-id"

    def test_empty_title_defaults(self):
        builder = EpubBuilder(title="")
        assert builder.title == "Livro Digitalizado"

    def test_empty_author_defaults(self):
        builder = EpubBuilder(title="Livro", author="")
        assert builder.author == "Autor Desconhecido"


class TestAddChapter:
    def test_add_chapter_auto_ids(self):
        builder = EpubBuilder(title="Livro", author="Autor", lang="pt")
        cid1 = builder.add_chapter("Capítulo 1", [])
        cid2 = builder.add_chapter("Capítulo 2", [])
        cid3 = builder.add_chapter("", [])

        assert cid1 == "chapter_01"
        assert cid2 == "chapter_02"
        assert cid3 == "chapter_03"
        assert len(builder.chapters) == 3
        assert builder.chapters[0]["title"] == "Capítulo 1"
        assert builder.chapters[2]["title"] == "Capítulo 3"
        assert builder.chapters[0]["filename"] == "chapter_01.xhtml"

    def test_add_chapter_custom_id(self):
        builder = EpubBuilder(title="Livro")
        cid = builder.add_chapter("Meu Capítulo", [], chapter_id="cap_custom")
        assert cid == "cap_custom"
        assert builder.chapters[0]["filename"] == "cap_custom.xhtml"


class TestAddImage:
    def test_add_image_returns_relative_path(self, tmp_path):
        builder = EpubBuilder(title="Livro")
        img_path = tmp_path / "figura.png"
        img_path.write_bytes(b"\x89PNG fake")

        rel = builder.add_image(str(img_path))
        assert rel == "images/figura.png"
        # O img_id sanitiza caracteres não alfanuméricos (incluindo o ponto)
        assert "figura_png" in builder.images
        assert builder.images["figura_png"] == str(img_path)

    def test_add_image_nonexistent_returns_empty(self):
        builder = EpubBuilder(title="Livro")
        rel = builder.add_image("/caminho/nao/existe.png")
        assert rel == ""


class TestRenderBlocksToHtml:
    def test_paragraph_block(self):
        builder = EpubBuilder(title="Livro")
        blocks = [{"type": "paragraph", "text": "Este é um parágrafo."}]
        html = builder._render_blocks_to_html(blocks)
        assert "<p>Este é um parágrafo.</p>" in html

    def test_heading_block(self):
        builder = EpubBuilder(title="Livro")
        blocks = [{"type": "heading", "level": 1, "text": "Título do Capítulo"}]
        html = builder._render_blocks_to_html(blocks)
        assert "<h1>Título do Capítulo</h1>" in html

    def test_code_block(self):
        builder = EpubBuilder(title="Livro")
        blocks = [{"type": "code", "text": "public void save() {}"}]
        html = builder._render_blocks_to_html(blocks)
        assert "<pre><code>" in html
        assert "public void save() {}" in html
        assert "</code></pre>" in html

    def test_list_block_unordered(self):
        builder = EpubBuilder(title="Livro")
        blocks = [{"type": "list", "items": ["Item 1", "Item 2"], "ordered": False}]
        html = builder._render_blocks_to_html(blocks)
        assert "<ul>" in html
        assert "<li>Item 1</li>" in html
        assert "<li>Item 2</li>" in html

    def test_list_block_ordered(self):
        builder = EpubBuilder(title="Livro")
        blocks = [{"type": "list", "items": ["Primeiro", "Segundo"], "ordered": True}]
        html = builder._render_blocks_to_html(blocks)
        assert "<ol>" in html
        assert "<li>Primeiro</li>" in html

    def test_quote_block(self):
        builder = EpubBuilder(title="Livro")
        blocks = [{"type": "quote", "text": "Esta é uma citação."}]
        html = builder._render_blocks_to_html(blocks)
        assert "<blockquote>" in html
        assert "Esta é uma citação." in html

    def test_image_block(self):
        builder = EpubBuilder(title="Livro")
        blocks = [{"type": "image", "src": "images/figura.png", "caption": "Figura 1"}]
        html = builder._render_blocks_to_html(blocks)
        assert '<img src="images/figura.png"' in html
        assert "<figcaption>Figura 1</figcaption>" in html

    def test_escape_html_special_chars(self):
        builder = EpubBuilder(title="Livro")
        blocks = [{"type": "paragraph", "text": "Texto com <tag> & \"aspas\" 'simples'"}]
        html = builder._render_blocks_to_html(blocks)
        assert "&lt;tag&gt;" in html
        assert "&amp;" in html
        assert "&quot;" in html
        assert "&#39;" in html


class TestBuild:
    def test_build_creates_valid_epub_structure(self, tmp_path):
        builder = EpubBuilder(title="Livro de Teste", author="Autor Teste", lang="pt")
        builder.add_chapter("Capítulo 1", [{"type": "paragraph", "text": "Conteúdo do capítulo 1."}])
        builder.add_chapter("Capítulo 2", [{"type": "paragraph", "text": "Conteúdo do capítulo 2."}])

        out_path = tmp_path / "livro_teste.epub"
        result = builder.build(str(out_path))

        assert result == str(out_path)
        assert out_path.exists()
        assert out_path.stat().st_size > 0

        with zipfile.ZipFile(out_path, "r") as z:
            names = z.namelist()
            # mimetype deve ser o primeiro e não comprimido
            assert names[0] == "mimetype"
            mimetype_info = z.getinfo("mimetype")
            assert mimetype_info.compress_type == zipfile.ZIP_STORED
            assert z.read("mimetype").decode() == "application/epub+zip"

            # Deve ter container.xml
            assert "META-INF/container.xml" in names
            # Deve ter styles.css
            assert "OEBPS/styles.css" in names
            # Deve ter content.opf
            assert "OEBPS/content.opf" in names
            # Deve ter nav.xhtml
            assert "OEBPS/nav.xhtml" in names
            # Deve ter toc.ncx
            assert "OEBPS/toc.ncx" in names
            # Capítulos
            assert "OEBPS/chapter_01.xhtml" in names
            assert "OEBPS/chapter_02.xhtml" in names

    def test_build_with_cover(self, tmp_path):
        builder = EpubBuilder(title="Livro com Capa", author="Autor", lang="pt")
        cover_path = tmp_path / "capa.png"
        cover_path.write_bytes(b"\x89PNG fake cover")
        builder.set_cover(str(cover_path))

        builder.add_chapter("Capítulo 1", [{"type": "paragraph", "text": "Conteúdo."}])

        out_path = tmp_path / "com_capa.epub"
        builder.build(str(out_path))

        with zipfile.ZipFile(out_path, "r") as z:
            names = z.namelist()
            # Deve ter imagem da capa
            cover_images = [n for n in names if n.startswith("OEBPS/images/cover")]
            assert len(cover_images) == 1
            # content.opf deve referenciar cover-image
            opf = z.read("OEBPS/content.opf").decode("utf-8")
            assert "cover-image" in opf

    def test_build_escapes_title_in_opf(self, tmp_path):
        builder = EpubBuilder(title="Livro com \"aspas\" e <tags>", author="Autor & Cia", lang="pt")
        builder.add_chapter("Capítulo 1", [{"type": "paragraph", "text": "Texto."}])

        out_path = tmp_path / "escape.epub"
        builder.build(str(out_path))

        with zipfile.ZipFile(out_path, "r") as z:
            opf = z.read("OEBPS/content.opf").decode("utf-8")
            assert "&quot;" in opf or "&lt;" in opf
            assert "&amp;" in opf
