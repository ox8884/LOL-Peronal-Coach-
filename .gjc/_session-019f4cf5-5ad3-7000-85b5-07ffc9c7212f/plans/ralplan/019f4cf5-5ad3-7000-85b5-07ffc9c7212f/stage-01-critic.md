## Summary
The planner artifact is complete enough to proceed: it directly targets manual offered-augment input, source-stamped individualized tips, Riot-first evidence with U.GG/Wiki fallbacks, verified >=128px augment icons, background refresh, and last-known-good offline cache behavior. I found no blocking gaps in alternatives, risks, acceptance criteria, or concrete verification; the main residual risk is catalog/evidence maintenance, which the plan already gates explicitly.

## Claims
- Current behavior is accurately characterized: `MayhemCoach.advise` currently accepts only `champion`, scores global `_FALLBACK`/archetype lists, and emits generic `_play_tips`; `CoachApp._run_aram` calls `self.mayhem.advise(key)` and `_render_aram` displays global Top 5/avoid lists; `icons.py` currently guesses League Wiki augment URLs and writes size-specific cache files.
- The plan covers the approved specification: manual offered augments only, source-stamped 3–5 tips with two champion-operation references and one offered-augment reference, Riot-first/U.GG-Wiki fallback policy, decoded source-image validation at >=128x128, off-thread refresh, and offline last-known-good behavior.
- The plan includes alternatives and explicitly rejects runtime scraping, expanded embedded dictionaries/URL guessing, and external/LLM-generated advice for reasons aligned with determinism, offline behavior, provenance, and privacy.
- Verification is concrete: focused catalog/advice/icon/threading/packaging tests, maintainer catalog checker, build resource smoke, and manual online/offline/cache-transition scenarios.

## Analysis
Stage 1 — Spec compliance: PASS. Lines 21–27 define the target behavior around manual offers, source/freshness display, no URL invention, off-thread cache refresh, and no fake icon. Lines 110–119 require `MayhemCoach.advise(champion, offered_augments)`, offered-only scoring, structured tips/sources, output invariant validation, and removal of the legacy global data after migration. Lines 131–140 wire the GUI so live Riot lookup only fills champion, offered tokens are resolved before work starts, cache prefetch occurs only in the worker, and rendering uses verified/stale/missing states. Lines 169–178 restate the acceptance criteria in testable terms.

Stage 2 — Architecture: CLEAR. The selected design separates immutable catalog evidence, champion ability evidence, advice scoring, verified raw-image cache, GUI rendering, and package-data wiring. This avoids the current problematic coupling between rendering heuristics and source discovery, and the v2 cache path isolates legacy low-resolution thumbnails without destructive migration. The one canonical `importlib.resources` catalog path plus PyInstaller data collection addresses editable/frozen parity.

Stage 3 — Constructive synthesis: The plan is already broad. The strongest antithesis is that a full all-known augment catalog and two honest champion-operation tips for every champion can become maintenance-heavy if Riot lacks a complete official augment API. The plan handles that risk with a declared patch baseline, source references, checker receipts, and an escalation gate for curated per-champion rules rather than weakening acceptance. Executors should treat those gates as hard stops, not implementation suggestions.

Stage 4 — Quality/security/performance: The proposed cache service has the right safety properties: disk/memory-only lookup, off-thread HTTP/decode/hash/index I/O, ordered exact candidates, magic-byte/Pillow/dimension/hash validation, one process lock, temp-file plus atomic replacement, and stale-cache preservation on failure. The plan avoids adding runtime dependencies and explicitly keeps downloaded images out of installer resources.

## Root Cause
The current defect is architectural: ARAM Mayhem advice and icons are derived from global scraped/fallback lists and guessed display-size image paths, while the UI has no representation of the actual offered choices. The plan repairs the primary contract by introducing offered-choice input, cataloged source evidence, structured advice invariants, and verified image cache state instead of adding fallbacks that would hide the defect.

## Findings
None.

## Recommendations
1. Proceed with implementation using the plan as the controlling contract.
2. Enforce the catalog/evidence gate first: no advice or GUI migration should merge until legacy names reconcile to stable catalog IDs and the checker reports zero missing records for the approved patch.
3. Keep the escalation gates binding: if Data Dragon evidence cannot honestly support two champion operations for more than a small bounded subset, add a reviewed per-champion rule resource instead of generic filler.
4. Retain execution receipts named in the plan: focused pytest results, catalog checker report, manual online/warm-offline/no-cache notes, and one-file resource-load smoke.

## Architectural Status
CLEAR

## Code Review Recommendation
APPROVE

## Tradeoffs
- Bundled evidence catalog: highest determinism/provenance/offline reliability; cost is release-time catalog maintenance.
- Runtime scraping: lower upfront metadata work; rejected due to drift, latency, Cloudflare fragility, and weak offline/source guarantees.
- Expanded embedded dictionaries/slug rules: smallest code movement; rejected because it preserves unverified identity/image/source failure modes.
- External generated advice: flexible prose; rejected due to nondeterminism, privacy/cost/availability, and unverifiable citations.

Verdict: OKAY
