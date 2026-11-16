# SPDX-License-Identifier: Apache-2.0
"""The step structure a reader sees: what builds on what, and what runs in parallel.

The web page turns these into "uses what you made in steps 1 and 2" and "steps
1 and 2 don't depend on each other". They are derived from the graph here, in
core, so the page and any other client tell the same story about one recipe.
"""

from __future__ import annotations

import pytest

from snapcook_core.render import RenderOptions, build_render_model
from snapcook_core.testing import CORPUS, get_recipe


def _model(slug: str):
    return build_render_model(get_recipe(slug), RenderOptions())


def test_a_join_lists_both_branches() -> None:
    """Tomato sauce: aromatics (1) and tomatoes (2) are prepared apart, then joined (3)."""
    steps = _model("004-tomato-sauce").steps
    assert [step.after for step in steps] == [(), (), (1, 2)]


def test_independent_branches_run_side_by_side() -> None:
    assert _model("004-tomato-sauce").side_by_side == ((1, 2),)


def test_a_named_intermediate_links_its_steps() -> None:
    """Pancakes: the batter from step 1 is fried in step 2."""
    model = _model("005-pancakes")
    assert [step.after for step in model.steps] == [(), (1,)]
    assert model.side_by_side == ()


@pytest.mark.parametrize("slug", sorted(CORPUS))
def test_every_dependency_points_backwards(slug: str) -> None:
    """A step can only build on steps a reader has already done."""
    for step in _model(slug).steps:
        assert all(earlier < step.index for earlier in step.after)


@pytest.mark.parametrize("slug", sorted(CORPUS))
def test_steps_in_a_run_never_depend_on_each_other(slug: str) -> None:
    model = _model(slug)
    after = {step.index: set(step.after) for step in model.steps}
    for run in model.side_by_side:
        assert len(run) > 1
        assert list(run) == list(range(run[0], run[-1] + 1)), "runs are consecutive"
        for member in run:
            assert not after[member] & set(run)
