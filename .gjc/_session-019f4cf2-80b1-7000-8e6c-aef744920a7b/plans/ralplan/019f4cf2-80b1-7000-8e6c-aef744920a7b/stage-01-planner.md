# Implementation Plan — ARAM Mayhem Personalized Tips and Reliable Augment Images

## Summary

Replace the current champion-role/global-tier ARAM Mayhem path with a deterministic flow that accepts the augment names currently offered to the user, compares only those inputs, and returns 3–5 source-attributed tips. At least two tips must cite the selected champion's real abilities or champion-specific operation, and at least one must name an offered augment with a concrete synergy or caution. Replace guessed League Wiki image URLs and display-size JPEG caches with a patch-stamped augment catalog, reviewed Riot-first/exact-Wiki-fallback image candidates, decoded source-image validation at both dimensions >=128 px, asynchronous refresh, and last-known-good offline behavior.

Preserve the existing worker-thread boundary in `CoachApp._boot` and `CoachApp._run_aram`, keep offered-augment entry manual, and add no runtime dependency: `requests` and Pillow are already declared in `pyproject.toml`.

## Intent Diff

### Inspected current behavior
- `src/lol_coach/analysis/aram_mayhem.py::MayhemCoach.advise(champion)` receives no offered augments. It scores the global U.GG article/frozen `_FALLBACK` lists using `ARCHETYPE_PREFER`/`ARCHETYPE_AVOID`, while `_play_tips` emits generic role-tag text.
- `src/lol_coach/gui/app.py::CoachApp._build_aram` creates only `aram_champ_var`; `_run_aram` calls `self.mayhem.advise(key)`; `_render_aram` presents global Top 5/avoid lists and collapses sources into one footer.
- `src/lol_coach/static/icons.py::_augment_wiki_slugs`, `_augment_urls`, and `augment_pil` guess Wiki paths, persist only size-specific `a_{key}_{size}.jpg` files, and return a one-letter placeholder without exposing whether an actual icon was found.
- `CoachApp._boot` and `_run_aram` already run in daemon workers; `tests/test_gui_threading.py` protects part of this threading contract.
- `src/lol_coach/static/ddragon.py::DataDragon` loads the summary champion feed but not full champion details needed for named P/Q/W/E/R evidence.
- `lol_coach.spec` bundles root `data/` when present, but that directory is empty and `pyproject.toml` has no package-data declaration.

### Target behavior
- The user manually enters/selects one or more currently offered augments; Riot client lookup continues to fill only the champion.
- Advice resolves aliases, deduplicates inputs in first-entry order, rejects unresolved names with suggestions, and never recommends or warns about an unoffered augment.
- Successful advice contains 3–5 structured tips satisfying the two champion-operation and one offered-augment invariants.
- The result shows source labels, URLs, source patch when available, and update/generated timestamps; unknown freshness stays visibly unknown.
- A bundled catalog defines every augment known at its declared patch, stable identity, aliases, mechanics, evidence, and ordered exact image candidates. Runtime code does not invent URLs.
- Cache refresh runs only off the Tk thread, validates actual decoded source images >=128x128, atomically replaces files/index only after verification, and preserves the last verified image on any failure.
- If no verified cache exists, the GUI renders a readable name+rarity card rather than a fake icon.

## RALPLAN-DR Decision Drivers

- **DR-1 — Offered-choice fidelity:** output MUST reference only normalized unique augments the user entered as currently offered.
- **DR-2 — Advice contract:** every successful response MUST contain 3–5 tips, at least two evidence-backed champion skill/operation references, and at least one named offered-augment synergy or caution.
- **DR-3 — Evidence hierarchy:** Riot Data Dragon and exact Riot patch notes are primary; U.GG and League Wiki are attributed fallbacks, never silently treated as equivalent official sources.
- **DR-4 — Honest freshness:** each snapshot exposes patch and/or `updated_at`; code MUST NOT synthesize a patch label such as the current `"u.gg"` fallback.
- **DR-5 — Image integrity:** an icon is usable only after Pillow decode and width >=128 and height >=128; URL/filename claims are insufficient.
- **DR-6 — Offline continuity:** failed refresh/revalidation MUST NOT delete, truncate, or de-index the last verified raw file.
- **DR-7 — Responsiveness:** HTTP, decode, dimension/hash validation, and index writes MUST NOT execute on Tk's main thread.
- **DR-8 — Packaged parity:** one canonical catalog resource path MUST work in editable installs and PyInstaller one-file builds; writable cache remains outside the bundle.
- **DR-9 — Conservative migration:** legacy 36/40 px `a_*_{size}.jpg` thumbnails are not trusted or promoted as verified originals and are not destructively deleted.
- **DR-10 — Reviewability:** identities, mechanics, source URLs, patches, and aliases belong in a versioned validated manifest, not rendering heuristics.

