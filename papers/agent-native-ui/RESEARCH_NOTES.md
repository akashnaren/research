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
- Catalog-size obs-cost sweep (2026-09-16, zero model calls,
  `--catalog-sweep 8,50,500,5000`): C4 median obs/step overtakes C3 at **13
  products**; C4 grows 453 / 992 / 6,767 / 64,517 across 8/50/500/5000 while
  C3 stays flat at 512 (its canonical path never reads the catalog; a real C3
  run pays the growing `list_products` payload once per task, 369 to 294,897
  tokens). The n=8 row reproduces the recorded baseline. Artifact:
  [`results-catalog-obs-cost.md`](results-catalog-obs-cost.md).
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
one synthetic app (server-held view state only; SPA/client-state unmeasured);
10-task power; C4 hand-authored; grader slack (last order only, substring
address, substitution-passable refusals; disclosed in paper Section 4);
prompt guidance differs per condition (disclosed); 8-product catalog embedded
whole in both structured conditions (scale unmeasured).

## Ranked next units

1. **Second general model, N=5 (RQ3).** Repeat the 4×10×5 sweep on one more
   general checkpoint that can do C1-C4 in one API (Vertex alias `sonnet` or
   `grok-fast` once enabled). Especially: does that model obey `enabled: false`
   on t10? No model mix across conditions. Do not pool models.
2. **Grader tightening (hygiene before more models).** Exact-order match,
   full address, substitution-proof refusals. Scripted 20/20 and oracle must
   stay green; then re-run C3/C4 N=5 (~$0.15) to confirm Tables 1-3 do not
   move. Small spend needs an Akash nod.
3. **Prompt-equalization ablation.** Neutral usage guidance for C3 and C4,
   re-run the structured pair N=5 (~$0.15). Tests the coaching confound now
   disclosed in paper Section 4.
4. **C4 constraint-pruning ablation.** Strip `enabled` flags and argument enums
   from the C4 document (keep view and entities). Measures compactness versus
   constraint-carrying. PROTOCOL change first, then code.
5. **Related work (writing).** Venue-format the verified list; keep the honest
   "what this is not" list. Do not add un-checked citations.
6. **Paper 2 AX later.** Package tokens, steps, success, illegal actions,
   ignored-affordance, and latency as an Agent Experience suite. Not this
   paper. Individual metrics are not new.

Done 2026-09-16: catalog-size obs-cost sweep (was unit 3); see the evidence
bullet above and [`results-catalog-obs-cost.md`](results-catalog-obs-cost.md).

Also later, not this unit: latency instrumentation; C4 error-message echo
re-run (paper Section 10); specialized computer-use models as a final check;
a second application, ideally an SPA with client-held view state (paper
Section 8.2); compiled or model-extracted C4 versus the hand-authored upper
bound. No Temporal. No arXiv submit. No expensive multi-model sweeps in the
current unit.

## Akash versus auto-advance

**Needs Akash**

- Vertex Model Garden enablement and spend approval for a second-model N=5
  (200 runs). Credentials stay in `.env`, never committed.
- Confirm which second model (`sonnet` vs `grok-fast`) and whether C1 is
  dropped if that model lacks vision.
- Approve the C4 ablation PROTOCOL wording before it is frozen.
- Nod for the two ~$0.15 structured re-runs: grader re-check (unit 2) and
  prompt ablation (unit 4).
- Paper 2 AX: greenlight when Paper 1's general-model table is stable.
- Any new citation that is not already in `research-plan.md` "Key references
  (verified)".
- GitHub Pages content on https://akashnaren.github.io/research/ (Profile
  Engineer owns that site).

**Auto-advance (no new model spend)**

- Keep Paper 1 prose scholarly and readable. Ban dash punctuation in prose.
- Keep `paper.pdf` current via `build.py` when the manuscript changes.
- Harness tests, scripted 20/20, surface-consistency, report unit tests.
- Implement the C4 ablation *flag* once PROTOCOL is updated (the paid run
  still needs Akash).
- Related-work formatting from the verified list only.

## Web export

Profile ingest path: `papers/agent-native-ui/paper.pdf` (exact PDF).
Editable source: `paper.md`. `build.py` rebuilds `paper.html` and `paper.pdf`.
`web/article.md` is a pointer only. Do not ingest it. The github.io reader is
Profile Engineer’s job. Do not open PRs on `akashnaren.github.io`.
