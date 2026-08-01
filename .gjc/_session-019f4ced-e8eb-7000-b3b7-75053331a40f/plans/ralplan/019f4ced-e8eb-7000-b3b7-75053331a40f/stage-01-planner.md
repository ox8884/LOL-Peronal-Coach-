# Implementation Plan — ARAM Mayhem Personalized Tips and Reliable Augment Images

**Status:** Proposed / pending approval. This plan does not authorize product changes until consensus and approval are recorded.

## Summary

Replace the current role-tag/global-tier ARAM Mayhem advice with a deterministic, source-attributed path that accepts the augment names the user is actually being offered, ranks only those inputs, and emits 3–5 actionable tips. At least two tips will name the champion's real abilities or champion-specific operation, and at least one will name an entered augment with a concrete synergy or caution. Replace guessed Wiki image URLs and size-specific lossy caches with a versioned augment catalog, verified source candidates, full-resolution raw caching, background conditional refresh, and an explicit name/rarity fallback card only when no verified cache exists.

The implementation should preserve the existing worker-thread boundary in `CoachApp._run_aram`, keep Riot data and patch notes authoritative, use U.GG and League Wiki only as attributed/validated fallbacks, and avoid adding a new runtime dependency.

## Intent Diff

### Current behavior (inspected)
- `src/lol_coach/analysis/aram_mayhem.py::MayhemCoach.advise(champion)` takes only a champion. It scores a broad U.GG article/frozen `_FALLBACK` catalog using Data Dragon role tags, and `_play_tips` emits generic role text.
- `src/lol_coach/gui/app.py::CoachApp._build_aram` has only a champion field; `_run_aram` cannot pass current offerings; `_render_aram` displays global Top 5/avoid lists and a single combined source footer.
- `src/lol_coach/static/icons.py::augment_pil` constructs multiple guessed League Wiki paths, stores a 36/40 px JPEG as the durable cache, and returns a one-letter image placeholder indistinguishable from an icon result at the API boundary.
- `CoachApp._boot` and `_run_aram` already execute network work on daemon threads, and `tests/test_gui_threading.py` protects part of that boundary.
- `lol_coach.spec` bundles root `data/` when present, but setuptools package data is not configured; root `data/` is currently empty.

### Target behavior
- The user manually enters/selects one or more currently offered augment names; the client never reads augment choices from the Riot client.
- Advice ranks and comments on exactly the normalized, unique input set—never an unoffered augment—and returns 3–5 structured tips satisfying the skill/operation and augment-reference invariants.
- Every displayed claim carries source provenance; the ARAM result shows catalog/build patch and refresh/as-of time without representing classic ARAM U.GG data as Mayhem-only data.
- Every known catalog augment has a stable ID and verified image candidates. Riot-hosted assets are tried first when published; exact, pre-verified League Wiki files are the only image fallback. No URL guessing occurs at runtime.
- Durable cache entries contain the verified source image (both dimensions at least 128 px), not only a display thumbnail. Refresh is background-only and atomic; offline failure preserves and serves the last verified file.

## RALPLAN-DR Decision Drivers

- **DR-1 — User-choice fidelity:** recommendations MUST be a comparison of only the names the user entered as currently offered.
- **DR-2 — Advice contract:** every successful result MUST contain 3–5 tips, at least two champion skill/operation references, and at least one entered-augment synergy or caution.
- **DR-3 — Evidence hierarchy:** Riot Data Dragon and Riot patch notes are authoritative; U.GG and League Wiki are attributed, validated fallbacks rather than silently equivalent sources.
- **DR-4 — Honest freshness:** every source snapshot exposes its patch and/or `updated_at`; unknown freshness is displayed as unknown, never synthesized as a patch string such as the current `"u.gg"` fallback.
- **DR-5 — Image integrity:** acceptance is based on decoded dimensions and source provenance, not filename or URL claims; source images MUST be at least 128×128.
- **DR-6 — Offline continuity:** a failed revalidation MUST NOT replace or delete the last verified cache entry.
- **DR-7 — UI responsiveness:** network, decode validation, hashing, and catalog refresh MUST NOT run on Tk's main thread.
- **DR-8 — Packaged parity:** resource lookup and writable cache location MUST work in editable installs and the PyInstaller one-file app.
- **DR-9 — Conservative migration:** old 36/40 px JPEG augment files cannot be promoted to verified raw cache; they may remain untouched but are ignored by the v2 index.
- **DR-10 — Maintainability:** source URLs and mechanics belong in a reviewable manifest with schema validation, not embedded URL heuristics or a second scraper hidden in rendering code.