## Options

### Option A — Bundled versioned evidence catalog + official champion detail + background cache (selected)
Use a reviewed catalog for offline identity and mechanics, Riot full champion JSON for ability evidence, U.GG only as labeled secondary build/tier evidence, and exact reviewed image candidates in a dedicated cache service. This is deterministic, auditable, packageable, and satisfies all decision drivers.

### Option B — Scrape U.GG/Wiki at advice time (rejected)
This reduces bundled metadata but introduces Cloudflare/page drift, unbounded latency, weak patch identity, incomplete offline behavior, and runtime source ambiguity.

### Option C — Expand the current embedded dictionaries and URL slug rules (rejected)
This keeps file count low but cannot prove catalog completeness, source provenance, actual resolution, or stable identity and preserves the current failure modes.

### Option D — External/LLM-generated advice (rejected)
This adds privacy, cost, availability, nondeterminism, and citation-verification boundaries not authorized by the specification.

## In scope / out of scope

### In scope
- Manual offered-augment input/selection, normalization, validation, and suggestions.
- Ranking only offered choices and deterministic champion/augment-specific advice.
- Riot-first source policy, explicit patch/as-of presentation, and labeled U.GG/Wiki fallbacks.
- Complete patch-stamped augment catalog plus maintainer refresh/check workflow.
- Verified >=128 px raw-image cache, asynchronous startup/patch refresh, atomic last-known-good behavior, and explicit no-cache cards.
- Focused domain, cache, GUI-threading, resource-packaging tests and manual online/offline checks.
- Directly affected README/BUILD documentation.

### Out of scope
- Riot-client, Live Client Data, screenshot, OCR, or process-memory extraction of augment offers.
- Rune recommendation or Summoner's Rift coaching expansion.
- Replacing the classic ARAM U.GG item-build path beyond truthful source labeling.
- Shipping downloaded images in the installer or redesigning champion/item icon caching.
- Automatic deletion of legacy augment thumbnails.

## File-level changes

### New `src/lol_coach/static/augment_catalog.py`
Add immutable domain/source models and a single normalizer:
- `SourceRef(kind, label, url, patch, updated_at)` with allowed kinds `riot_data`, `riot_patch_notes`, `ugg`, `league_wiki`.
- `ImageCandidate(source_kind, url, verified_width, verified_height, verified_sha256, verified_at)`.
- `AugmentRecord(id, name_en, name_ko, aliases, rarity, effect, mechanics, cautions, introduced_patch, source_refs, image_candidates)`.
- `AugmentCatalog(schema_version, catalog_patch, updated_at, records)`.
- `normalize_augment_name`, `load_augment_catalog`, `AugmentCatalog.resolve`, and `resolve_many`.

The loader uses `importlib.resources.files("lol_coach.data")`, rejects unknown schema versions, duplicate IDs/names/aliases, unsupported source kinds, non-HTTPS URLs, malformed timestamps, sub-128 declared candidates, and nondeterministic records. `resolve_many` handles Korean/English names, case, whitespace, Unicode apostrophes, and colon variants; it deduplicates while preserving first occurrence and reports close canonical suggestions for all unknowns.

### New `src/lol_coach/data/__init__.py` and `src/lol_coach/data/aram_mayhem_augments.json`
Create one canonical packaged resource. The JSON contains `schema_version`, `catalog_patch`, `updated_at`, completeness baseline/source references, and one stable record for every augment known at that patch. Each record has canonical names/aliases, rarity, factual effect, controlled mechanic/caution tags, introduced/current evidence, and ordered image candidates.

