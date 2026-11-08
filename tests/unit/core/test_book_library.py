"""Testes unitários para o BookLibrary (biblioteca digital local)."""

import json
import os
from pathlib import Path

import fitz  # PyMuPDF
import pytest

from src.core.library import BookLibrary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_pdf(path: Path, title: str, pages: int = 2):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{title} - página {i + 1}", fontsize=12)
    doc.save(str(path))
    doc.close()


def _make_epub(path: Path):
    """Cria um EPUB mínimo válido."""
    import zipfile

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>'
            "</container>",
            compress_type=zipfile.ZIP_DEFLATED,
        )
        z.writestr(
            "OEBPS/content.opf",
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            "<metadata/><manifest/><spine/></package>",
            compress_type=zipfile.ZIP_DEFLATED,
        )


class TestBookLibraryInit:
    def test_creates_library_dir(self, tmp_path):
        lib = BookLibrary(root_dir=str(tmp_path))
        assert os.path.isdir(lib.library_dir)
        assert lib.library_dir == str(tmp_path / "library")


class TestAddBook:
    def test_add_book_creates_metadata_and_copies_files(self, tmp_path):
        lib = BookLibrary(root_dir=str(tmp_path))
        pdf_path = tmp_path / "livro.pdf"
        epub_path = tmp_path / "livro.epub"
        _make_pdf(pdf_path, "Meu Livro")
        _make_epub(epub_path)

        record = lib.add_book(
            pdf_path=str(pdf_path),
            epub_path=str(epub_path),
            metadata={"title": "Meu Livro", "author": "Autor Teste"},
            lang="pt",
            source_lang="en",
        )

        assert record["title"] == "Meu Livro"
        assert record["author"] == "Autor Teste"
        assert record["slug"] == "Meu_Livro"
        assert record["lang"] == "pt"
        assert record["source_lang"] == "en"
        assert record["category"] == "translation"

        # Verifica que arquivos foram copiados para a biblioteca
        book_dir = Path(lib.library_dir) / "pt" / "Meu_Livro"
        assert (book_dir / "Meu_Livro_PT.pdf").exists()
        assert (book_dir / "Meu_Livro_PT.epub").exists()
        assert (book_dir / "metadata.json").exists()

    def test_add_book_generates_cover_from_pdf(self, tmp_path):
        lib = BookLibrary(root_dir=str(tmp_path))
        pdf_path = tmp_path / "livro.pdf"
        epub_path = tmp_path / "livro.epub"
        _make_pdf(pdf_path, "Livro com Capa")
        _make_epub(epub_path)

        lib.add_book(
            pdf_path=str(pdf_path),
            epub_path=str(epub_path),
            metadata={"title": "Livro com Capa"},
            lang="pt",
            source_lang="en",
        )

        book_dir = Path(lib.library_dir) / "pt" / "Livro_com_Capa"
        assert (book_dir / "cover.png").exists()

    def test_add_book_uses_provided_cover(self, tmp_path):
        lib = BookLibrary(root_dir=str(tmp_path))
        pdf_path = tmp_path / "livro.pdf"
        epub_path = tmp_path / "livro.epub"
        cover_path = tmp_path / "capa.jpg"
        cover_path.write_bytes(b"fake jpg")
        _make_pdf(pdf_path, "Livro com Capa Própria")
        _make_epub(epub_path)

        lib.add_book(
            pdf_path=str(pdf_path),
            epub_path=str(epub_path),
            cover_image_path=str(cover_path),
            metadata={"title": "Livro com Capa Própria"},
            lang="pt",
            source_lang="en",
        )

        book_dir = Path(lib.library_dir) / "pt" / "Livro_com_Capa_Propria"
        assert (book_dir / "cover.jpg").exists()

    def test_add_book_category_ocr_when_same_lang(self, tmp_path):
        lib = BookLibrary(root_dir=str(tmp_path))
        pdf_path = tmp_path / "livro.pdf"
        epub_path = tmp_path / "livro.epub"
        _make_pdf(pdf_path, "Livro OCR")
        _make_epub(epub_path)

        record = lib.add_book(
            pdf_path=str(pdf_path),
            epub_path=str(epub_path),
            metadata={"title": "Livro OCR"},
            lang="pt",
            source_lang="pt",  # mesmo idioma -> OCR
        )

        assert record["category"] == "ocr"

    def test_slugify_removes_special_chars(self):
        lib = BookLibrary()
        assert lib.slugify("Meu Livro (Edição Especial)!") == "Meu_Livro_Edicao_Especial"
        assert lib.slugify("___") == "unnamed_book"
        assert lib.slugify("") == "unnamed_book"


