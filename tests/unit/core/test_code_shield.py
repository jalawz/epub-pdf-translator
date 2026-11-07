"""Testes unitários para o CodeShield (blindagem de código e tags)."""

import pytest

from src.core.code_shield import CodeShield


class TestMaskCodeBlocks:
    def test_pre_block_is_masked(self):
        html = "<pre>public void save() {}</pre>"
        masked, placeholders = CodeShield.mask_code_blocks(html)

        assert "[[_CODE_BLOCK_0_]]" in masked
        assert "public void save" not in masked
        assert len(placeholders) == 1
        assert placeholders["[[_CODE_BLOCK_0_]]"] == html

    def test_multiple_pre_blocks(self):
        html = "<pre>code A</pre><p>texto</p><pre>code B</pre>"
        masked, placeholders = CodeShield.mask_code_blocks(html)

        assert "[[_CODE_BLOCK_0_]]" in masked
        assert "[[_CODE_BLOCK_1_]]" in masked
        assert "code A" not in masked
        assert "code B" not in masked
        assert len(placeholders) == 2

    def test_nested_pre_is_masked_as_whole(self):
        html = "<pre><code>public class Foo {}</code></pre>"
        masked, placeholders = CodeShield.mask_code_blocks(html)

        assert "[[_CODE_BLOCK_0_]]" in masked
        assert "public class Foo" not in masked

    def test_no_newlines_added_around_token(self):
        """mask_code_blocks não deve adicionar \n ao redor do token."""
        html = "texto<pre>code</pre>mais texto"
        masked, _ = CodeShield.mask_code_blocks(html)

        assert masked == "texto[[_CODE_BLOCK_0_]]mais texto"


class TestUnmaskCodeBlocks:
    def test_original_block_is_restored(self):
        html = "<pre>public void save() {}</pre>"
        masked, placeholders = CodeShield.mask_code_blocks(html)

        # Simula um tradutor que não altera os tokens
        restored = CodeShield.unmask_code_blocks(masked, placeholders)

        assert restored == html

    def test_restored_block_ignores_translator_spacing(self):
        """Tradutores podem inserir espaços ao redor do token; o bloco deve ser restaurado."""
        html = "<pre>public void save() {}</pre>"
        masked, placeholders = CodeShield.mask_code_blocks(html)

        # Simula tradutor que insere espaços ao redor do token
        translated_with_spaces = masked.replace("[[_CODE_BLOCK_0_]]", " [[ _CODE_BLOCK_0_ ]] ")
        restored = CodeShield.unmask_code_blocks(translated_with_spaces, placeholders)

        # O bloco original deve estar presente e nenhum token deve restar
        assert "<pre>public void save() {}</pre>" in restored
        assert "[[_CODE_BLOCK" not in restored
        assert "_CODE_BLOCK_" not in restored

    def test_multiple_blocks_restored_with_spacing(self):
        html = "<pre>code A</pre>texto<pre>code B</pre>"
        masked, placeholders = CodeShield.mask_code_blocks(html)
        spaced = masked.replace("[[_CODE_BLOCK_0_]]", " [ [ _CODE_BLOCK_0_ ] ] ")
        spaced = spaced.replace("[[_CODE_BLOCK_1_]]", " [ [ _CODE_BLOCK_1_ ] ] ")
        restored = CodeShield.unmask_code_blocks(spaced, placeholders)

        assert "code A" in restored
        assert "code B" in restored
        assert "[[_CODE_BLOCK" not in restored


class TestMaskHtmlTags:
    def test_inline_tags_are_masked(self):
        html = "<p>Hello <code>world</code>!</p>"
        masked, placeholders = CodeShield.mask_html_tags(html)

        assert "<code>" not in masked
        assert "</code>" not in masked
        assert "[[_TAG_0_]]" in masked
        assert "[[_TAG_1_]]" in masked

    def test_self_closing_tags_are_masked(self):
        html = "<img src='a.png'/>"
        masked, placeholders = CodeShield.mask_html_tags(html)

        assert "<img" not in masked
        assert len(placeholders) == 1


class TestUnmaskHtmlTags:
    def test_tags_are_restored(self):
        html = "<p>Hello <code>world</code>!</p>"
        masked, placeholders = CodeShield.mask_html_tags(html)

        restored = CodeShield.unmask_html_tags(masked, placeholders)

        assert restored == html

    def test_tolerates_translator_spacing(self):
        """Tradutores podem inserir espaços dentro/ao redor do token; as tags devem ser restauradas."""
        html = "<p>Hello <code>world</code>!</p>"
        masked, placeholders = CodeShield.mask_html_tags(html)

        # Simula tradutor que insere espaços dentro do token
        spaced = masked.replace("[[_TAG_0_]]", " [ [ _TAG_0_ ] ] ")
        spaced = spaced.replace("[[_TAG_1_]]", " [ [ _TAG_1_ ] ] ")
        restored = CodeShield.unmask_html_tags(spaced, placeholders)

        # As tags originais devem estar presentes e nenhum token deve restar
        assert "<code>" in restored
        assert "</code>" in restored
        assert "[[_TAG" not in restored
        assert "_TAG_" not in restored

    def test_text_content_preserved(self):
        html = "<p>Hello <code>world</code>!</p>"
        masked, placeholders = CodeShield.mask_html_tags(html)
        spaced = masked.replace("[[_TAG_0_]]", " [ [ _TAG_0_ ] ] ")
        spaced = spaced.replace("[[_TAG_1_]]", " [ [ _TAG_1_ ] ] ")
        restored = CodeShield.unmask_html_tags(spaced, placeholders)

        assert "Hello" in restored
        assert "world" in restored
        assert "!" in restored