**Source policy:**
1. Identity, champion ability facts, and patch changes: Riot Data Dragon and exact Riot patch-note URLs first.
2. Build/skill priority: U.GG only when its patch/as-of is known and labeled as classic ARAM fallback rather than Mayhem authority.
3. Missing augment identity/mechanics and images: exact maintainer-verified League Wiki pages/files only, labeled community fallback.
4. Image candidates: an exact Riot-owned asset first only when Riot actually publishes it; exact Wiki file second. CommunityDragon or another mirror MUST NOT be labeled `riot_*`; U.GG is not an image source.
5. Every catalog update records UTC `updated_at`; no source without evidence is admitted dynamically at runtime.

Initial migration reconciles every name in `_FALLBACK`, `AUGMENT_INFO`, `ARCHETYPE_PREFER`, and `ARCHETYPE_AVOID` against the authoritative snapshot. Names newly observed in U.GG are reported for review and are not silently added.

### New `scripts/refresh_aram_mayhem_data.py`
Add a maintainer-only command with `--patch`, `--check`, and explicit output/update mode. It consults Riot patch notes/data first, uses U.GG/Wiki only to corroborate unresolved records, verifies each exact image candidate by HTTP status/content type, magic bytes, Pillow decode, both dimensions >=128, and SHA-256, and emits deterministic JSON plus additions/removals/renames/source-downgrade/missing-image reports. It refuses unsupported sources and any record without adequate evidence. This script is never run automatically by the app.

### `src/lol_coach/static/ddragon.py`
Extend `DataDragon` with exact symbols:
- `champion_detail(champion_id_or_key)` fetching/caching current-patch `cdn/{version}/data/ko_KR/champion/{id}.json` through the existing session.
- `champion_abilities(champion_id_or_key)` returning structured P/Q/W/E/R key, localized name, factual description, cooldown/range metadata, Riot URL, and Data Dragon patch.
- Per-instance detail caches to avoid duplicate requests; optional same-patch English detail only when stable mechanic matching requires it.

Do not infer a mechanic absent from Riot fields/text. A conservative named cooldown/range/ultimate operation is allowed; unsupported champion-specific claims are not.

### `src/lol_coach/analysis/aram_mayhem.py`
Refactor exact symbols:
- Change `MayhemCoach.__init__` to receive/load `AugmentCatalog`.
- Change `MayhemCoach.advise(champion, offered_augments)`; empty input or any unresolved token is a user-facing validation error.
- Extend `AugmentPick` with canonical record ID and source/evidence.
- Add `AdviceTip(text, kind, champion_refs, augment_ids, sources)` and `AdviceSource`; change `MayhemAdvice.play_tips` to structured tips and add `catalog_patch`, `generated_at`, and explicit sources.
- Score only resolved offered records using explicit champion capability-to-augment mechanic matches. U.GG tier/build signals may adjust scores only as labeled secondary evidence; ties retain user order.
- Ensure displayed recommended/avoid records are a subset/partition of unique entered IDs. Do not classify an offered choice as avoid without a concrete caution/mismatch.
- Replace `_play_tips` with `_build_play_tips(champion_abilities, offered, scored, build)`, producing: a named skill-priority operation; a second distinct named ability/passive/ultimate operation; at least one named offered-augment synergy/caution; and up to two supported positioning/resource/comparison tips.
- Validate before return: 3–5 tips, at least two champion references/operations, at least one offered augment reference, valid sources, and no unoffered IDs. Raise a clear evidence error instead of generic filler.
- After consumers/tests migrate, remove `_FALLBACK`, `AUGMENT_INFO`, `ARCHETYPE_PREFER`, and `ARCHETYPE_AVOID`. Keep unrelated classic ARAM item fallback behavior but identify it as fallback evidence.

### New `src/lol_coach/static/augment_icons.py`
Introduce:
- `AugmentImageState`: `verified_cache`, `refreshed`, `stale_cache`, `missing`.
- `AugmentImageResult(record_id, state, path, source, verified_at, width, height)`; `path=None` for `missing`.
- `AugmentImageCache(catalog, cache_root=None)` with `lookup(record_id)`, `refresh_one(record_id)`, and `refresh_all(current_patch)`.

