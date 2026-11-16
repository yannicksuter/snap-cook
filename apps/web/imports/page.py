# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read a fetched page into what a model needs: its recipe data and its text.

Most recipe sites publish the recipe as schema.org JSON-LD for search engines.
That is the cleanest statement of it, so it is lifted out whole. The readable
text goes along too, because JSON-LD often drops details a cook needs (pan
sizes, doneness cues). Scripts, styles and markup do not: they are noise the
model would only have to read past.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser

from snapcook_core.importing import ImportSource

__all__ = ["MAX_TEXT", "read_page"]

MAX_TEXT = 60_000
"""Characters of page text passed on, about 15k tokens. A recipe page is far
shorter once its markup is gone; this only bounds pathological pages."""
_MAX_STRUCTURED = 30_000
# Not "head": its closing tag is optional in HTML, and a page that omits it
# would otherwise lose its whole body. The title is read separately anyway.
_SKIP = {"script", "style", "noscript", "template", "svg", "iframe", "canvas"}
_BLOCKS = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article"}


class _Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.json_ld: list[str] = []
        self._text: list[str] = []
        self._skipping: list[str] = []
        self._in_title = False
        self._in_json_ld = False
        self._json_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and ("type", "application/ld+json") in [
            (name, (value or "").strip().lower()) for name, value in attrs
        ]:
            self._in_json_ld = True
            self._json_buffer = []
        if tag == "title" and not self.title:
            self._in_title = True
        if tag in _SKIP:
            self._skipping.append(tag)
        elif tag in _BLOCKS:
            self._text.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_json_ld:
            self._in_json_ld = False
            self.json_ld.append("".join(self._json_buffer))
        if tag == "title":
            self._in_title = False
        if self._skipping and self._skipping[-1] == tag:
            self._skipping.pop()
        elif tag in _BLOCKS:
            self._text.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._json_buffer.append(data)
        elif self._in_title:
            self.title += data
        elif not self._skipping:
            self._text.append(data)

    def text(self) -> str:
        lines = (
            re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in "".join(self._text).split("\n")
        )
        return re.sub(r"\n{3,}", "\n\n", "\n".join(line for line in lines if line)).strip()


def read_page(url: str, html: str) -> ImportSource:
    """The page as an import source: URL, title, JSON-LD recipes and text."""
    reader = _Reader()
    reader.feed(html)
    reader.close()
    text = reader.text()
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT] + "\n[The page goes on; the rest was cut.]"
    return ImportSource(
        kind="page",
        url=url,
        title=re.sub(r"\s+", " ", reader.title).strip()[:300] or None,
        structured=tuple(_recipes(reader.json_ld)),
        text=text,
    )


def _recipes(blocks: list[str]) -> list[str]:
    """Every JSON-LD object typed Recipe, however the page nests it."""
    found: list[str] = []
    for block in blocks:
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for item in _walk(data):
            serialised = json.dumps(item, ensure_ascii=False)
            if len(serialised) <= _MAX_STRUCTURED:
                found.append(serialised)
    return found


def _walk(data: object):
    if isinstance(data, list):
        for item in data:
            yield from _walk(item)
    elif isinstance(data, dict):
        kind = data.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if "Recipe" in kinds:
            yield data
        elif "@graph" in data:
            yield from _walk(data["@graph"])
