# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading a fetched page: its recipe data whole, its text without the markup."""

from __future__ import annotations

from imports.page import MAX_TEXT, read_page

_PAGE = """<!doctype html>
<html><head>
<title>Best Tomato Sauce | Example Kitchen</title>
<script type="application/ld+json">
{"@context": "https://schema.org", "@graph": [
  {"@type": "WebPage", "name": "Best Tomato Sauce"},
  {"@type": "Recipe", "name": "Tomato sauce", "recipeYield": "4"}
]}
</script>
<style>p { color: red }</style>
</head>
<body>
<nav>Home Recipes About</nav>
<p>My grandmother made this every Sunday.</p>
<script>trackVisitor();</script>
<h2>Ingredients</h2><ul><li>6 tomatoes</li><li>2 garlic cloves</li></ul>
</body></html>
"""


def test_the_recipe_data_is_lifted_out_whole() -> None:
    source = read_page("https://example.com/sauce", _PAGE)
    assert source.kind == "page"
    assert source.title == "Best Tomato Sauce | Example Kitchen"
    assert len(source.structured) == 1
    assert '"name": "Tomato sauce"' in source.structured[0]


def test_the_text_keeps_the_words_and_drops_the_code() -> None:
    text = read_page("https://example.com/sauce", _PAGE).text
    assert "6 tomatoes" in text
    assert "2 garlic cloves" in text
    assert "trackVisitor" not in text
    assert "color: red" not in text


def test_a_page_that_never_closes_its_head_keeps_its_body() -> None:
    """HTML allows leaving out </head>; skipping the head must not skip the page."""
    source = read_page(
        "https://example.com/r", "<html><head><title>T</title><body><p>Body text</p>"
    )
    assert "Body text" in source.text


def test_broken_recipe_data_is_ignored() -> None:
    page = '<script type="application/ld+json">{not json</script><p>Text</p>'
    source = read_page("https://example.com/r", page)
    assert source.structured == ()
    assert source.text == "Text"


def test_a_recipe_with_several_types_is_found() -> None:
    page = (
        '<script type="application/ld+json">[{"@type": ["Recipe", "HowTo"], "name": "X"}]</script>'
    )
    assert len(read_page("https://example.com/r", page).structured) == 1


def test_a_very_long_page_is_cut_and_says_so() -> None:
    text = read_page("https://example.com/r", "<p>" + "word " * MAX_TEXT + "</p>").text
    assert len(text) < MAX_TEXT + 100
    assert text.endswith("the rest was cut.]")
