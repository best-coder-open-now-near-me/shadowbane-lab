# Normalized rules data

This directory will hold generated, reviewable Reforged rules data.

Each imported record should retain:

- a stable semantic ID;
- the concrete client/wiki name;
- source URL or client provenance;
- extraction timestamp;
- confidence (`confirmed`, `wiki`, `inferred`, `approximated`, `unresolved`);
- the primitive action/effect representation;
- any reviewed override required for exceptional mechanics.

The simulator currently uses the abstract catalog in `src/banesim/catalog.py`. That catalog is a schema and engine stress test, **not a claim about live Reforged balance values**.
