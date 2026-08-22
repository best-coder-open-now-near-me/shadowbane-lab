# Reforged rules ingestion

## Source hierarchy

No single source should be treated as universally authoritative.

Suggested precedence by field:

1. controlled current-client observation or exported runtime data;
2. current client tooltip/cache/configuration data;
3. Reforged-maintained wiki documentation;
4. historical Shadowbane/MagicBane references;
5. explicit approximation.

Each field should retain its own provenance when sources disagree.

## Confidence states

```text
confirmed      reproduced in controlled current-game observation
client         extracted from the installed current client
wiki           taken from Reforged documentation
inferred       derived from related values or mechanics
approximated   intentionally simplified for the playground
unresolved     excluded or represented only as unavailable
```

## Normalized power shape

A future normalized record should contain at least:

```json
{
  "id": "profession.example_power",
  "name": "Example Power",
  "concrete": {
    "client_identifier": null,
    "hotbar_name": "Example Power"
  },
  "provenance": {
    "confidence": "wiki",
    "sources": []
  },
  "availability": {
    "class": null,
    "discipline": null,
    "minimum_level": null,
    "minimum_skill": null
  },
  "costs": [],
  "targeting": {},
  "commitment": {},
  "effects": [],
  "unresolved": []
}
```

## Compiler outcomes

Every record should compile into one of three states:

```text
compiled
compiled_with_override
unresolved
```

An unresolved power must not silently become a generic damage action. Search algorithms are exceptionally good at exploiting accidental assumptions.

## Scraping order

Do not scrape the complete game before the grammar is stable. Use a deliberately diverse vertical sample first:

- direct weapon damage;
- projectile/spell damage;
- healing and resource transfer;
- damage over time;
- stun, silence, snare and immunity;
- stealth/reveal;
- teleport/reposition;
- summon/charm;
- dispel and stack interactions.

Once those compile cleanly, broaden to all classes and disciplines.

## Review artifacts

Importer output should include:

- normalized JSON;
- source snapshot or source locator;
- parse warnings;
- unresolved phrases;
- before/after diff on re-import;
- schema validation result;
- optional controlled-game verification trace.
