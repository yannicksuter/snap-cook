# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fetch a recipe page for the worker, and nothing on the server's own network.

Anyone who can sign in can make the worker fetch a URL. Without care that is a
server-side request forgery: a link to ``http://192.168.1.1/`` or to this
server's own ``/ops/api/`` would be fetched from inside the LAN. So:

- only ``http`` and ``https``, on their usual ports;
- every address a host name resolves to must be public, or nothing is fetched;
- the connection goes to the address that was checked, not to a second DNS
  answer that might differ (DNS rebinding);
- every redirect is checked the same way, at most five of them;
- 15 seconds and 3 MB at most.

Standard library only, so the guard is short enough to read in one sitting.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

__all__ = ["FetchError", "Page", "fetch_page"]

MAX_BYTES = 3_000_000
TIMEOUT = 15
MAX_REDIRECTS = 5
# Generic on purpose: a server's requests should not carry anything personal.
USER_AGENT = "snap-cook/0.1 (self-hosted recipe import)"
_PORTS = {"http": 80, "https": 443}
_REDIRECTS = {301, 302, 303, 307, 308}


class FetchError(Exception):
    """A page that could not or must not be fetched. ``code`` is shown to readers."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Page:
    url: str
    """The final URL, after redirects."""
    html: str


def fetch_page(url: str) -> Page:
    """Fetch an HTML page from the public internet."""
    for _ in range(MAX_REDIRECTS + 1):
        parts = urlsplit(url)
        if parts.scheme not in _PORTS or not parts.hostname:
            raise FetchError("not_allowed", f"not an http(s) URL: {url[:200]}")
        port = parts.port or _PORTS[parts.scheme]
        if port != _PORTS[parts.scheme]:
            raise FetchError("not_allowed", f"unusual port {port}")
        address = public_address(parts.hostname, port)
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"

        connection = _connection(parts.scheme, parts.hostname, port, address)
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                },
            )
            response = connection.getresponse()
            if response.status in _REDIRECTS:
                location = response.getheader("Location")
                if not location:
                    raise FetchError("fetch_failed", f"redirect without a location from {url}")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise FetchError("fetch_failed", f"HTTP {response.status} from {url}")
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise FetchError("too_large", f"more than {MAX_BYTES} bytes at {url}")
            charset = response.headers.get_content_charset() or "utf-8"
        except (OSError, http.client.HTTPException) as error:
            raise FetchError("fetch_failed", f"{type(error).__name__} for {url}") from error
        finally:
            connection.close()
        try:
            html = body.decode(charset, errors="replace")
        except LookupError:
            html = body.decode("utf-8", errors="replace")
        return Page(url=url, html=html)
    raise FetchError("fetch_failed", f"more than {MAX_REDIRECTS} redirects")


def public_address(host: str, port: int) -> str:
    """The address to connect to, if every address the host has is public."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as error:
        raise FetchError("fetch_failed", f"cannot resolve {host}") from error
    addresses = [info[4][0] for info in infos]
    if not addresses:
        raise FetchError("fetch_failed", f"cannot resolve {host}")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        mapped = getattr(ip, "ipv4_mapped", None)
        if not (mapped or ip).is_global or ip.is_multicast:
            raise FetchError("not_allowed", f"{host} is not on the public internet")
    return addresses[0]


def _connection(scheme: str, host: str, port: int, address: str) -> http.client.HTTPConnection:
    if scheme == "https":
        return _PinnedHTTPSConnection(host, port, address)
    return _PinnedHTTPConnection(host, port, address)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """Speaks to ``host`` (Host header) at the already-checked ``address``."""

    def __init__(self, host: str, port: int, address: str) -> None:
        super().__init__(host, port, timeout=TIMEOUT)
        self._address = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self._address, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Like the HTTP one, with the certificate checked against ``host``."""

    def __init__(self, host: str, port: int, address: str) -> None:
        self._tls = ssl.create_default_context()
        super().__init__(host, port, timeout=TIMEOUT, context=self._tls)
        self._address = address

    def connect(self) -> None:
        sock = socket.create_connection((self._address, self.port), self.timeout)
        self.sock = self._tls.wrap_socket(sock, server_hostname=self.host)
