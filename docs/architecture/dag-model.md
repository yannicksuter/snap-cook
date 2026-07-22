# The recipe graph

Nodes are **food-states**. Edges are **actions**.

```
flour ──┐
        ├─[mix, 3 min]──→ "the dough" ──[rest, 1 h @ 4 °C]──→ "rested dough"
water ──┘
```

A food-state is named and referenceable — "the dough", "the roux". An action
consumes one or more inputs and produces exactly one output state, carrying
verb, duration, temperature and tools as **attributes**.

## Why not the full academic ontology

The Kyoto recipe-flow-graph corpus defines 8 node types and 13 edge labels. It
is a rigorous model and we borrow one idea from it — food equivalence, so that
"the mixture" and "it" resolve to a prior node — but adopting it wholesale would
be a mistake here.

It is an **annotation schema for NLP research**, not an authoring schema.
Promoting durations and tools to graph nodes makes every renderer and the editor
substantially harder, in exchange for fidelity a cooking application does not
need.

Accepted limitation: states like "until golden brown" are action attributes
rather than first-class queryable nodes.

## Validation

Enforced at construction, so an invalid graph can never be hashed:

- every input reference resolves to an existing ingredient or food-state
- output state ids are unique across actions (one action produces one state)
- the graph is acyclic
- exactly one terminal state, or all terminals declared as outputs
- unused ingredients produce a **warning**, not an error

## Linear recipes

A step list where each action consumes the previous action's output is a
**degenerate DAG**. It needs no special case, and the authoring syntax requires
no extra markup for it — which matters, because most recipes are linear and the
model must not tax them for the sake of the ones that are not.
