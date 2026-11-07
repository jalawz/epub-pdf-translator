import re
from typing import Tuple, Dict


class CodeShield:
    """Protects source code, tags, URLs and technical identifiers from translation corruption."""

    # Regex robusta que tolera espaços entre colchetes e ao redor do conteúdo do token.
    # Exemplo: [[_CODE_BLOCK_0_]], [ [ _CODE_BLOCK_0_ ] ], [[ _CODE_BLOCK_0_ ]]
    # Os \s* nas bordas consomem espaços que o tradutor pode ter inserido ao redor do placeholder.
    _TOKEN_RE_CODE = re.compile(
        r"\s*\[\s*\[\s*_CODE_BLOCK_\s*(?P<idx>\d+)\s*_\s*\]\s*\]\s*"
    )
    _TOKEN_RE_TAG = re.compile(
        r"\s*\[\s*\[\s*_TAG_\s*(?P<idx>\d+)\s*_\s*\]\s*\]\s*"
    )

    @staticmethod
    def mask_code_blocks(inner_html: str) -> Tuple[str, Dict[str, str]]:
        """Mask entire <pre>...</pre> blocks so child code blocks are not sent to translator."""
        placeholders: Dict[str, str] = {}

        def repl(match):
            key = f"[[_CODE_BLOCK_{len(placeholders)}_]]"
            placeholders[key] = match.group(0)
            return key

        masked = re.sub(r"<pre[^>]*>.*?</pre>", repl, inner_html, flags=re.DOTALL)
        return masked, placeholders

    @staticmethod
    def unmask_code_blocks(text: str, placeholders: Dict[str, str]) -> str:
        """Restore all shielded code blocks, tolerating translator spacing artifacts."""
        restored = text
        for token, original_block in placeholders.items():
            # 1. Substituição exata (token inalterado pelo tradutor)
            restored = restored.replace(token, original_block)

            # 2. Substituição tolerando espaços (ex: [ [ _CODE_BLOCK_0_ ] ])
            idx = token.split("_")[3]
            restored = CodeShield._TOKEN_RE_CODE.sub(
                lambda m, b=original_block, i=idx: b
                if m.group("idx") == i
                else m.group(0),
                restored,
            )
        return restored

    @staticmethod
    def mask_html_tags(inner_html: str) -> Tuple[str, Dict[str, str]]:
        """Mask all inner HTML tags (e.g., <code>, <a>, <span>) with safe tokens."""
        placeholders: Dict[str, str] = {}

        def repl(match):
            key = f"[[_TAG_{len(placeholders)}_]]"
            placeholders[key] = match.group(0)
            return key

        # Match any HTML tag: <...>, </...>, <.../>
        masked_text = re.sub(r"<[^>]+>", repl, inner_html)
        return masked_text, placeholders

    @staticmethod
    def unmask_html_tags(translated_text: str, placeholders: Dict[str, str]) -> str:
        """Restore all original HTML tags, accounting for possible translator spacing artifacts."""
        restored = translated_text
        for token, original_tag in placeholders.items():
            # 1. Substituição exata
            restored = restored.replace(token, original_tag)

            # 2. Substituição tolerando espaços (ex: [ [ _TAG_0_ ] ])
            idx = token.split("_")[2]
            restored = CodeShield._TOKEN_RE_TAG.sub(
                lambda m, b=original_tag, i=idx: b
                if m.group("idx") == i
                else m.group(0),
                restored,
            )
        return restored
