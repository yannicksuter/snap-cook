# Units and internationalisation

## Volume to mass needs density

`(quantity, ingredient) → quantity`, not a unit conversion. No general unit
library can do it, because 250 g of flour is not 250 ml of flour.

Conversion table (Tandoor's shape, plus prep state):

```
UnitConversion(base_amount, base_unit, converted_amount, converted_unit,
               food_id?, prep_state?)
```

`food_id` null means universal (`ml` to `l`); set means ingredient-specific.
`prep_state` exists because sifted and scooped flour differ by ~20%, which is a
real baking failure and not a rounding detail.

> Conversion across dimensions without a density **raises**. It never guesses
> and never falls back to water at 1.0 g/ml. A wrong density is worse than a
> refusal because it is invisible.

## Pint, with two traps

Built on Pint for its unit registry and contexts.

1. **Offset units.** `20 * ureg.degC` is not 20 °C — Pint refuses arithmetic on
   offset units, correctly. Temperature is therefore a dedicated model, not a
   scalar with a unit, and differences use `delta_degC`.
2. **`non_int_type=Decimal`** must be set at registry construction. Mixing float
   and Decimal quantities raises at runtime, and floats are banned anyway.

## Locale-qualified units

A bare "cup" is ambiguous: US 236.6 ml, metric 250 ml, Japanese 200 ml, UK
284.1 ml. Resolution happens **at authoring time** and is frozen into the
version, so a recipe never silently changes meaning when read elsewhere.

## Scaling

Every quantity carries a policy: `linear`, `invariant`, `manual`, `nonlinear`.

> **Timers never auto-scale.** Doubling a recipe does not double bake time.
> Reduction times scale with surface area, not volume. The default is to leave
> them and warn.

Scaling is a **render-time operation**. Doubling a recipe does not create a
commit.

## Translation

- Ingredient names resolve through the registry at render time, per language.
  They are not stored in translations.
- Prose is translated per recipe, inside the recipe: every `LocalizedText`
  (title, description, the words of a step, notes, what a step makes, pans)
  gains a value per language. Words no registry knows, an ingredient it cannot
  bind or a unit it cannot resolve, go to the recipe's `glossary`, keyed by the
  word as written.
- Each translated string records the hash of its **source** string, so staleness
  is per string: fixing one typo invalidates one translation, and the next run
  redoes only that.
- A translation must lower to a graph with the same action ids and slot
  sequence. Translators translate text; they cannot alter structure. The model
  never sees amounts as text: a step goes out as its prose with numbered slots,
  `Den ⟦1⟧ verrühren`, and a step whose slots come back missing, repeated or
  out of order keeps its source words (`snapcook_core.translating`).
- Oven settings and the words standing in for an amount are closed
  vocabularies, labelled by the renderer in the reader's language. They need no
  translation.

How it runs: opening a recipe in another language starts one run in the worker
(`translations`), and the page says so until the run commits. The run commits a
new version **in the owner's name**, because `reindex` takes the owner from the
latest version's author. A failed run is not retried by reloading the page; the
reader retries. Translating uses the import's model and key, at low effort.

## Interface language

Everything a reader sees around the recipe (headings, buttons, hints) goes
through Django's gettext: `{% translate %}` in templates, `gettext` in Python.
English is the source language. German is the second, and the proof that the
interface is not English by construction.

- **Which language.** A signed-in reader's saved language (the settings page)
  wins, then the browser's `Accept-Language`, then English. `LocaleMiddleware`
  reads the browser; `accounts.middleware.UserLanguageMiddleware` applies the
  saved choice. A regional tag such as `de-CH` falls back to `de`.
- **One setting, two uses.** The same language opens recipes. A recipe page can
  still show one recipe in another language without changing the setting, and
  the link that does it is written in the language it switches to ("Auf Deutsch
  anzeigen"), because that is the one its reader recognises.
- **Catalogues** live in `apps/web/locale/<lang>/LC_MESSAGES/`. The compiled
  `.mo` is committed beside its `.po`, so the image and CI need no gettext
  tools. `apps/web/tests/test_locale_catalogs.py` fails when an entry is
  untranslated or the `.mo` is older than its `.po`.
- **Adding a language**: add it to `LANGUAGES` in `settings.py`, run
  `makemessages -l <code>` and `compilemessages` (commands in `AGENTS.md`),
  translate every entry, and give the renderer's label tables in
  `snapcook_core/render/build.py` (sizes, approximations, oven settings) and the
  translation prompt's `_LANGUAGE_NAMES` an entry for it.

Not localised yet, all in core rather than the web app:

- the plain-text renderer's own headings ("Serves", "Ingredients", "Steps"),
  and its notes about scaling;
- number formatting: German shows `1.5 kg`, not `1,5 kg`;
- plural forms of ingredient names: `6 tomato`, `2 mittlere Zwiebel`;
- the recipe list, which shows each recipe's title in its original language,
  because the catalog projects one title per recipe.