class TestListBooks:
    def test_list_books_empty_when_no_library(self, tmp_path):
        lib = BookLibrary(root_dir=str(tmp_path))
        assert lib.list_books() == []

    def test_list_books_returns_all(self, tmp_path):
        lib = BookLibrary(root_dir=str(tmp_path))
        for i in range(3):
            pdf = tmp_path / f"livro_{i}.pdf"
            epub = tmp_path / f"livro_{i}.epub"
            _make_pdf(pdf, f"Livro {i}")
            _make_epub(epub)
            lib.add_book(
                pdf_path=str(pdf),
                epub_path=str(epub),
                metadata={"title": f"Livro {i}"},
                lang="pt",
                source_lang="en",
            )

        books = lib.list_books()
        assert len(books) == 3

    def test_list_books_filter_by_lang(self, tmp_path):
        lib = BookLibrary(root_dir=str(tmp_path))

        # Livro em PT
        pdf_pt = tmp_path / "a.pdf"
        epub_pt = tmp_path / "a.epub"
        _make_pdf(pdf_pt, "Livro A")
        _make_epub(epub_pt)
        lib.add_book(
            pdf_path=str(pdf_pt), epub_path=str(epub_pt),
            metadata={"title": "Livro A"}, lang="pt", source_lang="en",
        )

        # Livro em EN
        pdf_en = tmp_path / "b.pdf"
        epub_en = tmp_path / "b.epub"
        _make_pdf(pdf_en, "Livro B")
        _make_epub(epub_en)
        lib.add_book(
            pdf_path=str(pdf_en), epub_path=str(epub_en),
            metadata={"title": "Livro B"}, lang="en", source_lang="pt",
        )

        books_pt = lib.list_books(lang="pt")
        assert len(books_pt) == 1
        assert books_pt[0]["title"] == "Livro A"

        books_en = lib.list_books(lang="en")
        assert len(books_en) == 1
        assert books_en[0]["title"] == "Livro B"

    def test_list_books_filter_by_category(self, tmp_path):
        lib = BookLibrary(root_dir=str(tmp_path))

        # Tradução (idiomas diferentes)
        pdf1 = tmp_path / "t.pdf"
        epub1 = tmp_path / "t.epub"
        _make_pdf(pdf1, "Traduzido")
        _make_epub(epub1)
        lib.add_book(
            pdf_path=str(pdf1), epub_path=str(epub1),
            metadata={"title": "Traduzido"}, lang="pt", source_lang="en",
        )

        # OCR (mesmo idioma)
        pdf2 = tmp_path / "o.pdf"
        epub2 = tmp_path / "o.epub"
        _make_pdf(pdf2, "Digitalizado")
        _make_epub(epub2)
        lib.add_book(
            pdf_path=str(pdf2), epub_path=str(epub2),
            metadata={"title": "Digitalizado"}, lang="pt", source_lang="pt",
        )

        trans = lib.list_books(category="translation")
        assert len(trans) == 1
        assert trans[0]["title"] == "Traduzido"

        ocr = lib.list_books(category="ocr")
        assert len(ocr) == 1
        assert ocr[0]["title"] == "Digitalizado"

    def test_list_books_sorted_by_date_desc(self, tmp_path):
        lib = BookLibrary(root_dir=str(tmp_path))
        for i in range(3):
            pdf = tmp_path / f"livro_{i}.pdf"
            epub = tmp_path / f"livro_{i}.epub"
            _make_pdf(pdf, f"Livro {i}")
            _make_epub(epub)
            lib.add_book(
                pdf_path=str(pdf), epub_path=str(epub),
                metadata={"title": f"Livro {i}"}, lang="pt", source_lang="en",
            )

        books = lib.list_books()
        titles = [b["title"] for b in books]
        # O último adicionado deve ser o primeiro na lista (ordem desc)
        assert titles == ["Livro 2", "Livro 1", "Livro 0"]


