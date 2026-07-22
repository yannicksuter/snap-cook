# Backlog

Unscheduled ideas. **Not commitments** — this is a parking lot, and most of it
will never be built. Items graduate to `ROADMAP.md` when they have a milestone.

## Discovery
- Find similar recipes (pgvector embeddings over the structured model, not prose)
- "What can I cook with what's in my fridge?" — needs the ingredient tree
- Substitution suggestions, driven by the ingredient hierarchy

## Rendering
- Kid-friendly mode: larger type, simplified verbs, per-step timers
- Live cooking mode: current step, running timers, screen-wake
- Print: real typographic layout for a bound cookbook (see the open question in ROADMAP)

## Health / fitness
- Nutrition per serving from USDA (`Ingredient.fdc_id` is already the join key)
- Macro targets and diet filters

## Social
- Collections and shared cookbooks
- "Cooked it" reports with photos and deviations — deviations are the interesting
  part, since they are effectively an unforked diff

## Import
- Handwritten recipe card OCR
- Video → structured recipe
- Bulk import of a personal collection

## Technical
- Store garbage collection and packfiles
- Offline-first sync for the mobile client
- Semantic three-way merge of recipe graphs
