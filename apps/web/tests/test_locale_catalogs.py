# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every interface language has a complete catalogue, compiled from its source.

The ``.mo`` files are committed, so the image and CI need no gettext tools. The
cost is that a ``.po`` edited without running ``compilemessages`` ships stale
strings, and a new string without a translation ships in English. These tests
catch both: every entry is translated, and what Django serves for each entry is
what the ``.po`` says.

German is the proof that the interface is not English-only by construction. A
new language is an entry in ``settings.LANGUAGES`` plus its catalogue, and these
tests then hold it to the same standard.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import translation

_LOCALE = Path(settings.LOCALE_PATHS[0])
_TRANSLATED = [code for code, _ in settings.LANGUAGES if code != "en"]


@dataclass
class _Entry:
    msgid: str = ""
    plural: str | None = None
    msgstr: dict[int, str] = field(default_factory=dict)
    fuzzy: bool = False


def _entries(po: Path) -> list[_Entry]:
    """A minimal ``.po`` reader: enough for catalogues ``makemessages`` writes."""
    entries: list[_Entry] = []
    entry = _Entry()
    target: tuple[str, int] | None = None

    def flush() -> None:
        nonlocal entry
        if entry.msgid:
            entries.append(entry)
        entry = _Entry()

    for line in po.read_text(encoding="utf-8").splitlines() + [""]:
        if not line.strip():
            flush()
            target = None
        elif line.startswith("#,"):
            entry.fuzzy = entry.fuzzy or "fuzzy" in line
        elif line.startswith("#"):
            continue
        else:
            keyword, _, rest = line.partition(" ")
            if line.startswith('"'):
                text = ast.literal_eval(line)
            else:
                text = ast.literal_eval(rest)
                index = re.fullmatch(r"msgstr\[(\d)\]", keyword)
                target = (
                    ("msgstr", int(index.group(1)))
                    if index
                    else {"msgid": ("msgid", 0), "msgid_plural": ("plural", 0)}.get(
                        keyword, ("msgstr", 0)
                    )
                )
            kind, n = target
            if kind == "msgid":
                entry.msgid += text
            elif kind == "plural":
                entry.plural = (entry.plural or "") + text
            else:
                entry.msgstr[n] = entry.msgstr.get(n, "") + text
    return entries


@pytest.mark.parametrize("language", _TRANSLATED)
def test_the_catalogue_exists_and_is_compiled(language: str) -> None:
    directory = _LOCALE / language / "LC_MESSAGES"
    assert (directory / "django.po").is_file()
    assert (directory / "django.mo").is_file(), "run manage.py compilemessages"


@pytest.mark.parametrize("language", _TRANSLATED)
def test_every_string_is_translated(language: str) -> None:
    entries = _entries(_LOCALE / language / "LC_MESSAGES" / "django.po")
    assert entries, "an empty catalogue translates nothing"
    untranslated = [e.msgid for e in entries if e.fuzzy or not all(e.msgstr.values())]
    assert not untranslated, f"untranslated or fuzzy in {language}: {untranslated}"


@pytest.mark.parametrize("language", _TRANSLATED)
def test_the_compiled_catalogue_matches_its_source(language: str) -> None:
    """Fails when a ``.po`` was edited and ``compilemessages`` was not run."""
    with translation.override(language):
        for entry in _entries(_LOCALE / language / "LC_MESSAGES" / "django.po"):
            if entry.plural is None:
                assert translation.gettext(entry.msgid) == entry.msgstr[0], entry.msgid
            else:
                assert translation.ngettext(entry.msgid, entry.plural, 1) == entry.msgstr[0]
                assert translation.ngettext(entry.msgid, entry.plural, 2) == entry.msgstr[1]