## Principles

1. **Compare what the user sees.** Normalize aliases, reject unresolved names with suggestions, preserve entered order for ties, and never invent an available choice.
2. **Evidence before prose.** Build tips from structured champion abilities, build priority, and augment mechanics; do not generate unsupported champion-specific claims from broad role tags.
3. **Source type is explicit.** A community mirror is not labeled Riot. A Riot candidate may be absent; in that case the verified Wiki candidate is used and shown as such.
4. **Last-known-good is immutable until replacement is verified.** Download to a temporary file, decode, dimension-check, hash, then atomically replace the indexed entry.
5. **Rendering is read-only.** UI image lookup reads memory/disk cache and returns state; it never performs network I/O.
6. **Fallbacks are visible.** Unknown input, stale/offline cache, Wiki provenance, and no-cache cards are user-observable states rather than silent degradation.

## Options

### Option A — Versioned bundled catalog + official runtime champion detail + background cache (selected)
- Bundle reviewed augment identity/mechanics/provenance records.
- Obtain current champion ability names/descriptions from Riot Data Dragon full champion JSON, then combine them with U.GG skill/build data only when available and labeled.
- Revalidate exact manifest image candidates in a background cache service.
- **Why selected:** deterministic input validation and offline identity, reviewable source evidence, no runtime Wiki scraping, and reliable packaged behavior.

### Option B — Scrape U.GG/Wiki at advice time
- Smaller bundled dataset, but page drift, Cloudflare, missing patch identity, UI latency, and inability to guarantee all-known coverage make this incompatible with DR-3/4/6/7.
- **Rejected.** U.GG remains a build/tier fallback only; League Wiki remains a pre-verified catalog/image fallback.

### Option C — Keep embedded dictionaries and add more champion/tag templates
- Lowest file count, but preserves guessed image URLs, broad role inference, no schema/completeness check, and poor update reviewability.
- **Rejected.** Existing `_FALLBACK`, `AUGMENT_INFO`, `ARCHETYPE_PREFER`, and `ARCHETYPE_AVOID` should be migrated rather than expanded in place.

### Option D — Add an external recommendation/LLM service
- Could create richer prose but adds privacy, availability, cost, nondeterminism, and citation-verification problems.
- **Rejected for this scope.** Advice remains local and deterministic.

## In scope

- Manual offered-augment entry/selection and alias-aware validation.
- Ranking only entered offerings and generating source-backed personalized tips.
- Structured source/patch/as-of presentation.
- A complete, patch-stamped known-augment catalog and maintainer refresh/validation workflow.
- Riot-first/exact-Wiki-fallback image candidates, decoded 128 px minimum validation, atomic cache index, startup/patch refresh, offline last-known-good behavior, and no-cache cards.
- Focused unit, threading, packaging, and manual GUI/offline verification.
- Directly affected README/build/cache documentation.

## Out of scope

- Reading offered augments from League Client, Live Client Data, screenshots, OCR, or process memory.
- Expanding rune or Summoner's Rift coaching.
- Replacing the existing classic ARAM U.GG item-build path, except to label it accurately and expose provenance.
- Shipping downloaded images in the installer; the bundled artifact is metadata/rules only.
- General champion/item icon cache redesign.
- Automatic deletion of legacy `cache/icons/a_*_{size}.jpg` files.

## File-level changes

### 1. Catalog and source models

