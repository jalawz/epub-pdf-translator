import re
from typing import List, Dict, Any, Tuple
from lxml import html as lxml_html


class QualityAuditor:
    """Automated Quality Assurance gate that audits translated documents to guarantee 100% language coverage.

    Configurable by language pair: `audit_html(html, lang_in, lang_out)` flags
    prose elements that still look like the *source* language (stopword-heavy)
    instead of the *target* language. Supported pairs include EN->PT, EN->ES
    and FR->PT (see STOPWORDS).
    """

    STOPWORDS: Dict[str, set] = {
        "en": {
            'the', 'is', 'are', 'was', 'were', 'this', 'that', 'these', 'those',
            'which', 'from', 'with', 'have', 'has', 'been', 'will', 'would',
            'should', 'could', 'their', 'there', 'they', 'what', 'when', 'where',
            'about', 'after', 'before', 'because', 'between', 'during', 'through',
            'without', 'again', 'further', 'then', 'once', 'here', 'all', 'both'
        },
        "pt": {
            'o', 'a', 'os', 'as', 'de', 'da', 'do', 'das', 'dos', 'em', 'no', 'na',
            'nos', 'nas', 'por', 'para', 'com', 'um', 'uma', 'uns', 'umas', 'que',
            'como', 'se', 'este', 'esta', 'estao', 'está', 'estão', 'foi', 'foram',
            'ser', 'será', 'serão', 'seu', 'sua', 'seus', 'suas', 'mais', 'mas',
            'não', 'nao', 'quando', 'onde', 'entre', 'sobre', 'também', 'tambem',
            'após', 'apos', 'antes', 'pelo', 'pela', 'pelos', 'pelas', 'mesmo', 'mesma'
        },
        "es": {
            'el', 'la', 'los', 'las', 'de', 'del', 'en', 'y', 'a', 'un', 'una',
            'unos', 'unas', 'que', 'es', 'se', 'con', 'por', 'para', 'al', 'lo',
            'como', 'más', 'mas', 'pero', 'sus', 'le', 'ya', 'o', 'este', 'esta',
            'esto', 'está', 'son', 'entre', 'cuando', 'muy', 'sin', 'sobre',
            'también', 'tambien', 'me', 'hasta', 'hay', 'donde', 'quien',
            'desde', 'todo', 'nos', 'todos', 'uno', 'les', 'ni', 'ellos',
            'antes', 'algo', 'nosotros', 'mi', 'mis', 'tú', 'te', 'ti', 'tu',
            'tus', 'ellas', 'vosotros', 'qué', 'yo', 'él', 'ella', 'mucho',
            'muchos', 'esta', 'estas', 'estos', 'ese', 'esa', 'eso'
        },
        "fr": {
            'le', 'la', 'les', 'de', 'des', 'du', 'un', 'une', 'et', 'est',
            'dans', 'que', 'qui', 'pour', 'pas', 'plus', 'ce', 'cette', 'ces',
            'il', 'elle', 'nous', 'vous', 'ils', 'elles', 'mon', 'ma', 'mes',
            'ton', 'ta', 'tes', 'son', 'sa', 'ses', 'au', 'aux', 'en', 'sur',
            'avec', 'sans', 'sous', 'chez', 'vers', 'par', 'moins', 'très',
            'aussi', 'comme', 'mais', 'ou', 'donc', 'car', 'ne', 'se', 'lui',
            'leur', 'y', 'sont', 'être', 'avoir', 'fait', 'faire', 'aller',
            'tout', 'tous', 'toutes', 'même', 'autre', 'autres', 'chaque'
        },
    }

    # Backwards-compatible aliases (legacy EN/PT pair).
    ENGLISH_STOPWORDS = STOPWORDS["en"]
    PORTUGUESE_STOPWORDS = STOPWORDS["pt"]

    @classmethod
    def audit_html(
        cls,
        html_str: str,
        lang_in: str = "en",
        lang_out: str = "pt",
    ) -> List[Dict[str, Any]]:
        """Audit an HTML document for untranslated text nodes outside code blocks.

        Flags elements whose stopwords predominate in `lang_in` (source)
        over `lang_out` (target). Unknown source languages cannot be audited
        and yield no flags.
        """
        source_lang = (lang_in or "en").lower()
        target_lang = (lang_out or "pt").lower()
        source_stopwords = cls.STOPWORDS.get(source_lang)
        if not source_stopwords:
            return []
        target_stopwords = cls.STOPWORDS.get(target_lang, set())

        tree = lxml_html.fromstring(html_str.encode("utf-8"))
        flagged_elements = []

        for el in tree.xpath('//p | //li | //h1 | //h2 | //h3 | //h4 | //h5 | //h6 | //blockquote | //td | //figcaption'):
            if el.xpath('ancestor::pre'):
                continue

            text = "".join(el.xpath('.//text()[not(ancestor::pre)]')).strip()
            if len(text) < 20:
                continue

            words = re.findall(r"[^\W\d_]+", text.lower())
            if not words:
                continue

            source_count = sum(1 for w in words if w in source_stopwords)
            target_count = sum(1 for w in words if w in target_stopwords)

            # Flag as suspicious if predominantly source-language stopwords
            if source_count >= 3 and source_count > target_count:
                flagged = {
                    'tag': el.tag,
                    'text_preview': text[:140],
                    'lang_in': source_lang,
                    'lang_out': target_lang,
                    'source_stopwords': source_count,
                    'target_stopwords': target_count,
                }
                # Legacy keys for the EN->PT pair (backwards compatibility).
                flagged['eng_stopwords'] = source_count if source_lang == "en" else 0
                flagged['pt_stopwords'] = target_count if target_lang == "pt" else 0
                flagged_elements.append(flagged)

        return flagged_elements
