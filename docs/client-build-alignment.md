# Offline WonderBane client-build alignment

The client-build alignment utility compares a reviewed WonderBane executable with a candidate
update without launching, modifying, attaching to, or writing either file. It is a developer
maintenance tool, not a simulator component, bot worker, client patcher, or live runtime service.

The first foundation answers a deliberately bounded question:

> Did this candidate change the PE structure or any byte range currently named by a reviewed
> native-observation profile?

It does not approve a new build automatically. A favorable report produces review evidence that
may later support adding the candidate hash to the existing native-layout compatibility registry.

## Isolation boundary

The package lives under `shadowbane_lab.client_alignment` and does not modify:

- simulator state, actions, effects, timelines, or combat compilation;
- build packages, simulation cases, policies, or group targeting;
- client input, process memory, window management, or worker supervision; or
- the official WonderBane executable and its installation directory.

The only existing runtime data it consumes is the checked-in set of hash-pinned native profile
JSON files and the manually reviewed native-layout compatibility registry.

## Inspect one executable

```powershell
python -m shadowbane_lab.client_alignment inspect `
  'C:\path\to\sb.exe' `
  --pretty
```

The output records SHA-256, file length, PE machine, pointer size, image base, entry point,
alignments, image/header sizes, and each section's layout and SHA-256.

Write a new report file with:

```powershell
python -m shadowbane_lab.client_alignment inspect `
  'C:\path\to\sb.exe' `
  --output .\client-inspection.json `
  --pretty
```

Output creation fails closed when the destination already exists.

## Compare a candidate update

```powershell
python -m shadowbane_lab.client_alignment compare `
  'C:\reviewed\sb.exe' `
  'C:\candidate\sb.exe' `
  --output .\client-alignment.json `
  --pretty
```

By default, the utility inventories the bundled files under
`shadowbane_lab.client_observation.data`. A fixture or separately reviewed profile directory can
be supplied with `--profiles ABSOLUTE_OR_RELATIVE_DIRECTORY`.

The comparison:

1. fingerprints both files;
2. verifies PE and section structure;
3. compares headers, mapped sections, gaps, and overlays;
4. maps changed bytes to RVAs only when section layouts are identical;
5. inventories every applicable profile field named `rva` or ending in `_rva`;
6. gives an attached hexadecimal signature its exact byte length and otherwise uses the profile's
   declared pointer size as a conservative anchor width;
7. reports every changed range intersecting a calibrated anchor; and
8. emits deterministic JSON with an explicit recommendation.

The inputs are reread only. The comparison never opens either path for writing.

## Recommendations

- `exact_build`: both complete file hashes match.
- `incompatible_architecture`: PE machine or pointer size differs.
- `structural_review_required`: section layout changed, so old RVA mapping is not assumed.
- `no_applicable_profiles`: no exact or reviewed-layout-family profile applies to the reference.
- `no_calibrated_anchors`: applicable profiles exist but expose no reviewed RVA anchors.
- `calibrated_anchor_review_required`: at least one changed range touches a reviewed anchor.
- `pe_header_review_required`: sections and anchors remain compatible, but reviewed PE header
  structure changed.
- `candidate_for_reviewed_compatibility`: PE/section layouts match and no calibrated anchor is
  touched. This is evidence for review, not automatic approval.

Only the final state includes `proposed_compatibility_evidence`. It records the two hashes, lengths,
section results, changed-byte/range totals, changed RVA envelope, applicable-profile count, and
anchor count, and always includes `review_required: true`.

## Fail-closed profile handling

Profile discovery is bounded and rejects malformed SHA-256 values, duplicate JSON fields,
non-standard JSON numbers, malformed hexadecimal signatures, invalid RVA values, implausible
pointer sizes, oversized files, and excessive profile counts. Files lacking both `profile_id` and
`executable_sha256` are ignored as non-profile JSON, which excludes registries and unrelated data.

A profile applies only when its executable hash exactly matches the reference or the existing
reviewed compatibility registry places both hashes in one layout family. An unknown reference does
not inherit offsets merely because its PE happens to look similar.

## Validation coverage

Synthetic PE fixtures cover:

- exact PE metadata and section hashing;
- malformed input rejection;
- deterministic CLI JSON;
- an unrelated code change that leaves calibrated anchors untouched;
- a change inside an exact breakpoint signature;
- section-layout movement that invalidates RVA mapping;
- refusal to propose compatibility without applicable profiles;
- reviewed compatibility-family profile reuse;
- nested and named RVA inventory; and
- duplicate profile-field rejection.

The fixture comparison also verifies that both executable input files remain byte-for-byte
unchanged after analysis.

## Deliberate next increments

This foundation does not relocate moved functions or infer changed object fields. Later isolated
branches may add normalized x86 instruction fingerprints, control-flow/call-graph matching, field
access inference, and passive read-only runtime probes. Those results should remain confidence-
scored candidate evidence until manually reviewed and promoted into an immutable build manifest.