#### New: `src/lol_coach/static/augment_catalog.py`
Introduce explicit immutable models and loader symbols:
- `SourceRef(kind, label, url, patch, updated_at)` where `kind` is constrained to `riot_data`, `riot_patch_notes`, `ugg`, or `league_wiki`.
- `ImageCandidate(source_kind, url, verified_width, verified_height, verified_sha256, verified_at)`.
- `AugmentRecord(id, name_en, name_ko, aliases, rarity, effect, mechanics, cautions, introduced_patch, source_refs, image_candidates)`.
- `AugmentCatalog(schema_version, catalog_patch, updated_at, records)`.
- `load_augment_catalog()` using `importlib.resources.files("lol_coach.data")`, schema-version rejection, duplicate ID/name/alias detection, HTTPS/source-kind validation, and deterministic normalized indexes.
- `normalize_augment_name`, `AugmentCatalog.resolve`, and `AugmentCatalog.resolve_many`; `resolve_many` deduplicates while preserving first-entry order and returns actionable unknown-name suggestions rather than silently dropping tokens.

Normalization should cover Korean/English aliases, Unicode apostrophes, colon variants, repeated whitespace, and case, reusing one canonical implementation instead of the separate `_norm_aug`/`_norm_augment_name` functions.

#### New: `src/lol_coach/data/__init__.py`
Mark bundled data as a resource package.

#### New: `src/lol_coach/data/aram_mayhem_augments.json`
Versioned catalog with:
- top-level `schema_version`, `catalog_patch`, `updated_at`, exact Riot patch-note sources, and a documented completeness baseline;
- one stable record for every augment known at that patch, including canonical English/Korean names and aliases, rarity, factual effect summary, normalized mechanic/caution tags, provenance, and ordered image candidates;
- Riot-hosted image candidates first when Riot actually publishes an asset; exact League Wiki file URLs second only after maintainer verification;
- no generated Wiki slug candidates and no U.GG image candidates.

The initial migration must reconcile every name currently in `_FALLBACK`, `AUGMENT_INFO`, and parsed U.GG tiers against the authoritative catalog. Unknown U.GG names are reported for catalog review, not admitted dynamically without provenance.

#### New: `scripts/refresh_aram_mayhem_data.py`
Add a maintainer-only, explicitly invoked refresh/check tool that:
- accepts a target Riot patch and output/check mode;
- compares Riot patch notes/data first, then corroborates unresolved records against U.GG and League Wiki;
- verifies exact image URLs by HTTP success, non-text content, Pillow decode, dimensions ≥128×128, and SHA-256;
- emits deterministic JSON and a missing/changed/source-downgrade report;
- refuses to mark CommunityDragon or another mirror as `riot_*` and refuses records with no evidence or with only sub-128 images.

This script is not invoked at app startup. Runtime startup only revalidates the reviewed candidates already in the shipped catalog.

### 2. Champion evidence and advice generation

#### `src/lol_coach/static/ddragon.py`
Extend `DataDragon` with:
- `champion_detail(champion_id)` to fetch/cache Riot's full `ko_KR/champion/{id}.json` record for the resolved current Data Dragon patch;
- a small structured ability view (key `P/Q/W/E/R`, localized name, factual description, cooldown/range metadata, Riot URL/patch provenance) consumed by Mayhem advice;
- request/session reuse and per-instance caching so one advice run does not refetch details.

Do not infer a skill mechanic unless an explicit Data Dragon field/description supports it. English full detail may be fetched only when needed for stable mechanic matching and must retain the same Riot patch provenance.

