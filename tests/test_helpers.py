from __future__ import annotations

import pytest

from tm.helpers import (
    deep_merge,
    json_patch_apply,
    json_patch_diff,
    json_merge_patch,
    parallel,
    switch,
)


@pytest.mark.asyncio
async def test_switch_helper_with_config():
    ctx = {"config": {"cases": {"manual": "manual"}, "default": "auto"}}
    state = {"branch": "manual"}
    result = await switch(ctx, state)
    assert result == "manual"


@pytest.mark.asyncio
async def test_parallel_helper_merges_results():
    async def branch_a(ctx, state):
        return {"text": "A"}

    def branch_b(ctx, state):
        return {"label": "B"}

    ctx = {"config": {"branches_map": {"a": branch_a, "b": branch_b}}}
    merged = await parallel(ctx, {})
    assert merged == {"text": "A", "label": "B"}


def test_deep_merge_and_patches():
    base = {"a": {"b": 1}, "c": [1]}
    update = {"a": {"d": 2}, "c": [2, 3]}
    merged = deep_merge(base, update)
    assert merged == {"a": {"b": 1, "d": 2}, "c": [2, 3]}

    src = {"k": 1, "arr": [1, 2]}
    dst = {"k": 2, "arr": [1, 2, 3]}
    patch = json_patch_diff(src, dst)
    applied = json_patch_apply(src, patch)
    assert applied == dst

    merge_patch = {"k": None, "x": 5}
    merged2 = json_merge_patch(src, merge_patch)
    assert merged2 == {"arr": [1, 2], "x": 5}
