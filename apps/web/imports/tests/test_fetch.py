# SPDX-License-Identifier: AGPL-3.0-or-later
"""The worker fetches pages from the public internet and nothing else.

A signed-in reader chooses the URL, so every way into the server's own network
is a test here: loopback, private ranges, link-local metadata addresses, a
redirect that turns inward, a host name with one bad address among good ones.
No test opens a connection.
"""

from __future__ import annotations

import socket
from email.message import Message

import pytest

from imports import fetch
from imports.fetch import MAX_BYTES, FetchError, fetch_page

_REAL_GETADDRINFO = socket.getaddrinfo


def _resolving(table: dict[str, list[str]]):
    def getaddrinfo(host, port, *args, **kwargs):
        if host in table:
            family = socket.AF_INET6
            return [
                (
                    socket.AF_INET6 if ":" in a else socket.AF_INET,
                    socket.SOCK_STREAM,
                    6,
                    "",
                    (a, port),
                )
                for a in table[host]
            ] or [(family, socket.SOCK_STREAM, 6, "", ("", port))]
        return _REAL_GETADDRINFO(host, port, *args, **kwargs)

    return getaddrinfo


class _Response:
    def __init__(self, status: int, body: bytes = b"", headers: dict | None = None) -> None:
        self.status = status
        self._body = body
        self.headers = Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value

    def getheader(self, name: str):
        return self.headers.get(name)

    def read(self, limit: int) -> bytes:
        return self._body[:limit]


class _Connection:
    """Answers by host, in place of a socket."""

    def __init__(self, responses: dict[str, _Response], host: str) -> None:
        self._responses = responses
        self._host = host

    def request(self, method, path, headers) -> None:
        assert headers["User-Agent"].startswith("snap-cook")

    def getresponse(self) -> _Response:
        return self._responses[self._host]

    def close(self) -> None:
        pass


def _serve(monkeypatch, responses: dict[str, _Response]) -> None:
    monkeypatch.setattr(
        fetch, "_connection", lambda scheme, host, port, address: _Connection(responses, host)
    )


@pytest.mark.parametrize("url", ["ftp://example.com/", "file:///etc/passwd", "example.com"])
def test_only_web_urls(url: str) -> None:
    with pytest.raises(FetchError) as refused:
        fetch_page(url)
    assert refused.value.code == "not_allowed"


@pytest.mark.parametrize("url", ["http://example.com:8931/", "https://example.com:22/"])
def test_unusual_ports_are_refused(url: str) -> None:
    with pytest.raises(FetchError) as refused:
        fetch_page(url)
    assert refused.value.code == "not_allowed"


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.5", "192.168.1.10", "172.16.0.1", "169.254.169.254", "100.64.0.1",
     "::1", "fc00::1", "fe80::1", "::ffff:192.168.1.1"],
)  # fmt: skip
def test_the_servers_own_network_is_refused(monkeypatch, address: str) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _resolving({"recipes.test": [address]}))
    with pytest.raises(FetchError) as refused:
        fetch_page("https://recipes.test/sauce")
    assert refused.value.code == "not_allowed"


def test_one_private_address_among_public_ones_is_enough(monkeypatch) -> None:
    """Otherwise a host could answer with both and let the connection pick."""
    resolving = _resolving({"recipes.test": ["93.184.215.14", "10.0.0.5"]})
    monkeypatch.setattr(socket, "getaddrinfo", resolving)
    with pytest.raises(FetchError) as refused:
        fetch_page("https://recipes.test/sauce")
    assert refused.value.code == "not_allowed"


def test_a_redirect_into_the_lan_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _resolving({"recipes.test": ["93.184.215.14"]}))
    _serve(
        monkeypatch, {"recipes.test": _Response(302, headers={"Location": "http://192.168.1.1/"})}
    )
    with pytest.raises(FetchError) as refused:
        fetch_page("https://recipes.test/sauce")
    assert refused.value.code == "not_allowed"


def test_a_public_page_is_read_in_its_charset(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _resolving({"recipes.test": ["93.184.215.14"]}))
    body = "<p>Rösti</p>".encode("latin-1")
    headers = {"Content-Type": "text/html; charset=iso-8859-1"}
    _serve(monkeypatch, {"recipes.test": _Response(200, body, headers)})
    page = fetch_page("https://recipes.test/roesti")
    assert page.html == "<p>Rösti</p>"
    assert page.url == "https://recipes.test/roesti"


def test_a_redirect_is_followed_to_its_target(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        _resolving({"a.test": ["93.184.215.14"], "b.test": ["93.184.215.15"]}),
    )
    _serve(
        monkeypatch,
        {
            "a.test": _Response(301, headers={"Location": "https://b.test/final"}),
            "b.test": _Response(200, b"<p>ok</p>"),
        },
    )
    assert fetch_page("https://a.test/start").url == "https://b.test/final"


def test_a_huge_page_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _resolving({"recipes.test": ["93.184.215.14"]}))
    _serve(monkeypatch, {"recipes.test": _Response(200, b"x" * (MAX_BYTES + 1))})
    with pytest.raises(FetchError) as refused:
        fetch_page("https://recipes.test/big")
    assert refused.value.code == "too_large"


def test_an_error_status_is_reported(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _resolving({"recipes.test": ["93.184.215.14"]}))
    _serve(monkeypatch, {"recipes.test": _Response(404)})
    with pytest.raises(FetchError) as failed:
        fetch_page("https://recipes.test/gone")
    assert failed.value.code == "fetch_failed"