#### `src/lol_coach/analysis/aram_mayhem.py`
Refactor exact symbols:
- Change `MayhemCoach.__init__` to receive/load `AugmentCatalog` in addition to existing `UGGClient`/`DataDragon` dependencies.
- Change `MayhemCoach.advise(champion, offered_augments)` so an empty or unresolved offering list is a validation error and every resulting `AugmentPick` carries the canonical `AugmentRecord` ID and source.
- Replace global-catalog scoring in `advise` with stable scoring of only resolved `offered_augments`. Score explicit champion capability ↔ augment mechanic matches; use current U.GG tier/build signals only as attributed secondary evidence and preserve user order for equal scores.
- Ensure `top_augments + avoid_augments` is a partition/subset of the unique input IDs and contains no unoffered ID. Do not force an augment into “avoid” without a concrete mismatch/caution.
- Replace string-only `play_tips` with `AdviceTip(text, kind, champion_refs, augment_ids, sources)` and add `AdviceSource`/freshness fields to `MayhemAdvice` (`catalog_patch`, `generated_at`, and source list). Keep display patch separate from source labels.
- Replace `_play_tips(ko, tags)` with `_build_play_tips(champion_detail, offered, scored, build)` that deterministically returns 3–5 tips:
  1. a skill-priority operation naming the actual key and localized skill name (U.GG priority when available, otherwise a conservative operation based on Riot metadata);
  2. a second distinct ability/passive/ultimate operation backed by Riot ability metadata;
  3. at least one tip naming an entered augment and its concrete synergy or caution, tied to the involved ability when supported;
  4. optionally one positioning/resource/timing tip when evidence supports it;
  5. optionally one choice comparison when two entered augments differ meaningfully.
- Add a final invariant validator before returning `MayhemAdvice`; fail with a user-facing evidence/validation error rather than returning fewer than 3 tips or unsupported filler.
- Remove migrated `_FALLBACK`, `AUGMENT_INFO`, `ARCHETYPE_PREFER`, and `ARCHETYPE_AVOID` blocks after all call sites/tests use the catalog. Retain classic ARAM item fallback logic only where unaffected, but label it as fallback evidence.

Safe fallback language may advise tracking a named skill's cooldown/range or holding a named ultimate for the next coordinated fight; it must not assert an unverified interaction. Generic role-tag sentences do not count toward the two champion references.

### 3. Reliable image service

#### New: `src/lol_coach/static/augment_icons.py`
Create a dedicated cache service rather than extending synchronous rendering helpers:
- `AugmentImageState` enum: `verified_cache`, `refreshed`, `stale_cache`, `missing`.
- `AugmentImageResult(record_id, state, path, source, verified_at, width, height)`; `path=None` for `missing` so the GUI can render a real card.
- `AugmentImageCache(catalog, cache_root=None)` with `lookup(record_id)`, `refresh_all(current_patch)`, and `refresh_one(record_id)`.
- Store full verified files under `cache/icons/augments/v2/raw/{stable_id}.{ext}` plus `index.json` containing schema version, catalog patch, URL/source kind, ETag/Last-Modified, dimensions, SHA-256, and verification time. Display resizing happens in memory from the raw file.
- On app startup, conditionally revalidate all records with ETag/Last-Modified; when `index.catalog_patch != catalog.catalog_patch` (or the current Riot patch indicates a shipped catalog change), force candidate re-evaluation. A per-process lock prevents duplicate refreshes.
- For each record, iterate ordered candidates (Riot first, verified Wiki second), download to a sibling temporary file, reject HTTP/text/magic-byte/decode failures and either dimension <128, verify expected hash when provided, fsync/close, then atomically replace the raw file and index entry.
- If every candidate fails, return the existing verified raw file as `stale_cache`; never truncate/remove it. Return `missing` only if no verified v2 file exists.
- Validate index paths against traversal and recover from a corrupt index by scanning only hash/dimension-valid v2 raw files; do not trust legacy thumbnails as verified originals.

#### `src/lol_coach/static/icons.py`
- Remove `_augment_wiki_slugs`, `_augment_urls`, guessed downloads, and the one-letter augment placeholder path.
- Keep champion/item APIs and reusable `to_ctk`/resize helpers.
- Stop exposing `augment_pil`/`augment_ctk`; `CoachApp` consumes `AugmentImageCache` state explicitly. This avoids a compatibility alias that would hide fallback state.

### 4. GUI input, background work, and rendering