Use `cache/icons/augments/v2/raw/{stable_id}.{ext}` and atomic `index.json` entries carrying schema/catalog patch, candidate URL/source, ETag, Last-Modified, decoded dimensions, SHA-256, and verification time. `lookup` is disk/memory-only. Refresh uses one process lock, ordered Riot-first then Wiki candidates, conditional requests for an unchanged catalog, and forced candidate reevaluation when catalog/current patch changes. Download to a sibling temporary file, validate content and expected hash/dimensions, close/fsync, atomically replace raw file, then atomically replace index. If every candidate fails, preserve and return existing verified raw data as `stale_cache`; return `missing` only without a verified v2 file. Reject path traversal and recover a corrupt index only from v2 raw files that still pass hash/dimension validation.

### `src/lol_coach/static/icons.py`
Keep champion/item APIs and reusable resize/`to_ctk`. Remove `_augment_wiki_slugs`, `_augment_urls`, guessed network behavior, `augment_pil`, and `augment_ctk` after the GUI migrates. Do not leave a compatibility alias that hides verified/stale/missing state.

### `src/lol_coach/gui/app.py`
Update exact symbols:
- `CoachApp.__init__`: load one `AugmentCatalog`, inject it into `MayhemCoach`, construct one `AugmentImageCache`.
- `_build_aram`: add a labeled “현재 제시된 증강” manual input below the champion field, accepting comma/newline tokens with catalog-backed suggestions/chips; explain that offers are not read from the Riot client.
- `_apply_live_aram`: continue setting only `aram_champ_var`; never populate or clear offered augments. If none are entered, focus/show the required field instead of immediately running generic advice.
- `_run_aram`: resolve all offered tokens before busy state, show unresolved names and suggestions, pass canonical offerings to `self.mayhem.advise(key, offered)` in the existing worker, and prefetch via `AugmentImageCache` only in that worker.
- `_boot`: after Data Dragon/catalog initialization, call `refresh_all(self.dd.version)` in the existing worker; refresh failure is nonfatal and all Tk updates go through `after`.
- `_render_aram`: rename global Top 5 copy to “입력한 선택지 비교”; render only entered choices and evidence. Read cache state without network; resize verified/stale raw images sharply to 40/36 px. For `missing`, render a bordered card containing canonical name and rarity. Mark stale output unobtrusively as last verified.
- `_render_aram`: display 3–5 structured tips and a source block with label, URL, patch/as-of/update time. Distinguish Riot Data Dragon, Riot patch notes, U.GG classic ARAM fallback, and League Wiki validated fallback.
- Keep refresh rerender callbacks through `after`, confirm widget/current-advice identity, and never mutate Tk widgets in a worker.

### `pyproject.toml` and `lol_coach.spec`
- Declare `lol_coach.data/*.json` as package data in setuptools.
- Bundle the same `src/lol_coach/data` resource in PyInstaller using `collect_data_files("lol_coach")` or an exact equivalent.
- Do not create a competing root `data/` catalog copy. No dependency addition is expected.

### `README.md` and `BUILD.md`
Document champion + manual offered-augment usage, source/patch-attributed 3–5 tips, no Riot-client offer extraction, startup/patch background refresh, `cache/icons/augments/v2`, last-known-good offline behavior, maintainer catalog check, and the fact that downloaded images are not installer resources.

### Tests
- New `tests/test_augment_catalog.py`: schema/resource loading, stable-ID/alias uniqueness, normalization/dedup/suggestions, completeness against all migrated names, evidence fields, allowed HTTPS sources, and Riot-before-Wiki candidate order.
- New `tests/test_aram_mayhem.py`: offered-only output, stable tie order, 3–5 tip/two-operation/one-offered-augment invariants, source freshness, U.GG labeling, partial/missing U.GG behavior, and explicit evidence failure instead of unsupported filler.
- Refactor `tests/test_icons.py`: retain champion/item main-thread checks and cover cache lookup no-network, valid >=128 acceptance, 127px/corrupt/HTML/hash/interruption rejection, Riot-to-Wiki fallback, atomic replacement, stale last-known-good, missing-only-without-cache, patch revalidation, and corrupt-index recovery.
- Extend `tests/test_gui_threading.py`: `_boot`/`_run_aram` off-thread refresh, normalized offerings passed to advice, all GUI callbacks via `after`, and `_apply_live_aram` neither fabricating nor clearing offerings.
- Extend `tests/test_packaging.py`: resource declarations and `importlib.resources` loading in normal/frozen-oriented configuration.

## Sequencing and dependencies

