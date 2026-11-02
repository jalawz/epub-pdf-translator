import re
from typing import Tuple, Dict

class CodeShield:
    """Protects source code, tags, URLs and technical identifiers from translation corruption."""

    @staticmethod
    def mask_code_blocks(inner_html: str) -> Tuple[str, Dict[str, str]]:
        """Mask entire <pre>...</pre> blocks so child code blocks are not sent to translator."""
        placeholders = {}
        def repl(match):
            key = f"[[_CODE_BLOCK_{len(placeholders)}_]]"
            placeholders[key] = match.group(0)
            return f"\n{key}\n"
        masked = re.sub(r'<pre[^>]*>.*?</pre>', repl, inner_html, flags=re.DOTALL)
        return masked, placeholders

    @staticmethod
    def unmask_code_blocks(text: str, placeholders: Dict[str, str]) -> str:
        """Restore all shielded code blocks."""
        restored = text
        for token, original_block in placeholders.items():
            restored = restored.replace(token, original_block)
            idx = token.split("_")[3]
            pattern = r'\[\[\s*_CODE_BLOCK_' + idx + r'_\s*\]\]'
            restored = re.sub(pattern, lambda m, b=original_block: b, restored)
        return restored

    @staticmethod
    def mask_html_tags(inner_html: str) -> Tuple[str, Dict[str, str]]:
        """Mask all inner HTML tags (e.g., <code>, <a>, <span>) with safe tokens."""
        placeholders = {}
        
        def repl(match):
            key = f"[[_TAG_{len(placeholders)}_]]"
            placeholders[key] = match.group(0)
            return key

        # Match any HTML tag: <...>, </...>, <.../>
        masked_text = re.sub(r'<[^>]+>', repl, inner_html)
        return masked_text, placeholders

    @staticmethod
    def unmask_html_tags(translated_text: str, placeholders: Dict[str, str]) -> str:
        """Restore all original HTML tags, accounting for possible translator spacing artifacts."""
        restored = translated_text
        for token, original_tag in placeholders.items():
            restored = restored.replace(token, original_tag)
            # Handle potential space insertions by translation engines (e.g. [[ _TAG_0_ ]])
            idx = token.split("_")[2]
            pattern = r'\[\[\s*_TAG_' + idx + r'_\s*\]\]'
            restored = re.sub(pattern, original_tag, restored)
        return restored