#### `src/lol_coach/gui/app.py`
Update exact symbols:
- In `CoachApp.__init__`, load one `AugmentCatalog`, inject it into `MayhemCoach`, and construct one `AugmentImageCache`.
- In `_build_aram`, add a clearly labeled “현재 제시된 증강” manual input below champion selection. Use a multiline/comma-separated entry with alias-aware suggestions/chips from the bundled catalog; show examples and state explicitly that the app does not read Riot client choices. Allow one or more unique entries rather than assuming a fixed server-side offer count.
- Keep `_apply_live_aram` limited to champion autofill; it MUST NOT populate or clear offered augments. If no augment has been entered, live autofill should focus/show the required augment field instead of immediately producing non-personalized advice.
- In `_run_aram`, parse/resolve entries before setting busy state, show all unresolved names and closest canonical suggestions, and call `self.mayhem.advise(key, offered_augments)` inside the existing worker. Prefetch only by calling image-cache refresh methods in that worker; do not call a network-capable icon helper during rendering.
- In `_boot`, after Data Dragon/catalog initialization, call `augment_image_cache.refresh_all(self.dd.version)` on the existing background thread. Send completion/status updates to Tk only through `self.after`; startup remains usable if refresh fails.
- In `_render_aram`, rename Top 5 copy to “입력한 선택지 비교”, show only entered offerings, and show each result's rarity and evidence. Render verified/stale raw images sharply at 40/36 px. For `missing`, render a bordered text card containing canonical name and rarity—never a letter badge presented as an icon. Optionally mark stale cache unobtrusively as “마지막 확인 이미지”.
- Render 3–5 `AdviceTip` objects and a source block listing source label, patch/as-of date, and URL. Distinguish “Riot Data Dragon”, “Riot patch notes”, “U.GG ARAM build fallback”, and “League Wiki validated fallback”; do not collapse them into an unlabeled pipe-delimited string.
- If background refresh replaces an image while the ARAM result is visible, schedule a safe `after` rerender of the current immutable advice; do not mutate widgets from the worker.

### 5. Packaging, docs, and tests

#### `pyproject.toml`
Add package-data configuration for `lol_coach.data/*.json`. No dependency change is expected because `requests` and Pillow already exist.

#### `lol_coach.spec`
Use `collect_data_files("lol_coach")` or an explicit `src/lol_coach/data` mapping so the same `importlib.resources` path exists in the one-file executable. Keep root `data/` handling only if another feature uses it; do not rely on two competing catalog copies.

#### `README.md`
Update the ARAM feature/table and usage text to say:
- champion + manually entered current augment offerings;
- 3–5 source/patch-attributed personalized tips;
- background image refresh and last-verified offline cache;
- no Riot-client augment auto-read.

#### `BUILD.md`
Document packaged catalog resources, `cache/icons/augments/v2`, conditional startup refresh, offline last-known-good behavior, and the maintainer catalog refresh/check command. Clarify that the installer does not prebundle downloaded third-party images.

#### New: `tests/test_aram_mayhem.py`
Focused deterministic tests with mocked Data Dragon/U.GG/catalog evidence:
- Korean/English alias normalization, Unicode punctuation, duplicate removal, and actionable unknown names;
- result IDs are exactly a subset/partition of entered IDs and no global high-tier unoffered augment appears;
- 3–5 tip invariant, two distinct champion ability/operation references, and at least one exact entered augment name with synergy/caution;
- source records expose URL plus patch/as-of and U.GG fallback is labeled as classic ARAM data;
- missing/partial U.GG data still produces only evidence-safe tips or a clear validation error, never generic filler;
- deterministic order on tied scores.

#### New: `tests/test_augment_catalog.py`
- schema/resource loading, unique stable IDs and aliases;
- every known record at the catalog patch has effect/rarity/source evidence and at least one verified ≥128 candidate;
- candidate order is Riot before Wiki when both exist; only allowed source types/HTTPS URLs occur;
- completeness baseline includes all migrated legacy names and no guessed URL-generation path exists.