1. **Catalog/evidence contract:** choose the initial approved Riot patch baseline and exact Riot patch-note URLs; add schema/models/resource and checker. Gate on zero unresolved legacy names and reviewable source classification.
2. **Image cache lane:** implement v2 service and failure-state tests against frozen catalog IDs/candidates. Only then remove guessed augment image APIs.
3. **Advice lane:** add champion detail evidence, offered-only scoring, structured tip/source models, and invariant tests. This can proceed in parallel with step 2 after step 1 contracts freeze.
4. **GUI integration:** add input and wire `__init__`, `_boot`, `_apply_live_aram`, `_run_aram`, `_render_aram` after advice/cache interfaces stabilize.
5. **Packaging/docs:** establish one resource path, update user/maintainer guidance, and verify focused normal/frozen resource behavior.
6. **Critic/architect closeout:** compare implementation and evidence receipts against the specification and ADR; do not declare completion with catalog gaps or degraded advice invariants.

## Acceptance criteria

- Champion plus known offered names/aliases produces compared/recommended/avoid IDs containing no ID outside the normalized unique input set.
- Empty input and unresolved names block analysis with actionable canonical suggestions; duplicates collapse while retaining first-entry tie order.
- Every successful response contains 3–5 tips, at least two explicit champion-specific skill/operation references, and at least one exact offered augment name with concrete synergy/caution.
- UI shows source label, URL, and patch or update timestamp; unknown freshness is honest, and U.GG classic ARAM evidence is not described as Mayhem-specific.
- The catalog checker proves all augments known at its declared patch and every migrated legacy name are represented with evidence.
- Every displayed actual augment icon derives from a decoded source with width >=128 and height >=128 and is sharply resized only for display.
- Exact Riot-owned candidates are tried before exact validated Wiki candidates. Runtime has no guessed slug/path generation.
- Startup and patch-change refresh perform no HTTP/decode/hash/index I/O on Tk's main thread.
- Offline/download failure with a verified v2 cache displays that same last-known image and does not alter it; without one, the UI shows a readable name+rarity card.
- Editable and one-file builds load the same bundled catalog, while cache writes remain under the existing writable project/user `cache/icons` root.
- Live ARAM autofill changes only the champion; rune/Summoner's Rift behavior is unchanged.

## Verification

