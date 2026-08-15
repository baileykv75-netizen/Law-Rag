from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .models import LegalArticle

ARTICLE_RE = re.compile(r"^\s*(第(?P<number>[零〇一二三四五六七八九十百千万两\d]+)条)(?:[\s　]*(?P<rest>.*))$")
CHAPTER_RE = re.compile(r"^\s*第[零〇一二三四五六七八九十百千万两\d]+(?:编|分编|章|节)\s*.*$")
SECTION_RE = re.compile(r"^\s*[一二三四五六七八九十百千万]+、\s*.+$")

DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}


class LegalParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedLegalText:
    articles: list[LegalArticle]
    preamble_text: str | None


def normalize_snapshot_text(text: str) -> str:
    normalized = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    return normalized.strip() + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chinese_integer(value: str) -> int | None:
    if value.isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    if not value:
        return None
    if all(char in DIGITS for char in value):
        rendered = "".join(str(DIGITS[char]) for char in value)
        parsed = int(rendered)
        return parsed if parsed > 0 else None

    total = 0
    section = 0
    number = 0
    seen = False
    for char in value:
        if char in DIGITS:
            number = DIGITS[char]
            seen = True
            continue
        unit = UNITS.get(char)
        if unit is None:
            return None
        seen = True
        if unit == 10000:
            section += number
            total += (section or 1) * 10000
            section = 0
            number = 0
        else:
            section += (number or 1) * unit
            number = 0
    parsed = total + section + number if seen else 0
    return parsed if parsed > 0 else None


def _article_id(ordinal: int | None, token: str) -> str:
    if ordinal is not None:
        return f"article-{ordinal}"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return f"article-{digest}"


def _legal_evidence_id(authority_id: str, version_id: str, article_id: str) -> str:
    return f"legal:{authority_id}:{version_id}:{article_id}"


def parse_chinese_articles(text: str, *, authority_id: str, version_id: str) -> ParsedLegalText:
    """Parse article headings only when they begin a physical line.

    References such as "依据民法典第五百八十四条" inside prose are therefore not
    mistaken for new articles. Structural headings are retained as context instead
    of being discarded. Article text preserves snapshot line content except for
    normalized newline encoding and outer-document whitespace normalization.
    """

    normalized = normalize_snapshot_text(text)
    lines = normalized.splitlines()
    preamble: list[str] = []
    headings: list[str] = []
    articles: list[LegalArticle] = []
    current_token: str | None = None
    current_ordinal: int | None = None
    current_lines: list[str] = []
    current_context: list[str] = []

    def flush() -> None:
        nonlocal current_token, current_ordinal, current_lines, current_context
        if current_token is None:
            return
        article_text = "\n".join(current_lines).strip()
        if not article_text:
            raise LegalParseError(f"Article {current_token} is empty.")
        article_id = _article_id(current_ordinal, current_token)
        articles.append(
            LegalArticle(
                authority_id=authority_id,
                version_id=version_id,
                article_id=article_id,
                article_token=current_token,
                article_ordinal=current_ordinal,
                text=article_text,
                text_sha256=sha256_text(article_text),
                legal_evidence_id=_legal_evidence_id(authority_id, version_id, article_id),
                heading_context=list(current_context),
            )
        )
        current_token = None
        current_ordinal = None
        current_lines = []
        current_context = []

    for raw_line in lines:
        line = raw_line.rstrip()
        article_match = ARTICLE_RE.match(line)
        if article_match:
            flush()
            current_token = article_match.group(1)
            current_ordinal = chinese_integer(article_match.group("number"))
            current_context = list(headings)
            current_lines = [line]
            continue

        if CHAPTER_RE.match(line) or SECTION_RE.match(line):
            if current_token is not None:
                flush()
            heading = line.strip()
            if heading:
                headings = [*headings[-3:], heading]
                if not articles:
                    preamble.append(heading)
            continue

        if current_token is None:
            if line.strip():
                preamble.append(line.strip())
            continue

        current_lines.append(line)

    flush()

    if not articles:
        raise LegalParseError("No Chinese article headings were found in the source snapshot.")

    tokens = [article.article_token for article in articles]
    duplicates = sorted({token for token in tokens if tokens.count(token) > 1})
    if duplicates:
        raise LegalParseError(f"Duplicate article tokens: {', '.join(duplicates)}")

    preamble_text = "\n".join(preamble).strip() or None
    return ParsedLegalText(articles=articles, preamble_text=preamble_text)
