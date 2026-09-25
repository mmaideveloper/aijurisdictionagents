"""Reject conversational export placeholders, without judging legal completeness."""
from __future__ import annotations

import re
import unicodedata


def is_status_only_document(content: str) -> bool:
    """Recognize status/boilerplate-only text, including wrapped legacy payloads.

    A real clause beside an introductory status message must remain exportable.
    This is deliberately not a legal quality or required-fields validator.
    """
    normalized = "".join(
        char for char in unicodedata.normalize("NFKD", content.lower())
        if not unicodedata.combining(char)
    )
    status_pattern = (
        r"spracovanie stale prebieha|processing (?:is )?(?:still )?in progress|"
        r"(?:dokument|document|export|pdf|balik).{0,100}(?:pripraven|ready|bereit)|"
        r"(?:pripravim|vygenerujem|i will (?:prepare|generate)).{0,80}(?:dokument|zmluv|document|contract)|"
        r"please wait|chvilu.*(?:prosim|trva)|dokument sa nepodarilo ulozit|document could not be saved"
    )
    if not re.search(status_pattern, " ".join(normalized.split())):
        return False
    # Split complete sentences first, then lines: PDF extraction can wrap a
    # status sentence, while markdown often separates an intro from real clauses.
    status_line = re.compile(status_pattern)
    boilerplate = re.compile(
        r"^(?:spracovanie|processing|stav dokument|document status|"
        r"(?:dokument|document|export|pdf|balik).*(?:pripraven|ready|bereit)|"
        r"(?:pripraven\w*|ready) na|stiahnutie|vo formate pdf|"
        r"mozete si ho|pomocou nasledujuceho odkazu|ak mate dalsie|"
        r"dokumentmi,|neva[hž]ajte sa|if you have|you can download|"
        r"using the following link|feel free|generated case document:|"
        r"pravny zaklad|skore overenia|dokument je pravny navrh|"
        r"api version:|core version:|jurisdigta\b)"
    )
    heading = re.compile(
        r"^(?:(?:navrh|finalny navrh)\s+)?(?:pracovna zmluva|zmluva|dokument|"
        r"employment contract|contract|document|splnomocnenie|power of attorney|"
        r"pripraven\w*|ready|hotovo|finished|done)[\s:.-]*$"
    )
    for sentence in re.split(r"[.!?]+(?:\s+|$)", normalized):
        for line in sentence.splitlines():
            line = line.strip(" *#_`->\t\r")
            if not line or not re.search(r"[a-z0-9]", line):
                continue
            if status_line.search(line) or boilerplate.search(line) or heading.fullmatch(line):
                continue
            return False
    return True
