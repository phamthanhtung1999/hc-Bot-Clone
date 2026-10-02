"""Convert Zendesk article HTML into clean, LLM-friendly Markdown."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Comment, Tag
from markdownify import MarkdownConverter

from .scraper import Article

# Elements that are never article content (site chrome, widgets, ads, scripts).
NOISE_TAGS = ("script", "style", "noscript", "nav", "header", "footer", "aside", "form", "button", "svg")
NOISE_CLASS_RE = re.compile(r"(^|[-_ ])(ad|ads|advert|banner|promo|cookie|share|social|breadcrumbs?)($|[-_ ])", re.I)
# Inline wrappers that only carry styling.
UNWRAP_TAGS = ("span", "font", "u")
ANCHOR_TOKEN = "KBANCHOR{}KBEND"
ANCHOR_RE = re.compile(r"KBANCHOR([0-9a-f]+)KBEND")
ZERO_WIDTH_RE = re.compile("[​‌‍⁠﻿]")


@dataclass(frozen=True)
class Doc:
    article_id: str
    filename: str
    url: str
    title: str
    updated_at: str
    content: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def _code_language(el: Tag) -> str:
    for node in (el, el.find("code")):
        if isinstance(node, Tag):
            for cls in node.get("class") or []:
                if cls.startswith(("language-", "lang-")):
                    return cls.split("-", 1)[1]
    return ""


def _absolutize(url: str) -> str:
    # Protocol-relative URLs ("//cdn...") break outside a browser; give them a scheme.
    return "https:" + url if url.startswith("//") else url


def _preprocess(soup: BeautifulSoup) -> None:
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()
    for tag in soup.find_all(class_=NOISE_CLASS_RE):
        tag.decompose()
    for tag in soup.find_all(UNWRAP_TAGS):
        tag.unwrap()

    # In-page anchors (<a name="X"></a>) are targets of the article's own TOC links
    # ("#X"). markdownify drops empty anchors, so protect them with a token and
    # re-emit them as inline HTML afterwards; this keeps relative links working.
    for a in soup.find_all("a"):
        name = a.get("name") or (a.get("id") if not a.get("href") else None)
        if name and not a.get_text(strip=True):
            a.replace_with(ANCHOR_TOKEN.format(name.encode().hex()))
            continue
        if a.get("href"):
            a["href"] = _absolutize(a["href"].strip())

    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src or src.startswith("data:"):
            img.decompose()
        else:
            img["src"] = _absolutize(src)

    # Embedded videos would vanish entirely; keep them as links.
    for frame in soup.find_all(["iframe", "video"]):
        source = frame.find("source")
        src = frame.get("src") or (source.get("src") if source else None)
        if src:
            p = soup.new_tag("p")
            link = soup.new_tag("a", href=_absolutize(src))
            link.string = f"Embedded video: {_absolutize(src)}"
            p.append(link)
            frame.replace_with(p)
        else:
            frame.decompose()

    # Zendesk "callout" boxes are 1-column tables (IMPORTANT / NOTE / TIP).
    # A Markdown table with an empty header row reads badly; use a blockquote.
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if rows and all(len(r.find_all(["td", "th"], recursive=False)) == 1 for r in rows):
            quote = soup.new_tag("blockquote")
            for r in rows:
                cell = r.find(["td", "th"], recursive=False)
                for child in list(cell.contents):
                    quote.append(child)
            (table.find_parent("figure") or table).replace_with(quote)
    for fig in soup.find_all("figure"):
        fig.unwrap()


def _postprocess(md: str) -> str:
    md = ANCHOR_RE.sub(lambda m: f'<a id="{bytes.fromhex(m.group(1)).decode()}"></a>', md)
    md = md.replace("\xa0", " ")
    md = ZERO_WIDTH_RE.sub("", md)
    md = "\n".join(line.rstrip() for line in md.splitlines())
    md = re.sub(r"\n{3,}", "\n\n", md)
    # Lines that are only a blockquote marker add noise.
    md = re.sub(r"(\n>\s*){2,}\n", "\n>\n", md)
    return md.strip()


def html_to_markdown(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    _preprocess(soup)
    md = MarkdownConverter(
        heading_style="ATX",
        bullets="-",
        code_language_callback=_code_language,
        escape_underscores=False,
        escape_asterisks=False,
        table_infer_header=True,
        keep_inline_images_in=["td", "th", "li", "a", "strong", "em", "blockquote"],
    ).convert_soup(soup)
    return _postprocess(md)


def slug_for(article: Article) -> str:
    """`<id>-<Title-Slug>` taken from the canonical URL, e.g. 360017964153-How-to-..."""
    tail = urlparse(article.html_url).path.rstrip("/").rsplit("/", 1)[-1]
    if not tail.startswith(str(article.id)):
        tail = f"{article.id}-{article.title}"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", tail).strip("-")
    return slug[:150] or str(article.id)


def render(article: Article) -> Doc:
    """Final Markdown file: title, source URL (for citations), body, URL again.

    The URL appears at the top *and* bottom so that both the first and the last
    chunk of a long article carry a citable "Article URL:" line.
    """
    body = html_to_markdown(article.body)
    content = (
        f"# {article.title}\n\n"
        f"Article URL: {article.html_url}\n\n"
        f"{body}\n\n"
        f"---\n"
        f"Article URL: {article.html_url}\n"
    )
    return Doc(
        article_id=str(article.id),
        filename=f"{slug_for(article)}.md",
        url=article.html_url,
        title=article.title,
        updated_at=article.updated_at,
        content=content,
    )
