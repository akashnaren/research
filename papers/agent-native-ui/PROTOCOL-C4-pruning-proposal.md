# Proposed ablation protocol: constraint-pruned view document (C4a)

**Status: PROPOSED, NOT FROZEN.** This file is a draft for Akash to approve,
amend, or reject. The frozen [`PROTOCOL.md`](PROTOCOL.md) is unchanged and
stays authoritative until approval is given in writing. No harness code, no
ablation flags, and no paid runs exist for this ablation yet. Implementation
follows approval; the paid run additionally needs its own spend approval.

Drafted 2026-09-21 against main `15b4a8d`. Fills ranked unit 4 in
[`RESEARCH_NOTES.md`](RESEARCH_NOTES.md) and the measurement that
`paper.md` Section 6.5 describes as not yet run.

## Claim under test

If the view document (C4) saves steps because it carries validity
constraints, then removing the `enabled` flags and argument enums while
keeping everything else should erase the step savings; if it saves steps
because it compactly restates the current state, the savings should
survive.

The pilot left these two mechanisms entangled (paper Sections 4 and 6.5).
This ablation separates them.

## The new condition

One new condition, the **constraint-pruned view document (C4a)**, written
as method name plus identifier throughout, following the paper's
convention. C4a is byte-for-byte the C4 document minus its constraint
content, defined field by field below. It is an ablation of C4, not a new
surface design.

## Held constant (identical to the frozen protocol)

- MiniShop, its backend, the hidden-state grader, and the frozen task set.
- Temperature 0, step cap 20, memory policy (task text, prior actions,
  current observation).
- The seven state-changing operations at the same grain as C3 and C4.
- The C4 delivery mechanism: document in the prompt, model replies with one
  JSON action. No native tool calling.
- One model per comparison, recorded in run metadata, never mixed, never
  pooled.

## Varied (the document only)

| Document field | View document (C4), frozen | Constraint-pruned (C4a), proposed |
| --- | --- | --- |
| `view` | kept | kept |
| `state` (product_id, selected_size, cart_count, address, order_count) | kept | kept |
| `entities` (products, cart, address, order) | kept | kept |
| `affordances[].id` (all seven, every view) | kept | kept |
| `affordances[].enabled` | true or false from backend state | **removed** |
| `affordances[].input` type, properties, required, additionalProperties | kept | kept |
| `affordances[].input` enum values (in-stock sizes, product ids) | kept | **removed** |

Two mechanical consequences worth stating. First, without `enabled` the
affordance list is identical on every view (all seven actions are always
listed), so C4a still names the current view and its contents but never
says which actions are valid right now. Second, with enums removed, C4a's
argument schemas carry exactly the information grain of the flat tools
(C3) schema (names, argument shapes, required fields), so the comparison
C4a versus flat tools (C3) isolates the value of view identity plus
entities, and C4 versus C4a isolates the value of constraints.

## Enforcement rule

C4a runs with backend-native validation only (the same as flat tools
(C3)): the surface-enforcement layer is off, because it enforces exactly
the constraints the ablation removes, and enforcing rules the document no
longer shows would be incoherent. The backend still rejects every illegal
action, rejections still count as illegal actions per step, and, as in the
pilot's C4 loop, no error text is echoed to the model (the error-feedback
limitation disclosed in the paper applies to C4a identically).

## Prompt deviation (disclosed, unavoidable)

The C4 system prompt block references constraints, so C4a needs its own
block. Proposed rule: copy the C4 block and delete only the sentences that
reference constraint content, specifically "Prefer enabled affordances"
and "Out-of-stock sizes are omitted from enums. Disabled pay/add_to_cart
means preconditions failed." Everything else stays identical, including
the JSON reply format and the done rule. This is a necessary confound of
any constraint ablation and is reported as such; it also interacts with
the separately ranked prompt-equalization unit, and the two can be batched
into one paid run if Akash prefers.

## Dependent variables and analysis (same as the pilot)

Per run: success (refusal tasks scored and reported separately), input and
output tokens, steps, illegal actions per step, malformed replies per
step. Analysis: the pilot's per-condition table plus paired per-task
differences with bootstrap confidence intervals over tasks, for both C4a
minus C4 and C4a minus flat tools (C3). Task t10 is the focal readout: C4
failed it on four of five repeats with the flag present and ignored.

Free pre-step, before any spend and after approval: compute C4a's
model-free per-look cost and its catalog-size scaling with the existing
observation-cost machinery. This separates the token effect of a smaller
document from any behavioral effect, so the paid comparison can be read at
matched semantics rather than matched bytes.

## Sample size, model, and cost

Fifty runs for the new condition: ten tasks by five repeats, matching the
pilot. Primary model: the same recorded checkpoint as the published table
(`gemini-2.5-flash` via Vertex), recorded in run metadata.

- Option A (default, about $0.06): run C4a alone and compare against the
  recorded C3 and C4 cells.
- Option B (about $0.19): re-run C3 and C4 alongside C4a in one batch to
  control provider-side drift since the pilot.

If a second general model is later run for RQ3, C4a repeats there and is
reported per model. No model mixing within a comparison, no pooling.

## Interpretation

- **Constraints carry the value.** C4a loses the step advantage (median
  back near seven) or loses success (premature actions of the t10 kind
  spread to more tasks), and illegal actions per step rise above C4's
  0.016. Reading: the document's worth is telling the model what is valid,
  and compact state restating alone does not pay.
- **Compactness carries the value.** C4a keeps the six-step median and
  C4-level success at a lower token price than C4. Reading: on this store
  the constraints were dead weight for this model, which is consistent
  with the t10 evidence that the model did not read `enabled`.
- **The t10 lens.** If C4a fails t10 at C4's rate, the flag was inert for
  this model. If C4a does worse than C4 broadly, the flags were doing
  quiet work on tasks that never showed a rejection.
- **A null result.** With seven success tasks and five repeats, intervals
  are wide. A difference smaller than about one step or one task will not
  separate from zero. A null means "not distinguishable at this sample
  size," never equivalence.

## Threats to validity

- The prompt necessarily differs by the two deleted sentences.
- Document size and constraint content covary; the free per-look pre-step
  above is the mitigation.
- The rejection layer moves from surface enforcement to backend
  validation; both return the same counted rejection, but where rejections
  originate changes.
- One model, small N, and a tiny store where the measurable step effect is
  a single step at median. The harder-application cell (paper Section 10)
  is where a larger effect is predicted; this ablation is still worth
  running first because it is cheap and directly resolves Section 6.5.

## Approval and freeze procedure

Nothing changes until Akash approves this wording. Upon approval: first,
this protocol is frozen (this file's status line flips and the frozen
[`PROTOCOL.md`](PROTOCOL.md) gains a pointer to it, or the text is folded
in, whichever Akash prefers); second, the document flag, the C4a prompt
block, and tests are implemented in the harness, gated by the scripted and
oracle checks, all free; third, the fifty-run batch waits for separate
spend approval of Option A or B.
