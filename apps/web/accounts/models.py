# SPDX-License-Identifier: AGPL-3.0-or-later
"""Identity, rendering preferences, and API tokens.

DB-authoritative: none of this is derivable from the recipe store, so it is not
a `catalog` concern and `reindex` must never touch it.
"""

from __future__ import annotations

import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

# Fixed prefixes make tokens greppable, give gitleaks a high-precision rule, and
# let GitHub push-protection match them. They are a security feature, not
# cosmetics.
PAT_PREFIX = "snck_pat"
PREFIX_LENGTH = 8


class UnitSystem(models.TextChoices):
    METRIC = "metric", "Metric"
    US = "us", "US customary"
    IMPERIAL = "imperial", "Imperial"


class UserPreferences(models.Model):
    """How this user wants recipes rendered.

    The whole point of a view-independent model: language and unit system are
    render options, not properties baked into a recipe. Two people read the same
    stored recipe in different languages and different units.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="preferences"
    )
    language = models.CharField(max_length=16, default="en", help_text="BCP-47 tag")
    unit_system = models.CharField(
        max_length=16, choices=UnitSystem.choices, default=UnitSystem.METRIC
    )
    # Disambiguates a bare "cup": US 236.6 ml vs metric 250 ml vs Japanese 200 ml.
    units_locale = models.CharField(max_length=16, default="en-US")

    class Meta:
        verbose_name_plural = "user preferences"

    def __str__(self) -> str:
        return f"{self.user} ({self.language}/{self.unit_system})"


class ApiTokenQuerySet(models.QuerySet["ApiToken"]):
    def active(self) -> ApiTokenQuerySet:
        now = timezone.now()
        return self.filter(revoked_at__isnull=True).exclude(expires_at__lt=now)


class ApiToken(models.Model):
    """A per-user Personal Access Token for the product API.

    A single shared bearer token would be categorically wrong for this surface:
    recipe content is private by default, and a shared token carries no user
    identity, so it cannot scope anything. Every product endpoint needs to know
    *who* is asking.

    The plaintext secret is shown once at creation and never stored.
    """

    class Scope(models.TextChoices):
        RECIPES_READ = "recipes:read", "Read recipes"
        RECIPES_WRITE = "recipes:write", "Write recipes"
        IMPORT_WRITE = "import:write", "Create imports"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_tokens"
    )
    name = models.CharField(max_length=100, help_text="What this token is for")
    # Indexed so lookup is a point query, never a full-table scan over hashes.
    prefix = models.CharField(max_length=PREFIX_LENGTH, db_index=True)
    token_hash = models.CharField(max_length=64)
    scopes = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = ApiTokenQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["prefix", "revoked_at"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.prefix}…)"

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        return self.expires_at is None or self.expires_at > timezone.now()

    @staticmethod
    def hash_secret(secret: str) -> str:
        """Hash a token secret with the server-side pepper.

        A pepper rather than a per-row salt: the lookup is by indexed prefix, so
        a deterministic hash is required to compare. The pepper lives in the
        environment, so a database dump alone does not permit offline
        brute-forcing of tokens.
        """
        pepper = settings.SNAPCOOK_API_TOKEN_PEPPER
        return hashlib.sha256(f"{pepper}{secret}".encode()).hexdigest()

    @classmethod
    def issue(
        cls,
        user: object,
        name: str,
        scopes: list[str] | None = None,
        expires_at: object = None,
    ) -> tuple[ApiToken, str]:
        """Create a token. Returns (row, plaintext) -- plaintext is never stored."""
        prefix = secrets.token_hex(PREFIX_LENGTH // 2)
        secret = secrets.token_urlsafe(32)
        token = cls.objects.create(
            user=user,
            name=name,
            prefix=prefix,
            token_hash=cls.hash_secret(secret),
            scopes=scopes or [cls.Scope.RECIPES_READ],
            expires_at=expires_at,
        )
        return token, f"{PAT_PREFIX}_{prefix}_{secret}"
