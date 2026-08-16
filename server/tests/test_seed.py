"""Seeding prebuilt daily pipeline presets (Q1-Q10)."""

from __future__ import annotations

import pytest

from app.seed import PRESET_DEFINITIONS, seed_default_definitions
from fakes import FakeRepo


def test_three_presets_with_correct_universe_hints():
    by_name = {d["name"]: d for d in PRESET_DEFINITIONS}
    assert set(by_name) == {"Daily VCP Scan", "Daily BO Scan", "Daily EP Scan"}
    assert by_name["Daily BO Scan"]["defaults"]["universe_source"] == "snapshot"
    assert by_name["Daily VCP Scan"]["defaults"]["universe_source"] == "paste"
    assert by_name["Daily EP Scan"]["defaults"]["universe_source"] == "paste"


def test_preset_graphs_are_valid():
    import stock_analyze.tools  # noqa: F401  (registers the builtins)

    from stock_analyze.tools.canvas import validate_canvas_graph

    for preset in PRESET_DEFINITIONS:
        assert validate_canvas_graph(preset) == [], preset["name"]


@pytest.mark.asyncio
async def test_seed_creates_three_definitions_when_absent():
    repo = FakeRepo()
    created = await seed_default_definitions(repo)
    assert created == 3
    assert {d["name"] for d in repo.definitions.values()} == {
        "Daily VCP Scan",
        "Daily BO Scan",
        "Daily EP Scan",
    }


@pytest.mark.asyncio
async def test_seed_is_idempotent():
    repo = FakeRepo()
    await seed_default_definitions(repo)
    created = await seed_default_definitions(repo)
    assert created == 0
    assert len(repo.definitions) == 3


@pytest.mark.asyncio
async def test_seed_preserves_edited_preset():
    repo = FakeRepo()
    await seed_default_definitions(repo)
    vcp = next(d for d in repo.definitions.values() if d["name"] == "Daily VCP Scan")
    vcp["graph"]["nodes"][1]["variables"]["family"] = "custom"  # user edit
    created = await seed_default_definitions(repo)
    assert created == 0
    assert vcp["graph"]["nodes"][1]["variables"]["family"] == "custom"


@pytest.mark.asyncio
async def test_seed_recreates_deleted_preset():
    repo = FakeRepo()
    await seed_default_definitions(repo)
    bo_id = next(i for i, d in repo.definitions.items() if d["name"] == "Daily BO Scan")
    del repo.definitions[bo_id]
    created = await seed_default_definitions(repo)
    assert created == 1
    assert any(d["name"] == "Daily BO Scan" for d in repo.definitions.values())