class TestGetBook:
    def test_get_book_returns_record(self, tmp_path):
        lib = BookLibrary(root_dir=str(tmp_path))
        pdf = tmp_path / "x.pdf"
        epub = tmp_path / "x.epub"
        _make_pdf(pdf, "Livro X")
        _make_epub(epub)
        lib.add_book(
            pdf_path=str(pdf), epub_path=str(epub),
            metadata={"title": "Livro X"}, lang="pt", source_lang="en",
        )

        book = lib.get_book(lang="pt", slug="Livro_X")
        assert book is not None
        assert book["title"] == "Livro X"
        assert book["slug"] == "Livro_X"

    def test_get_book_returns_none_when_missing(self, tmp_path):
        lib = BookLibrary(root_dir=str(tmp_path))
        assert lib.get_book(lang="pt", slug="Nao_Existe") is None


class TestDeleteBook:
    def test_delete_book_removes_folder(self, tmp_path):
        lib = BookLibrary(root_dir=str(tmp_path))
        pdf = tmp_path / "d.pdf"
        epub = tmp_path / "d.epub"
        _make_pdf(pdf, "Para Deletar")
        _make_epub(epub)
        lib.add_book(
            pdf_path=str(pdf), epub_path=str(epub),
            metadata={"title": "Para Deletar"}, lang="pt", source_lang="en",
        )

        book_dir = Path(lib.library_dir) / "pt" / "Para_Deletar"
        assert book_dir.exists()

        result = lib.delete_book(lang="pt", slug="Para_Deletar")
        assert result is True
        assert not book_dir.exists()

    def test_delete_book_returns_false_when_missing(self, tmp_path):
        lib = BookLibrary(root_dir=str(tmp_path))
        result = lib.delete_book(lang="pt", slug="Nao_Existe")
        assert result is False


class TestScanAndMigrateLegacy:
    def test_scan_and_migrate_legacy_finds_pdf_epub_pairs(self, tmp_path):
        lib = BookLibrary(root_dir=str(tmp_path))

        # Cria um par PDF+EPUB na raiz de output
        pdf = tmp_path / "Meu Livro_for_pt.pdf"
        epub = tmp_path / "Meu Livro_for_pt.epub"
        _make_pdf(pdf, "Meu Livro")
        _make_epub(epub)

        migrated = lib.scan_and_migrate_legacy()
        assert len(migrated) == 1
        assert migrated[0]["title"] == "Meu Livro"
        assert migrated[0]["lang"] == "pt"

    def test_scan_and_migrate_legacy_idempotent(self, tmp_path):
        lib = BookLibrary(root_dir=str(tmp_path))
        pdf = tmp_path / "Livro_for_pt.pdf"
        epub = tmp_path / "Livro_for_pt.epub"
        _make_pdf(pdf, "Livro")
        _make_epub(epub)

        lib.scan_and_migrate_legacy()
        migrated_again = lib.scan_and_migrate_legacy()
        assert len(migrated_again) == 0  # já migrado, não duplica

    def test_scan_and_migrate_legacy_extracts_author_from_epub(self, tmp_path):
        """CORREÇÃO Sprint 10: autor migrado vem do dc:creator do EPUB, não de hardcode."""
        import zipfile

        lib = BookLibrary(root_dir=str(tmp_path))
        pdf = tmp_path / "Microservices_for_pt.pdf"
        epub = tmp_path / "Microservices_for_pt.epub"
        _make_pdf(pdf, "Microservices")
        with zipfile.ZipFile(epub, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            z.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>'
                "</container>",
                compress_type=zipfile.ZIP_DEFLATED,
            )
            z.writestr(
                "OEBPS/content.opf",
                '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
                '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                "<dc:title>Microservices</dc:title><dc:creator>Autora Real</dc:creator></metadata>"
                "<manifest/><spine/></package>",
                compress_type=zipfile.ZIP_DEFLATED,
            )

        migrated = lib.scan_and_migrate_legacy()
        assert len(migrated) == 1
        assert migrated[0]["author"] == "Autora Real"
        assert migrated[0]["author"] != "Magnus Larsson"
