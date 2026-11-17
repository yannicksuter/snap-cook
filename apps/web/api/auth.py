# SPDX-License-Identifier: AGPL-3.0-or-later
"""Authentication for the two API surfaces.

Two very different models, deliberately kept apart:

**Product API** -- per-user Personal Access Tokens, plus session auth so the
HTMX UI can call the same endpoints without a second implementation. Content is
private by default, so the API must always know *who* is asking.

**Ops API** -- a single shared bearer token, or a staff session. It has no user
context because it deliberately ignores ownership: `/ops/api/versions/{hash}`
can read any user's private recipe. That is the point of the surface and the
reason its token is the highest-value secret in the system.
"""

from __future__ import annotations

import hmac
import ipaddress
import logging

from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone
from ninja.security import HttpBearer

from accounts.models import PAT_PREFIX, ApiToken

logger = logging.getLogger(__name__)


class PatAuth(HttpBearer):
    """Authenticate a user by Personal Access Token.

    Lookup is a point query on the indexed ``prefix`` column, then a constant
    time comparison of the hash. Never a table scan, never a plaintext compare.
    """

    def authenticate(self, request: HttpRequest, token: str) -> object | None:
        # snck_pat_<prefix>_<secret>. At most three splits: the secret comes
        # from token_urlsafe, whose alphabet includes "_", so about half of all
        # secrets contain one. The hex prefix never does.
        parts = token.split("_", 3)
        if len(parts) != 4 or f"{parts[0]}_{parts[1]}" != PAT_PREFIX:
            return None

        prefix, secret = parts[2], parts[3]
        candidate = ApiToken.objects.active().filter(prefix=prefix).select_related("user").first()
        if candidate is None:
            return None

        if not hmac.compare_digest(candidate.token_hash, ApiToken.hash_secret(secret)):
            return None

        # Cheap enough at human request rates, and makes stale tokens visible.
        ApiToken.objects.filter(pk=candidate.pk).update(last_used_at=timezone.now())

        request.user = candidate.user
        request.api_token = candidate
        return candidate.user


def _check_ops_token(request: HttpRequest) -> bool:
    """Constant-time comparison against the configured ops token."""
    expected = settings.SNAPCOOK_OPS_API_TOKEN
    if not expected:
        return False

    header = request.headers.get("Authorization", "")
    scheme, _, presented = header.partition(" ")
    if scheme.lower() != "bearer" or not presented:
        return False

    return hmac.compare_digest(expected, presented)


# Headers a reverse proxy or tunnel adds on the way in. Cloudflare's tunnel adds
# CF-Connecting-IP and CF-Ray to every request it carries, and no client can
# take them off, so their presence is proof the request came from outside.
_PROXY_HEADERS = (
    "HTTP_CF_CONNECTING_IP",
    "HTTP_CF_RAY",
    "HTTP_X_FORWARDED_FOR",
    "HTTP_FORWARDED",
    "HTTP_X_REAL_IP",
)


def direct_from_the_lan(request: HttpRequest) -> bool:
    """True for a request that reached the app straight from an address the
    internet cannot route: the LAN, Docker's bridge, a VPN such as Tailscale.

    The ops API's one real safeguard used to be a sentence in the docs: do not
    route it through a public tunnel. On a server whose site *is* behind a
    tunnel, that left switching it on one forgotten proxy rule away from
    publishing every private recipe. Now the app refuses what came through a
    proxy, so the API answers on the LAN or a VPN and nowhere else.
    """
    if any(header in request.META for header in _PROXY_HEADERS):
        return False
    try:
        address = ipaddress.ip_address(request.META.get("REMOTE_ADDR", ""))
    except ValueError:
        return False
    if getattr(address, "ipv4_mapped", None) is not None:
        address = address.ipv4_mapped
    return not address.is_global


def require_ops_access(request: HttpRequest) -> bool:
    """Allow a **staff** web session, else require the ops bearer token.

    Either way, only for a request straight from the LAN or a VPN (see
    :func:`direct_from_the_lan`).

    The ``is_staff`` check is the essential difference from a single-operator
    deployment. Anyone with a Google account can sign in to snap-cook, so a
    bare authenticated session must not confer ops access -- that would hand
    every user the ability to read every other user's private recipes.
    """
    if not direct_from_the_lan(request):
        _log_ops_access(request, actor="proxied", allowed=False)
        return False

    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_staff:
        _log_ops_access(request, actor=f"session:{user.pk}")
        return True

    if _check_ops_token(request):
        _log_ops_access(request, actor="token")
        return True

    _log_ops_access(request, actor="anonymous", allowed=False)
    return False


def _log_ops_access(request: HttpRequest, *, actor: str, allowed: bool = True) -> None:
    """Audit every ops request, granted or refused.

    Refusals are logged too: a burst of them is the signal that the token has
    leaked and needs rotating.
    """
    logger.info(
        "ops-access %s %s actor=%s allowed=%s ip=%s",
        request.method,
        request.path,
        actor,
        allowed,
        request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "?")),
    )
