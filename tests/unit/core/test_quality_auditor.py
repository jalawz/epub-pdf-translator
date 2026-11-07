"""Testes unitários para o QualityAuditor (auditoria de cobertura linguística)."""

import pytest

from src.core.quality_auditor import QualityAuditor


class TestAuditHtmlDetectsUntranslatedPortugueseTarget:
    def test_flags_english_stopwords_in_portuguese_target(self):
        html = """
        <html><body>
            <p>The quick brown fox jumps over the lazy dog.</p>
            <p>This is a test paragraph with many english words.</p>
            <p>Another paragraph that remains in english after translation.</p>
        </body></html>
        """
        flagged = QualityAuditor.audit_html(html)

        assert len(flagged) >= 1
        # Deve flagar elementos com stopwords em inglês
        total_eng = sum(f["eng_stopwords"] for f in flagged)
        assert total_eng >= 3

    def test_passes_when_all_translated_to_portuguese(self):
        html = """
        <html><body>
            <p>Este é um texto em português que foi traduzido corretamente.</p>
            <p>Outro parágrafo completamente em português do Brasil.</p>
            <p>Mais conteúdo traduzido para verificar a qualidade.</p>
        </body></html>
        """
        flagged = QualityAuditor.audit_html(html)

        # Não deve flagar (stopwords em português predominam)
        assert len(flagged) == 0

    def test_skips_short_text(self):
        html = """
        <html><body>
            <p>The</p>
            <p>Hi</p>
            <p>OK</p>
        </body></html>
        """
        flagged = QualityAuditor.audit_html(html)
        assert len(flagged) == 0

    def test_skips_code_blocks_in_pre(self):
        html = """
        <html><body>
            <pre>
            The quick brown fox jumps over the lazy dog.
            This code block should not be flagged.
            </pre>
            <p>Este parágrafo está em português.</p>
        </body></html>
        """
        flagged = QualityAuditor.audit_html(html)
        # O conteúdo dentro de <pre> deve ser ignorado
        assert len(flagged) == 0

    def test_flagged_element_structure(self):
        html = """
        <html><body>
            <p>The the the the the the the the the the.</p>
        </body></html>
        """
        flagged = QualityAuditor.audit_html(html)

        assert len(flagged) == 1
        f = flagged[0]
        assert "tag" in f
        assert "text_preview" in f
        assert "eng_stopwords" in f
        assert "pt_stopwords" in f
        assert f["tag"] == "p"
        assert f["eng_stopwords"] >= 3

    def test_audits_multiple_tags(self):
        html = """
        <html><body>
            <h1>The the the the the the the chapter title</h1>
            <p>The the the paragraph text in english and more.</p>
            <li>The the the list item in english and more.</li>
            <blockquote>The the the quote in english and more.</blockquote>
        </body></html>
        """
        flagged = QualityAuditor.audit_html(html)
        # Deve flagar múltiplas tags
        assert len(flagged) >= 2

    def test_quality_certified_flag_logic(self):
        html_clean = """
        <html><body>
            <p>Texto traduzido para português do Brasil corretamente.</p>
        </body></html>
        """
        flagged_clean = QualityAuditor.audit_html(html_clean)
        assert len(flagged_clean) == 0

        html_dirty = """
        <html><body>
            <p>The the the the the the the the the.</p>
        </body></html>
        """
        flagged_dirty = QualityAuditor.audit_html(html_dirty)
        assert len(flagged_dirty) >= 1
