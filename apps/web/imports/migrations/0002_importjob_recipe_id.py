# SPDX-License-Identifier: AGPL-3.0-or-later
"""The recipe a saved import became, by id: a slug changes when the title does.

Deleting a recipe deletes what it was imported from, and finds it by this id.
Imports saved before this column existed get it from their slug, while that
slug still names a recipe.
"""

from django.db import migrations, models


def fill(apps, schema_editor) -> None:
    ImportJob = apps.get_model("imports", "ImportJob")
    Recipe = apps.get_model("catalog", "Recipe")
    ids = dict(Recipe.objects.values_list("slug", "recipe_id"))
    for job in ImportJob.objects.exclude(recipe_slug="").filter(recipe_id=""):
        if job.recipe_slug in ids:
            job.recipe_id = ids[job.recipe_slug]
            job.save(update_fields=["recipe_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("imports", "0001_initial"),
        ("catalog", "0002_recipe_search_terms"),
    ]

    operations = [
        migrations.AddField(
            model_name="importjob",
            name="recipe_id",
            field=models.CharField(
                blank=True,
                db_default="",
                db_index=True,
                help_text="Set once saved; unlike the slug, never changes",
                max_length=40,
            ),
        ),
        migrations.RunPython(fill, migrations.RunPython.noop),
    ]