#### `tests/test_icons.py`
Retain champion/item main-thread tests and replace augment-placeholder expectations with cache-service cases:
- `lookup` never downloads on main thread;
- valid ≥128 image becomes indexed and serves resized display data;
- 127×N, HTML payload, corrupt decode, hash mismatch, and interrupted download never replace last-known-good;
- Riot failure tries exact Wiki fallback;
- total failure returns stale verified cache; only no-cache returns `missing`;
- catalog patch change triggers revalidation; unchanged startup uses conditional headers;
- index and image replacement are atomic/recoverable.

#### `tests/test_gui_threading.py`
Add focused tests that `_boot`/`_run_aram` schedule refresh/network work off the Tk thread, pass normalized offered inputs to `advise`, and make GUI updates via `after`. Assert `_apply_live_aram` does not fabricate or clear offerings.

#### `tests/test_packaging.py`
Assert the augment JSON resources are declared for setuptools/PyInstaller and load through `importlib.resources`; keep existing version/Pillow assertions.

## Sequencing and dependencies

### Stage 0 — Approval/risk gate
1. Review and approve this plan/ADR, catalog maintenance ownership, and the rule that CommunityDragon is not represented as Riot.
2. Record the initial target Riot patch and exact authoritative sources for the first catalog snapshot.
3. Do not begin product mutation before this gate passes.

### Stage 1 — Establish catalog and contracts
1. Add resource package, schema/models/loader, initial complete manifest, and maintainer refresh/check script.
2. Add catalog schema/completeness/provenance tests.
3. Dependency: exact source URLs and initial patch baseline must be reviewable before the cache/advice layers consume them.

### Stage 2 — Build image cache independently
1. Implement v2 full-resolution cache, atomic index, source ordering, revalidation, and stale/missing states.
2. Remove guessed augment URL logic only after equivalent cache tests pass.
3. Dependency: Stage 1 stable IDs and candidates. This stage can be executed by a bounded executor independently of advice once the schema is fixed.

### Stage 3 — Build personalized advice
1. Add Riot full champion detail retrieval and structured ability evidence.
2. Change `MayhemCoach.advise` input/model/scoring and enforce tip/source invariants.
3. Remove migrated embedded augment data after focused advice tests pass.
4. Dependency: Stage 1 catalog mechanics/aliases; independent of Stage 2 cache internals.

### Stage 4 — Integrate GUI/background lifecycle
1. Add offered-augment input and validation.
2. Wire new advice signature and cache service into `__init__`, `_boot`, `_run_aram`, and `_render_aram`.
3. Add source/freshness rendering and explicit stale/missing cards.
4. Dependency: Stages 2 and 3 public contracts finalized.

### Stage 5 — Package, document, and focused verification
1. Configure package/PyInstaller resources and update README/BUILD.
2. Run only the focused test files and manual scenarios below; resolve warnings/failures rather than suppressing them.
3. Obtain final critic review against the spec and ADR before implementation is declared complete.

## Acceptance criteria

- Entering champion `Ahri`/`아리` and a known set such as three canonical/alias augment names produces advice whose compared/recommended/avoid IDs contain no ID outside that entered set.
- A successful advice response contains 3–5 tips; at least two explicitly name distinct Ahri ability keys/names or evidence-backed champion operations, and at least one names one of the entered augments with a concrete synergy/caution.
- Unknown augment text blocks analysis with canonical suggestions; duplicates/alias variants collapse to one choice without changing first-entry tie order.
- The result UI visibly shows source label, URL, and patch or update timestamp for tip/catalog/build evidence; classic ARAM U.GG build evidence is not called Mayhem-specific.
- The shipped catalog passes completeness checks for all augments known at its declared patch and all migrated legacy names.
- Every usable icon is decoded from an actual source whose width and height are each ≥128; display scaling remains sharp at current 40/36 px sizes.
- Candidate resolution attempts a reviewed Riot-hosted candidate before a reviewed Wiki candidate where both exist. No runtime slug guessing or unverified host is used.
- Startup and patch-change image refresh perform no network/decode/hash work on the Tk thread.
- With networking disabled and a verified cache present, the same image renders and is marked last-verified/stale as appropriate. Failed downloads do not damage it.
- With networking disabled and no verified cache, the UI shows a clear card containing augment name and rarity and does not show a fake letter icon.
- Editable install and PyInstaller one-file resource loading both find the same catalog; writable images/index remain under the existing user data cache root.
- Riot-client automatic augment extraction, rune work, and Summoner's Rift coaching remain unchanged.

