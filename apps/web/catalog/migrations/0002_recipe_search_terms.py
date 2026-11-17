# SPDX-License-Identifier: AGPL-3.0-or-later
"""Search by ingredient: a column of search terms, filled for existing recipes.

The column is derived from the store like every catalog field, so ``reindex``
would fill it too. The migration does it here so an update needs no extra step:
each recipe's HEAD is read once. A recipe the store cannot give is skipped,
which leaves it findable by title only until the next reindex reports why.
"""

from django.db import migrations, models


def fill(apps, schema_editor):
    from django.conf import settings

    from snapcook_core.search import search_terms
    from snapcook_core.store import FilesystemStore

    recipes = apps.get_model("catalog", "Recipe")
    store = FilesystemStore(settings.SNAPCOOK_STORE_DIR)
    for row in recipes.objects.only("pk", "recipe_id").iterator():
        try:
            head = store.head(row.recipe_id)
        except Exception:  # noqa: BLE001 - a broken entry must not stop the update
            continue
        if head is not None:
            terms = "\n".join(search_terms(head.recipe))
            recipes.objects.filter(pk=row.pk).update(search_terms=terms)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="recipe",
            name="search_terms",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "What a search finds the recipe by beyond its title: every ingredient's "
                    "name and the title in every language known, one per line "
                    "(snapcook_core.search)."
                ),
            ),
        ),
        migrations.RunPython(fill, migrations.RunPython.noop),
    ]
