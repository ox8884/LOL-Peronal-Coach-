## Summary
The planner artifact is architecture-sound against the approved ARAM Mayhem specification: it replaces champion-only/global-tier advice with manual offered-augment input, source-attributed structured tips, and a verified Riot-first/Wiki-fallback image/cache contract. No product code was edited and no tests were run per the read-only assignment. Main execution risks are catalog completeness and honest champion-operation evidence, and the plan already gates both before completion.

## Claims
- The approved spec requires manual entry/selection of current offered augments, Riot official data/patch notes first, U.GG and League Wiki only as verified auxiliary sources, Riot-first/Wiki-fallback image collection, background refresh on startup/patch change, last verified cache offline, and name/rarity fallback only when no cache exists (`.gjc/_session-019f4cd9-c439-7000-81a8-1e111f4de713/specs/deep-interview-aram-mayhem-tips-and-augment-images.md:39-60`).
- Current advice is structurally unable to satisfy offered-choice fidelity: `MayhemCoach.advise` takes only `champion`, scores broad U.GG/fallback tier names with archetype lists, and returns global top/avoid picks (`src/lol_coach/analysis/aram_mayhem.py:489-557`). Current tips are role-tag strings from `_play_tips`, not evidence-backed champion/entered-augment tips (`src/lol_coach/analysis/aram_mayhem.py:592-605`, `src/lol_coach/analysis/aram_mayhem.py:624-657`).
- Current GUI collects only a champion for ARAM, auto-live fill immediately calls `_run_aram`, and rendering presents global Top 5/avoid sections while importing `augment_ctk` from the generic icon module (`src/lol_coach/gui/app.py:554-580`, `src/lol_coach/gui/app.py:854-956`, `src/lol_coach/gui/app.py:970-1078`).
- Current augment icon code guesses League Wiki slugs/URLs, can download during worker rendering, writes size-specific `a_{key}_{size}.jpg` display thumbnails, and falls back to a one-letter placeholder without exposing verified/stale/missing state (`src/lol_coach/static/icons.py:293-410`, `src/lol_coach/static/icons.py:496-510`).
- Current Data Dragon support loads the champion summary feed and indexes names/items/runes/spells, but has no full champion detail or ability extraction method for P/Q/W/E/R evidence (`src/lol_coach/static/ddragon.py:30-276`).
- Current packaging has dependencies for `requests` and Pillow but no package-data declaration, while PyInstaller bundles only a root `data/` directory if present (`pyproject.toml:10-20`, `pyproject.toml:26-27`, `lol_coach.spec:38-42`).
- The planner addresses those gaps with a canonical packaged augment catalog, strict source policy, a maintainer checker, Data Dragon champion-detail APIs, offered-only structured advice invariants, a separate v2 raw-image cache, GUI input/render changes, package-data updates, docs, tests, manual scenarios, and explicit risk gates (`stage-01-planner.md:80-183`, `stage-01-planner.md:184-259`).

## Analysis
Stage 1 — Spec compliance: The plan directly maps every approved acceptance item to a design contract. Manual offered-augment entry is explicit, Riot-client offer extraction is out of scope, output is constrained to normalized unique offered IDs, successful advice must contain 3-5 structured tips with two champion references and one offered-augment synergy/caution, sources carry labels/URLs/patch-or-update timestamps, and U.GG classic ARAM evidence is not represented as Mayhem authority (`stage-01-planner.md:19-39`, `stage-01-planner.md:151-183`). For images, the plan removes runtime URL guessing, requires decoded source dimensions >=128x128, tries exact Riot-owned candidates before exact validated Wiki candidates, preserves last-known-good cache on failures, and renders name/rarity cards only when no verified v2 cache exists (`stage-01-planner.md:24-26`, `stage-01-planner.md:119-145`, `stage-01-planner.md:172-179`).

Stage 2 — Architecture: The proposed boundaries are appropriate for a brownfield GUI app. `augment_catalog.py` owns identity, aliases, evidence, source references, and schema validation; `refresh_aram_mayhem_data.py` is maintainer-only and prevents runtime scraping; `DataDragon` supplies champion ability facts; `aram_mayhem.py` becomes deterministic domain logic with return-time invariant validation; `augment_icons.py` owns cache state/refresh; `icons.py` returns to champion/item utilities; `app.py` handles manual input and display only. That separation fixes the current coupling where rendering guesses URLs and hides placeholders behind the same API as real icons.

Stage 3 — Antithesis and synthesis: The risky alternative is to keep expanding embedded dictionaries or scrape U.GG/Wiki at advice time. That would be faster to implement but would not prove all-known augment coverage, image dimensions, source priority, offline last-known-good behavior, or no-main-thread I/O. The selected catalog/cache path has maintenance cost, but it is the only option in the plan that can produce auditable receipts for the approved spec. The plan also correctly anticipates weak spots: absent Riot assets, source disagreement, patch-day staleness, Data Dragon evidence being too thin for some champions, PyInstaller resource duplication, and destroyed-widget callbacks (`stage-01-planner.md:184-259`).

Stage 4 — Code quality/security/performance: The plan avoids new runtime dependencies, keeps network/decode/hash/index I/O off Tk's main thread, rejects non-HTTPS/unsupported source kinds, avoids path traversal in cache recovery, requires atomic raw-file/index replacement, and refuses compatibility aliases that would hide verified/stale/missing icon state. The proposed test matrix covers normal, boundary, and failure paths for catalog normalization, advice invariants, cache corruption, offline behavior, GUI threading, and packaged resources.

## Root Cause
The current design has no domain object for offered augments or source provenance, and it conflates UI rendering with best-effort Wiki URL generation and thumbnail caching. As a result, it can only produce global, role-tag advice and visually plausible placeholders, not source-stamped individualized tips or verified real icons. The plan fixes the root cause by introducing explicit catalog/evidence/cache contracts before GUI integration.

## Findings
No reportable issues found. No `report_finding` entries were emitted.

## Recommendations
1. Approve the plan as the implementation contract; keep step 1 as a hard gate: approved patch baseline, exact Riot patch-note URLs, zero unresolved legacy names, and reviewable source classification.
2. Do not weaken the advice invariant during execution. If Data Dragon/U.GG evidence cannot honestly support two champion-specific operations for more than a small bounded subset, follow the plan's gate and add a reviewed per-champion rule resource rather than emitting generic filler.
3. Preserve one canonical packaged catalog path under `lol_coach.data` and one writable v2 cache path; do not reintroduce root `data/` duplication or legacy thumbnail promotion.
4. Treat U.GG as secondary classic-ARAM evidence only when freshness is known or explicitly displayed as unknown; never synthesize a patch label.
5. Close implementation only with the specified pytest receipts, catalog checker report, online/offline/manual notes, and one-file resource-load smoke evidence.

## Architectural Status
CLEAR

## Code Review Recommendation
APPROVE

## Tradeoffs
| Option | Strength | Weakness | Verdict |
|---|---|---|---|
| Bundled versioned catalog + v2 LKG cache | Auditable source/freshness, offline continuity, no runtime URL guessing, packageable | Maintainer catalog review cost | Selected; satisfies spec |
| Runtime U.GG/Wiki scraping | Less bundled data | Cloudflare/page drift, latency, weak provenance/offline story | Reject |
| Expand embedded dictionaries/slug rules | Smallest code delta | Repeats current unverified completeness/resolution failures | Reject |
| External/LLM advice | Flexible prose | Privacy/cost/nondeterminism/citation verification outside spec | Reject |
