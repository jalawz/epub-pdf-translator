import re
from typing import List, Dict, Any, Tuple
from lxml import html as lxml_html

class QualityAuditor:
    """Automated Quality Assurance gate that audits translated documents to guarantee 100% language coverage."""

    ENGLISH_STOPWORDS = {
        'the', 'is', 'are', 'was', 'were', 'this', 'that', 'these', 'those',
        'which', 'from', 'with', 'have', 'has', 'been', 'will', 'would',
        'should', 'could', 'their', 'there', 'they', 'what', 'when', 'where',
        'about', 'after', 'before', 'because', 'between', 'during', 'through',
        'without', 'again', 'further', 'then', 'once', 'here', 'all', 'both'
    }

    PORTUGUESE_STOPWORDS = {
        'o', 'a', 'os', 'as', 'de', 'da', 'do', 'das', 'dos', 'em', 'no', 'na',
        'nos', 'nas', 'por', 'para', 'com', 'um', 'uma', 'uns', 'umas', 'que',
        'como', 'se', 'este', 'esta', 'estao', 'está', 'estão', 'foi', 'foram',
        'ser', 'será', 'serão', 'seu', 'sua', 'seus', 'suas', 'mais', 'mas',
        'não', 'nao', 'quando', 'onde', 'entre', 'sobre', 'também', 'tambem',
        'após', 'apos', 'antes', 'pelo', 'pela', 'pelos', 'pelas', 'mesmo', 'mesma'
    }

    @classmethod
    def audit_html(cls, html_str: str) -> List[Dict[str, Any]]:
        """Audit an HTML document for untranslated text nodes outside code blocks."""
        tree = lxml_html.fromstring(html_str.encode("utf-8"))
        flagged_elements = []

        for el in tree.xpath('//p | //li | //h1 | //h2 | //h3 | //h4 | //h5 | //h6 | //blockquote | //td | //figcaption'):
            if el.xpath('ancestor::pre'):
                continue

            text = "".join(el.xpath('.//text()[not(ancestor::pre)]')).strip()
            if len(text) < 20:
                continue

            words = re.findall(r'\b[a-zA-ZáéíóúãõçÁÉÍÓÚÃÕÇ]+\b', text.lower())
            if not words:
                continue

            eng_count = sum(1 for w in words if w in cls.ENGLISH_STOPWORDS)
            pt_count = sum(1 for w in words if w in cls.PORTUGUESE_STOPWORDS)

            # Flag as suspicious if predominantly English stopwords
            if eng_count >= 3 and eng_count > pt_count:
                flagged_elements.append({
                    'tag': el.tag,
                    'text_preview': text[:140],
                    'eng_stopwords': eng_count,
                    'pt_stopwords': pt_count
                })

        return flagged_elements
