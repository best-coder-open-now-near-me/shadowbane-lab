# Vendor recipe and Inventory contract — September 24

## Evidence and scope

The installed observation baseline is client 1.3.38.11, native 1.8.30 / host
0.3.50, source `8ba181868fca7ca113f94361b61118ce74a9d4a1`.
The prepared executable SHA-256 is
`7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f`;
the reviewed original is
`6347b420c6c151995f168f16fd1624408dd8911698d11a4a74b26d211fb49f19`.
All addresses below are image-relative RVAs or object field offsets, never
runtime addresses or permission to invoke a function directly.

A read-only capture at 2026-09-24 21:15:58 UTC contains three stable recipe-menu
samples. Its private evidence identifier is `snapshot-1790284559590796900.json`,
SHA-256 `87adbc809d434e41b8445c3e7af5ce441dccbd09942b904911f328f047559a3b`.
The private static note is `vendor-menu-contract-20260924.md`, backed by bounded
exact-client inspection. Raw captures, disassembly, character/vendor identities
and process addresses remain private. This source handoff changes no commands,
package or game state.

## Observed ordinary menu contract

All three samples agree on the following state:

| Field | Observed value |
| --- | --- |
| Recipe | Anthame, template `5051080:0` |
| Mode / modification table | `1` (Magic/random) / `16` |
| Prefix and suffix | Both equal random sentinel `3362971591` |
| Quantity / multiple | `1` / false |
| Recipe row | Enabled, visible, selected and matching the activated entry |
| Retained template | Matches the same selected/activated row key |

The owned controls expose these event-zero action prefixes; the next two words
are zero. They are diagnostic prefixes, not complete callable event objects.

| Owned control | Action prefix | Ordinary meaning |
| --- | --- | --- |
| `BTNVIEW` | `0x58C` | Hireling goods Inventory |
| `BTNCREATEITEM` | `0x5A1` | Single-item recipe window |
| `BTNCREATEMULTIPLEITEM` | `0x5A2` | Multiple-slot recipe window |
| `NORMAL` | `0x71C` | Recipe mode 0 |
| `MAGIC` | `0x71D` | Recipe mode 1 |
| `FORMULA` | `0x71E` | Recipe mode 2 |

These six controls were enabled and visible. The first recipe page owns its
nested `ITEMLIST`; it is not a flat direct-child lookup. The page callback has
wrapper type `0x116C2C0`, receiver equal to the current recipe HUD, and target
thunk `0x238AD` resolving to `0x63D1F0`. The sampled selected row and activated
entry agree with the retained template. This validates the observed ownership
and state relationships; a stable snapshot alone does not establish the gesture
or sequence that produced them.

The current queue reader correctly reports `qualified_random_scepter=false` for
this dagger. Do not relabel table 16 as the existing Gilded Scepter/table-12
contract or generalize crafting admission from random-mode similarity. The
separate hireling-roster channel was unavailable while this recipe was open;
these observations do not establish roster completeness or management permission.

## Reviewed static call and lifetime boundaries

- Root `+0xA4` owns the asset manager (`0x1171ADC`); manager `+0x78` owns the
  vendor menu and `+0x384` the selected hireling entry. The management handler
  `0x6C9D70` receives a 0x24-byte event by value. Passing only an action number
  would use the wrong calling contract and omit source-HUD ownership.
- `0x5A1` and `0x5A2` reach `0x6CA5E9`. The ordinary item-producing branch checks
  capability and free capacity, creates `ItemCreation` (`0x116BF7C`), and calls
  `0x63BA10` on that HUD with seven arguments. The final argument determines
  multiple mode. Other service capabilities can take different production paths.
- Recipe HUD `+0x518` owns its pages and `+0x520` identifies the active list.
  Callback `0x63D1F0` processes `0x4CE` through list selection `+0x404`, row payload
  `+0x44C` (`0x116C2D0`) and its template key `+0x10`, then invokes `0x6404D0`.
  The callback is thiscall on the recipe HUD with an event pointer. A highlighted
  row alone is insufficient evidence that the requested recipe became active.
- `0x6404D0` resolves the template, releases the old HUD `+0x408` reference and
  retains the replacement. It refreshes recipe/affix/cost state without invoking
  Create. Never write or cache that retained pointer across visits. Initialization
  can automatically select the first eligible recipe, so window creation alone
  does not verify a requested selection.
- Inventory action `0x58C` reaches `0x6CA444`, checks the selected hireling's goods
  capability, creates/retains `ItemManaging` at manager `+0x7C`, and updates
  manager `+0x58`. Routine `0x6E2920` populates the owned list from the hireling's
  cached item tree; it does not itself send a fresh inventory request. This
  corrects the earlier provisional description of that routine as a request.
  Window presence cannot establish fresh or complete inventory coverage.

## Missing gates and next work

1. Observe the pending user-selected Balanced Dagger switch. Verify a different
   requested row becomes selected and activated, its retained template changes,
   and the complete mode/table/sentinel/quantity/multiple state remains coherent.
   Do not infer its key or treat Anthame's initial selection as this transition.
2. Close the recipe without crafting, then observe Inventory open, close and
   reopen for the same exact building/vendor. Verify manager flags, HUD/list
   ownership and item identities; preserve unavailable/loading states. A populated
   cached list still does not prove complete or fresh inventory.
3. Before admitting a production recipe, qualify that requested recipe and mode
   on its compatible service. Existing Gilded Scepter admission remains template
   `26990:0`, mode 1, table 12 and both random sentinel fields. The dagger sample
   does not replace that contract. Multiple mode is not qualified by merely
   observing its opener control.
4. Only after these gates, implement typed owner-thread open/select/reopen actions
   through ordinary owned controls, with exact process/scene, enabled/visible,
   foreground, lease and pending-operation checks; confirm the intended result
   before continuing. Then integrate saved selection and the durable one-capacity
   run across vendors. Unknown affixes stay kept; disposal and recurring spending
   remain unqualified.

No Create, Keep, Junk, resource transfer or old-job replay is needed for the
remaining menu observations. The [vendor recovery handoff](vendor-recovery-20260923.md)
records the existing job boundaries and the separate provenance fix in draft
[PR #38](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/38).
The provenance code checkpoint `37d919a` passed all 15 hosted checks before this
documentation update; that does not establish gameplay acceptance or installation.
