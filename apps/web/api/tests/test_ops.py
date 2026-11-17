# SPDX-License-Identifier: AGPL-3.0-or-later
"""The ops API: every import and recipe, and only for the LAN or a VPN.

It ignores ownership by design, so who may reach it matters more than anywhere
else. A valid token is not enough: a request that came through the Cloudflare
tunnel or any other proxy, or from a public address, is refused.
"""

from __future__ import annotations

import pytest

from api.auth import direct_from_the_lan
from catalog.projection import project_recipe
from imports.models import ImportJob
from snapcook_core.cooklang import parse_cook
from snapcook_core.store import FilesystemStore

pytestmark = [pytest.mark.django_db, pytest.mark.urls("api.tests.ops_urls")]

_TOKEN = "ops-" + "k3Q9x7Lm2Vt8Rw4Zp6Nb1Yc5" * 2
_PDF = b"%PDF-1.7\n" + b"0" * 64
_KAESEKUCHEN = """---
title: Käsekuchen
lang: de
---
Bei ^conventional{175%C} (^fan{155%C}) ~{55%min} backen.
"""


@pytest.fixture
def server(settings, tmp_path, django_user_model):
    """A saved import: its uploaded PDF, the model's reading, the stored recipe."""
    settings.SNAPCOOK_OPS_API_TOKEN = _TOKEN
    settings.SNAPCOOK_STORE_DIR = tmp_path / "store"
    settings.SNAPCOOK_SOURCES_DIR = tmp_path / "sources"
    owner = django_user_model.objects.create_user(username="nonna", email="nonna@example.com")
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    recipe = parse_cook(_KAESEKUCHEN)
    store.commit(recipe, author="nonna", created_at="2026-11-17T20:00:00", origin="imported")
    row = project_recipe(store, recipe.id, owner)
    job = ImportJob.objects.create(
        owner=owner,
        kind=ImportJob.Kind.FILES,
        status=ImportJob.Status.SAVED,
        extraction={"cooklang": "Bei ^{175%C} backen.", "left_out": ["the comments"]},
        cooklang=_KAESEKUCHEN,
        left_out=["the comments"],
        recipe_slug=row.slug,
    )
    job.source_dir().mkdir(parents=True)
    (job.source_dir() / "1.pdf").write_bytes(_PDF)
    return job, row


def _get(client, path: str, **extra):
    extra.setdefault("REMOTE_ADDR", "192.168.1.20")
    return client.get(f"/ops/api/{path}", HTTP_AUTHORIZATION=f"Bearer {_TOKEN}", **extra)


def test_the_lan_sees_every_import(server, client) -> None:
    job, row = server
    (listed,) = _get(client, "imports").json()
    assert (listed["id"], listed["owner"], listed["recipe_slug"]) == (
        str(job.pk),
        "nonna",
        row.slug,
    )
    assert listed["source_files"] == ["1.pdf"]


def test_an_import_shows_its_reading_and_what_was_saved(server, client) -> None:
    job, _row = server
    detail = _get(client, f"imports/{job.pk}").json()
    assert detail["reading"]["cooklang"] == "Bei ^{175%C} backen."
    assert detail["left_out"] == ["the comments"]
    assert "^conventional{175%C} (^fan{155%C})" in detail["saved"]


def test_a_source_comes_back_as_uploaded(server, client) -> None:
    job, _row = server
    response = _get(client, f"imports/{job.pk}/sources/1.pdf")
    assert response["Content-Type"] == "application/pdf"
    assert b"".join(response.streaming_content) == _PDF
    assert _get(client, f"imports/{job.pk}/sources/2.pdf").status_code == 404


def test_a_recipe_comes_back_as_cooklang(server, client) -> None:
    _job, row = server
    recipe = _get(client, f"recipes/{row.slug}").json()
    assert (recipe["owner"], recipe["origin"], recipe["versions"]) == ("nonna", "imported", 1)
    assert recipe["cooklang"].startswith("---\ntitle: Käsekuchen")


@pytest.mark.parametrize(
    "header",
    ["HTTP_CF_CONNECTING_IP", "HTTP_CF_RAY", "HTTP_X_FORWARDED_FOR", "HTTP_FORWARDED"],
)
def test_a_valid_token_through_a_tunnel_or_proxy_is_refused(server, client, header) -> None:
    assert _get(client, "imports", **{header: "198.51.100.7"}).status_code == 401


@pytest.mark.parametrize(
    ("address", "allowed"),
    [
        ("192.168.1.20", True),
        ("10.0.0.5", True),
        ("172.17.0.1", True),  # Docker's bridge
        ("127.0.0.1", True),
        ("100.101.102.103", True),  # Tailscale
        ("::ffff:192.168.1.20", True),
        ("8.8.8.8", False),
        ("2a00:1450:4001:80b::200e", False),
    ],
)
def test_only_private_and_vpn_addresses_may_ask(server, client, address, allowed) -> None:
    assert (_get(client, "imports", REMOTE_ADDR=address).status_code == 200) is allowed


def test_without_the_token_nothing(server, client) -> None:
    assert client.get("/ops/api/imports", REMOTE_ADDR="192.168.1.20").status_code == 401


def test_the_guard_reads_only_the_connection(rf) -> None:
    request = rf.get("/ops/api/health", REMOTE_ADDR="192.168.1.20", HTTP_X_REAL_IP="10.0.0.1")
    assert not direct_from_the_lan(request)
    assert not direct_from_the_lan(rf.get("/", REMOTE_ADDR="not-an-address"))
