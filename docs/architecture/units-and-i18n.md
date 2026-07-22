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
  They are not stored in translation files.
- Only prose is translated per recipe, in sibling files.
- Each translated string records the hash of its **source** string, so staleness
  is per string — fixing one typo does not invalidate a whole translation.
- A translation must lower to a graph with the same action ids. Translators
  translate text; they cannot alter structure.
