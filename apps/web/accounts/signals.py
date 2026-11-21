# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every account gets a profile the moment it exists, and the site its name."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from accounts.identity import initials_for
from accounts.models import Profile


@receiver(post_save, sender=get_user_model())
def give_a_profile(sender, instance, created: bool, **kwargs) -> None:
    if not created or Profile.objects.filter(user=instance).exists():
        return
    for _attempt in range(5):
        taken = set(Profile.objects.values_list("initials", flat=True))
        try:
            with transaction.atomic():
                Profile.objects.create(
                    user=instance, initials=initials_for(instance.email or instance.username, taken)
                )
            return
        except IntegrityError:
            continue  # someone else took those initials a moment ago


def name_the_site(**kwargs) -> None:
    """The name and host the sign-in library puts into its mails.

    From the settings on every start (the entrypoint migrates each time), so a
    changed host name reaches the mails without anyone editing the database.
    """
    from django.contrib.sites.models import Site

    Site.objects.update_or_create(
        pk=settings.SITE_ID,
        defaults={"name": "snap-cook", "domain": settings.SNAPCOOK_PUBLIC_HOST},
    )


post_migrate.connect(name_the_site, dispatch_uid="accounts.name_the_site")
