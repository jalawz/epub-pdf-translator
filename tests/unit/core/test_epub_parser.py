"""Testes unitários para o EpubParser (parsão de container, manifesto e spine)."""

import os
import pytest

from src.core.epub_parser import EpubParser


class TestEpubParserInit:
    def test_raises_on_missing_file(self, tmp_path):
        missing = tmp_path / "nao_existe.epub"
        with pytest.raises(FileNotFoundError):
            EpubParser(str(missing))

    def test_parses_mini_epub_metadata(self, mini_epub_path):
        parser = EpubParser(str(mini_epub_path))

        assert parser.metadata["title"] == "Mini Book for Tests"
        assert parser.metadata["creator"] == "Test Author"

    def test_parses_spine(self, mini_epub_path):
        parser = EpubParser(str(mini_epub_path))

        assert len(parser.spine) == 1
        assert "chapter1.xhtml" in parser.spine[0]

    def test_parses_manifest(self, mini_epub_path):
        parser = EpubParser(str(mini_epub_path))

        assert "chap1" in parser.manifest
        assert parser.manifest["chap1"].endswith("chapter1.xhtml")

    def test_get_chapter_content(self, mini_epub_path):
        parser = EpubParser(str(mini_epub_path))

        content = parser.get_chapter_content(parser.spine[0])
        assert "Chapter 1" in content
        assert "public void save()" in content

    def test_extract_assets_writes_inside_target(self, mini_epub_path, tmp_output_dir):
        parser = EpubParser(str(mini_epub_path))

        # O EPUB mínimo não tem assets, mas o método não deve quebrar
        parser.extract_assets(str(tmp_output_dir / "assets"))
        assert os.path.isdir(tmp_output_dir / "assets")

    def test_close_releases_zip(self, mini_epub_path):
        parser = EpubParser(str(mini_epub_path))
        parser.close()
        # Não deve lançar ao fechar duas vezes
        parser.close()