Run after implementation (not during planning), without suppressing warnings:

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_augment_catalog.py -q
python -m pytest tests/test_aram_mayhem.py -q
python -m pytest tests/test_icons.py -q
python -m pytest tests/test_gui_threading.py -q
python -m pytest tests/test_packaging.py -q
python scripts/refresh_aram_mayhem_data.py --check --patch <approved-patch>
```

After focused tests pass, verify packaged resource parity with the existing targeted build:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

Do not build the installer unless the execution/release ticket explicitly includes it.

## Escalation/Risk Gate

Stop and return to architect/maintainer review when:
- no exact Riot image exists and the only Wiki asset is ambiguous or below 128 px;
- Riot, U.GG, and Wiki disagree on identity/rarity/mechanics/patch;
- a patch rename/removal cannot preserve stable cache identity;
- more than a small bounded champion subset cannot support two honest operations from Data Dragon/U.GG evidence—approve a reviewed per-champion rule resource instead of weakening acceptance;
- PyInstaller requires duplicate competing catalog copies;
- cache refresh would require scraping or any Tk-thread network work.

Handoff: **Architect** approves catalog/source contracts and ADR; **Executor** may take parallel bounded catalog/cache and advice lanes after contracts freeze, then GUI integration; **Critic** challenges completeness, unsupported tips, and cache failure transitions before closeout; use **team/ultragoal** only if the all-known augment reconciliation or all-champion evidence audit exceeds a bounded executor, never by silently reducing coverage.

## Verification Plan

| Area | Normal | Boundary | Failure |
|---|---|---|---|
| Offered input | Korean/English canonical names | whitespace, curly apostrophe, colon, duplicate alias, one offer | empty/unknown blocked with suggestions |
| Ranking | three offered choices | tied scores preserve input order | U.GG unavailable; no unoffered result |
| Tips | two abilities + matching augment | weakest supported champion metadata | explicit evidence error, no generic filler |
| Sources | Riot current patch | labeled U.GG/Wiki fallback | unknown date visible, no fabricated patch |
| Images | Riot candidate >=128 | Riot absent then Wiki >=128 | corrupt/127px/hash/timeout preserves LKG |
| Cache | current conditional refresh | catalog/patch change | corrupt index/interrupted write/offline |
| GUI | warm cache and tips | refresh completes while visible | no-cache name+rarity card; no Tk worker mutation |
| Packaging | editable resource | one-file resource | writable cache remains outside bundle |

Manual scenarios:
1. Fresh cache/online: enter one champion plus three known offers; verify only those choices, 3–5 compliant tips, visible provenance/freshness, and a responsive first render.
2. Warm cache/offline: seed verified images, disable network, relaunch, and confirm identical last-known images remain available and intact.
3. Empty cache/offline: use a clean cache root and confirm readable name+rarity cards, with no fake one-letter icon.
4. Patch transition: seed an older index catalog patch and confirm immediate cached rendering, worker revalidation, and safe `after` rerender.
5. Unknown/duplicate input: enter a typo plus aliases of one augment; verify suggestions, blocking until correction, then one canonical entry.
6. Live autofill: with offers present/absent, verify only champion autofill and required manual offer behavior.

Execution evidence to retain: five focused pytest receipts, catalog checker report (patch, record count, missing count zero, source-kind counts, minimum dimensions), manual notes/screenshots for normal/warm-offline/no-cache, and one-file resource-load smoke receipt.

## ADR-001 — Versioned evidence catalog and last-known-good augment image cache

- **Status:** Proposed for implementation under the approved feature specification.
- **Context:** Current advice has no offered-augment input and relies on broad role tags/U.GG tier data. Current icon code guesses Wiki filenames and stores only small lossy thumbnails, so source priority, resolution, completeness, freshness, and offline correctness cannot be demonstrated.
- **Decision:** Adopt one bundled, versioned augment evidence catalog with stable IDs, aliases, mechanics, exact source references, and ordered image candidates. Use Riot Data Dragon full champion detail as primary champion evidence and exact Riot patch notes as change evidence; use U.GG only for attributed build/tier fallback and League Wiki only as validated identity/image fallback. Add a background `AugmentImageCache` that atomically stores/indexes verified decoded >=128x128 raw files and serves last-known-good offline. Advice accepts manually entered offerings only and validates its output invariants before return.
- **Positive consequences:** deterministic offered-choice behavior, auditable evidence/freshness, sharp images, offline resilience, no main-thread network, stable cache identity, and explicit fallback states.
- **Costs:** catalog review becomes release work; package-data and cache schema handling are added; conservative champion evidence may require curated follow-up for some champions.
- **Rejected alternatives:** runtime scraping, expanding embedded dictionaries/URL guesses, and external generated advice.
- **Migration:** ship `augments/v2` beside legacy files; never promote or delete legacy thumbnails automatically; reconcile embedded names into stable catalog IDs; switch catalog/advice/GUI consumers; remove old data and URL-generation symbols only after focused tests pass; use exactly one packaged catalog path.
- **Revisit when:** Riot publishes a stable official augment API/asset manifest, catalog maintenance cost becomes unacceptable, or a reviewed per-champion operation resource is required to satisfy evidence honestly.

## Risks and mitigations

- **Official Riot asset absent:** record the absence, use only an exact validated Wiki fallback, and show its provenance; never relabel a mirror as Riot.
- **Patch-day staleness:** stamp the catalog, compare it with current Riot metadata, display freshness, and fail the checker on unresolved additions/removals.
- **U.GG is classic ARAM:** label it explicitly and use it only as secondary build/skill-priority evidence, not Mayhem mechanic authority.
- **Ability heuristics overclaim:** require explicit Riot text/fields, use conservative named operations, and escalate to curated rules rather than fabricate interaction claims.
- **Cache corruption/concurrency:** one refresh lock, temp files, decode/dimension/hash checks, atomic replace, versioned index, and immutable last-known-good on failure.
- **Legacy low-resolution cache:** isolate v2 and ignore old thumbnails as verified sources without deleting user data.
- **One-file resource differences:** use `importlib.resources`, configure both setuptools/PyInstaller, and verify editable plus one-file paths.
- **Destroyed-widget callbacks:** use `after`, immutable results, and current-widget/advice identity checks before rerender.
- **Thin input:** require offered augments and never fall back to global Top 5, because doing so violates the approved contract.
