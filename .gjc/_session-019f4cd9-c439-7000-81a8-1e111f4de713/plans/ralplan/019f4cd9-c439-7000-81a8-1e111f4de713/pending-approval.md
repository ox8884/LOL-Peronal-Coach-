# Pending Approval: ARAM Mayhem Personalized Tips and Reliable Augment Images

## Decision
Adopt a versioned, bundled augment evidence catalog at the latest live patch available during implementation. Advice accepts only manually entered offered augments and generates evidence-backed champion/augment-specific tips. Icon loading uses exact, cataloged Riot-owned candidates first and verified League Wiki candidates second; it never invents URLs.

## Intent Reconciliation
- Catalog baseline: latest live patch at implementation time; display the catalog patch in the UI.
- Cache refresh may react to app startup/patch change, but catalog identity, mechanic, and candidate changes remain reviewed maintainer updates.
- No Riot-client extraction of offered augments; manual entry remains required.

## Implementation Sequence
1. Add packaged `lol_coach.data` resources and `static/augment_catalog.py`: stable augment IDs, Korean/English aliases, mechanics/cautions, ordered exact image candidates, evidence URLs, patch, and update time. Add a maintainer-only checker/refresh script; reconcile every legacy `_FALLBACK`, `AUGMENT_INFO`, and archetype name before migration.
2. Add `static/augment_icons.py`: decoded >=128px raw-image validation, Riot-first/Wiki-fallback candidate order, atomic v2 index/raw cache, last-known-good state, and missing-card state. Preserve but do not trust or delete legacy thumbnails.
3. Extend `static/ddragon.py` with cached full champion-detail/ability facts. Refactor `analysis/aram_mayhem.py` so `advise(champion, offered_augments)` resolves only entered offers, produces structured evidence/source records, and rejects unsupported filler. Enforce 3–5 tips, >=2 named champion operation references, >=1 offered augment synergy/caution reference, and no unoffered result.
4. Update `gui/app.py`: add manual offered-augment input with catalog suggestions; validate before worker dispatch; retain live autofill for champion only; display compared offered choices, structured tips, source URL/patch/update data, cached/stale icons, and name+rarity cards only for missing cache. All download/decode/index work remains off the Tk thread.
5. Update `pyproject.toml`, `lol_coach.spec`, `README.md`, and `BUILD.md` for package resources, PyInstaller parity, cache policy, and maintainer workflow.

## Exact Change Areas
- New: `src/lol_coach/static/augment_catalog.py`, `src/lol_coach/static/augment_icons.py`, `src/lol_coach/data/__init__.py`, `src/lol_coach/data/aram_mayhem_augments.json`, `scripts/refresh_aram_mayhem_data.py`, `tests/test_augment_catalog.py`, `tests/test_aram_mayhem.py`.
- Modify: `src/lol_coach/analysis/aram_mayhem.py`, `src/lol_coach/static/ddragon.py`, `src/lol_coach/static/icons.py`, `src/lol_coach/gui/app.py`, `tests/test_icons.py`, `tests/test_gui_threading.py`, `tests/test_packaging.py`, `pyproject.toml`, `lol_coach.spec`, `README.md`, `BUILD.md`.

## Acceptance Criteria
- Only normalized, unique entered augment IDs are compared; empty/unknown input blocks with suggestions.
- Each successful result has 3–5 tips: >=2 champion skill/operation references and >=1 named entered augment synergy/caution; source and patch/update time are visible.
- Every actual icon originates from a decoded >=128×128 source; no guessed URLs.
- Riot candidates precede validated Wiki candidates; verified cache survives offline/download failure; no cache renders an explicit name+rarity card.
- Startup/patch refresh performs no network, image decode, hashing, or index writes on Tk’s thread.
- Editable and one-file builds read the same catalog while user cache stays writable outside the bundle.

## Verification
- Focused: `tests/test_augment_catalog.py`, `tests/test_aram_mayhem.py`, `tests/test_icons.py`, `tests/test_gui_threading.py`, and `tests/test_packaging.py`.
- Run the maintainer catalog checker for the approved live patch.
- Manual scenarios: fresh online cache, warm offline cache, empty offline cache, patch transition, unknown/duplicate input, and live champion autofill.
- Build the executable with `powershell -ExecutionPolicy Bypass -File scripts/build_exe.ps1` after focused checks pass.

## ADR-001
- **Drivers:** offered-choice fidelity, verifiable evidence/freshness, image integrity, offline continuity, Tk responsiveness, and packaged parity.
- **Chosen:** versioned evidence catalog + deterministic advice invariants + atomic last-known-good raw cache.
- **Alternatives rejected:** runtime U.GG/Wiki scraping, expanding URL-slug heuristics, and external/LLM-generated advice; each fails determinism, provenance, offline reliability, or scope constraints.
- **Consequences:** catalog review is release work; champion evidence must remain conservative; legacy thumbnails remain untouched but are not verified sources.

## Status
Pending explicit execution approval.
