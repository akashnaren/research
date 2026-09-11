# Paper 1 research notes (agent-native UI / MiniShop C1-C4)

Working notes for the next units. Not a paper. Claims and numbers below are
only those already in `paper.md` and `research-plan.md`. Nothing here is a new
result.

## Current claim

On MiniShop with `gemini-2.5-flash` (N=5, temperature 0, ten frozen tasks),
human-surface conditions (screenshot C1, accessibility tree C2) are dominated
on cost and success. Among matched-grain structured conditions, flat tools
(C3) is Pareto-preferred over the view document (C4) on tokens and success;
C4 saves steps. H2 (C4 dominates) is not supported on this model and app. RQ3
is untested.

## Evidence (already collected)

- Protocol: `PROTOCOL.md` (frozen). Harness: `dualsurface/minishop/`.
- Model-free observation-cost baseline (`harness/obs_cost.py`): C1 ~1105, C3
  ~512, C4 ~453 observation tokens per step on the minimal path.
- Oracle control: C3 and C4 reach 100% with a scripted perfect agent.
- First model, N=5 (`gemini-2.5-flash` via Vertex): C1 30% [18, 42] at ~46k
  median input tokens; C2 72% [60, 84] with 0.198 illegal/step and 0.116
  malformed/step; C3 100% at ~3,134 tokens; C4 92% [84, 98] at ~4,455 tokens
  and 6 median steps. Paired C4 minus C3 on success tasks: success −0.114
  (CI includes 0); input tokens +1,404 (CI excludes 0); steps −1.17 (CI excludes
  0). C4's success gap is t10: the model ignored `enabled: false` on
  `set_address` while still on the product view. Surface and backend agree
  (`tests/test_surface_consistency.py`).
- Scripted non-model sanity: `python -m harness.scripted` must be 20/20 before
  any model call.
- Generated tables and figures live in `dualsurface/minishop/report/`
  (gitignored). Pointers: [`results.md`](results.md).
- Scholarly positioning (verified sources only): `research-plan.md` and
  `paper.md` Section 3. No new citations in this note.

Gaps: one model; no C4 constraint-pruning ablation; latency not instrumented;
one synthetic app; 10-task power; C4 hand-authored.

## Ranked next units

1. **Second general model, N=5 (RQ3).** Repeat the 4×10×5 sweep on one more
   general checkpoint that can do C1-C4 in one API (Vertex alias `sonnet` or
   `grok-fast` once enabled). Especially: does that model obey `enabled: false`
   on t10? No model mix across conditions. Do not pool models.
2. **C4 constraint-pruning ablation.** Strip `enabled` flags and argument enums
   from the C4 document (keep view and entities). Measures compactness versus
   constraint-carrying. PROTOCOL change first, then code.
3. **Related work (writing).** Venue-format the verified list; keep the honest
   "what this is not" list. Do not add un-checked citations.
4. **Paper 2 AX later.** Package tokens, steps, success, illegal actions,
   ignored-affordance, and latency as an Agent Experience suite. Not this
   paper. Individual metrics are not new.

Also later, not this unit: latency instrumentation; specialized computer-use
models as a final check; a second application; compiled or model-extracted C4
versus the hand-authored upper bound. No Temporal. No arXiv submit. No
expensive multi-model sweeps in the current unit.

## Akash versus auto-advance

**Needs Akash**

- Vertex Model Garden enablement and spend approval for a second-model N=5
  (200 runs). Credentials stay in `.env`, never committed.
- Confirm which second model (`sonnet` vs `grok-fast`) and whether C1 is
  dropped if that model lacks vision.
- Approve the C4 ablation PROTOCOL wording before it is frozen.
- Paper 2 AX: greenlight when Paper 1's general-model table is stable.
- Any new citation that is not already in `research-plan.md` "Key references
  (verified)".
- GitHub Pages content on https://akashnaren.github.io/research/ (Profile
  Engineer owns that site).

**Auto-advance (no new model spend)**

- Keep Paper 1 prose scholarly and readable. Ban dash punctuation in prose.
- Keep `web/article.md` in sync with `paper.md` via `build.py`.
- Harness tests, scripted 20/20, surface-consistency, report unit tests.
- Implement the C4 ablation *flag* once PROTOCOL is updated (the paid run
  still needs Akash).
- Related-work formatting from the verified list only.

## Web export

Profile ingest path: `papers/agent-native-ui/web/article.md` (Medium-like
reader: title, dek, byline placeholder, figure paths). Scholarly source:
`paper.md`. `build.py` rebuilds HTML/PDF and does not overwrite `article.md`.
Do not open PRs on `akashnaren.github.io`.