## Verification

Run after implementation, not during planning, and avoid project-wide commands:

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_aram_mayhem.py -q
python -m pytest tests/test_augment_catalog.py -q
python -m pytest tests/test_icons.py -q
python -m pytest tests/test_gui_threading.py -q
python -m pytest tests/test_packaging.py -q
python scripts/refresh_aram_mayhem_data.py --check --patch <approved-patch>
```

For packaging parity, use the existing targeted build only after unit verification:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

Do not run the installer build unless release packaging is part of the approved execution ticket.

## Escalation/Risk Gate

Stop implementation and return to architect/maintainer review if any of the following occurs:
- Riot does not publish an image for a record and the only available Wiki file is below 128 px or cannot be tied to an exact canonical augment.
- The authoritative sources disagree on identity, rarity, mechanics, or introduced/current patch; do not resolve by silently preferring U.GG.
- The current patch adds/removes/renames augments and a stable-ID migration cannot preserve cache identity.
- More than a small bounded subset of champion ability descriptions cannot support two honest operational references without per-champion curated rules; approve a curated rule resource rather than weakening the acceptance invariant.
- PyInstaller cannot load package resources without duplicating the catalog; choose one canonical bundle path before proceeding.
- Runtime refresh would require scraping or loading pages on the UI thread.

Recommended handoff:
- **Architect:** approve the data contracts, source classification, and ADR before mutation.
- **Critic:** challenge catalog completeness, evidence-safe tip fallbacks, and cache failure transitions after Stages 1–3.
- **Executor:** use separate bounded lanes for (a) catalog/cache and (b) advice models/tests after interfaces are approved; GUI integration follows both.
- **Team/ultragoal:** use only if the initial all-known catalog reconciliation or all-champion evidence audit proves too large for one bounded executor; do not silently reduce coverage.

## Verification Plan

### Automated behavior matrix

| Area | Normal | Boundary | Failure |
|---|---|---|---|
| Input | English/Korean canonical names | whitespace, curly apostrophe, colon, duplicate aliases | unknown name with suggestions; empty list blocked |
| Ranking | 3 offered choices | 1 choice, tied scores | U.GG unavailable; still no unoffered result |
| Tips | ability + matching augment evidence | weakest supported champion metadata | invariant failure is explicit, no generic filler |
| Sources | Riot + matching patch | U.GG/Wiki fallback | unknown date visibly unknown, no fabricated patch |
| Images | Riot candidate ≥128 | Riot absent then Wiki ≥128 | corrupt/127 px/hash mismatch/timeout retain LKG |
| Cache | current catalog/conditional request | catalog patch change | corrupt index/interrupted write/offline |
| GUI | cached image and tips | refresh completion during visible result | no cache card; no Tk worker-thread mutation |
| Packaging | editable resources | frozen one-file resources | writable cache remains outside read-only bundle |

### Manual GUI scenarios
1. Fresh cache: enter a champion and three known offerings; verify only those choices appear, tips/source/freshness satisfy the contract, and first render remains responsive while refresh proceeds.
2. Warm offline cache: disable networking after one successful verification; relaunch and confirm last verified images render without replacement/deletion.
3. Empty offline cache: use a clean cache root with networking disabled; confirm each augment has a readable name+rarity card and analysis remains usable if its non-image evidence is available.
4. Patch transition: seed an older `index.catalog_patch`; start the app and confirm immediate cached/fallback rendering followed by worker refresh and safe UI update.
5. Unknown/duplicate input: enter one typo and two aliases for the same augment; confirm typo suggestions, no analysis until resolved, and one canonical choice after correction.
6. Live autofill: trigger ARAM champion autofill with offerings present and absent; confirm it never reads/fabricates augment choices and prompts for required manual input when absent.

### Evidence to retain in execution handoff
- Focused pytest receipts for the five files.
- Catalog checker report with patch, record count, missing count zero, source-kind counts, and minimum decoded dimensions.
- Manual scenario notes/screenshots for normal, warm-offline, and no-cache card states.
- PyInstaller resource-load smoke result if packaging changes are included.

## ADR-001 — Versioned evidence catalog and last-known-good augment image cache

- **Status:** Proposed; pending consensus/approval.
- **Context:** Current advice has no offered-augment input and relies on broad role tags/U.GG tier data. Current icon code guesses Wiki filenames and saves only display-size JPEGs, so source priority, image resolution, completeness, and offline correctness cannot be proven.
- **Decision:** Adopt a bundled, versioned augment evidence catalog with stable IDs, aliases, factual mechanics, source references, and ordered exact image candidates. Use Riot Data Dragon full champion details as primary runtime champion evidence, Riot patch notes as catalog-change evidence, U.GG only for attributed build/tier fallback, and League Wiki only for validated record/image fallback. Add a dedicated background `AugmentImageCache` that atomically stores and indexes decoded ≥128 px raw sources and serves last-known-good offline. Advice accepts only manually entered offerings and enforces its output invariants before return.
- **Consequences (positive):** deterministic offered-choice behavior; auditable source/freshness; sharp images; robust offline cache; no main-thread network; testable fallback states; stable cache identity across spelling changes.
- **Consequences (costs):** a catalog refresh/review workflow is now release work; package-data handling changes; cache index/schema migration is required; champion evidence extraction needs conservative fallbacks; exact Wiki/Riot provenance must be maintained.
- **Alternatives rejected:** runtime U.GG/Wiki scraping (fragile and network-dependent), expanding embedded dictionaries (not auditable/completeness-safe), and external generated advice (nondeterministic and adds a new trust boundary).
- **Migration:** introduce `augments/v2` alongside legacy cache without deleting user files; ignore legacy thumbnails as verified originals; migrate embedded names into stable catalog IDs; switch all consumers, then remove old URL/data blocks; add one canonical packaged resource path for editable/frozen builds.
- **Revisit when:** Riot exposes a stable official augment API/asset manifest, the catalog update burden becomes unacceptable, or evidence shows two honest champion operations require a reviewed per-champion rules resource.

## Risks and mitigations

- **No official Riot augment icon for some records:** represent absence honestly, use only a verified Wiki fallback, and surface provenance. Never relabel a mirror as Riot.
- **Catalog staleness on patch day:** patch-stamp the catalog, compare against current Data Dragon/Riot patch metadata, display freshness, and fail the maintainer checker on unresolved additions/removals.
- **U.GG data is classic ARAM rather than Mayhem:** label it as such and use it only as secondary build/skill-priority evidence, not proof of Mayhem augment mechanics.
- **Ability text heuristics overclaim mechanics:** require explicit evidence tags, use conservative cooldown/range/ultimate operations, and escalate to a curated per-champion rule resource rather than inventing facts.
- **Cache corruption/concurrent refresh:** one refresh lock, temporary downloads, decoded/hash checks, atomic replace, schema-versioned index, and last-known-good retention.
- **Legacy cache appears valid but is low resolution:** isolate v2 namespace and never migrate 36/40 px JPEGs into the verified index.
- **One-file resource paths differ from development:** use `importlib.resources`, configure both setuptools and PyInstaller, and verify both paths with focused packaging tests/smoke.
- **Background callback touches destroyed widgets:** route updates via `after`, check widget/current-advice identity before rerender, and keep refresh results immutable.
- **Thin/no input:** make offered augments required and actionable; do not fall back to global Top 5 because that violates the approved contract.
