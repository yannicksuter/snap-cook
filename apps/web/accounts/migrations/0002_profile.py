# SPDX-License-Identifier: AGPL-3.0-or-later
"""Profiles, and the accounts there already are, moved to uids and initials.

Everyone who had an account before had full use of the site, so they keep it:
their profile may cook. Their username becomes their uid, and the old one is
kept as ``former_handle``, the author name their earlier recipe versions carry.
A Google account whose address was never recorded as verified gets it so:
Google verified it, and without it the account would only read from now on.
Accounts a command made (the corpus curator) keep their name and only read.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def forwards(apps, schema_editor) -> None:
    from accounts.identity import initials_for, normalize, uid_for

    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Profile = apps.get_model("accounts", "Profile")
    EmailAddress = apps.get_model("account", "EmailAddress")
    SocialAccount = apps.get_model("socialaccount", "SocialAccount")

    taken: set[str] = set()
    for user in User.objects.order_by("date_joined", "pk"):
        # Signed up through the sign-in library, as a person; the curator and
        # other accounts made by a command never did, and keep their name.
        person = bool(user.email) and (
            EmailAddress.objects.filter(user=user).exists()
            or SocialAccount.objects.filter(user=user).exists()
        )
        email = normalize(user.email or "") if person else ""
        initials = initials_for(email or user.username, taken)
        taken.add(initials)
        former = ""
        if email:
            uid = uid_for(email)
            if user.username != uid:
                former, user.username = user.username, uid
                user.save(update_fields=["username"])
            if (
                not EmailAddress.objects.filter(user=user, verified=True).exists()
                and SocialAccount.objects.filter(user=user, provider="google").exists()
            ):
                EmailAddress.objects.update_or_create(
                    user=user,
                    email=user.email,
                    defaults={"verified": True, "primary": True},
                )
        Profile.objects.create(
            user=user, initials=initials, can_cook=bool(email), former_handle=former
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("account", "0009_emailaddress_unique_primary_email"),
        ("socialaccount", "0006_alter_socialaccount_extra_data"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Profile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("initials", models.CharField(max_length=3, unique=True)),
                ("can_cook", models.BooleanField(default=False)),
                ("former_handle", models.CharField(blank=True, db_index=True, max_length=150)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
