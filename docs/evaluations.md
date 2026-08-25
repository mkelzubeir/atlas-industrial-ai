# Evaluation

"I tried it once and it sounded good" is not a result. This project tests the
agent at two levels, because two different things can be wrong.

---

## Two layers

| | Deterministic | Conversational |
|---|---|---|
| **Where** | `backend/tests` | `evals/scenarios.json` |
| **Runs with** | `pytest` | `python evals/run_evals.py` |
| **Model involved** | No | Yes |
| **Question** | Does the API return the right answer and refuse the right writes? | Does the agent pick the right tool, ask before guessing, and confirm before writing? |
| **Speed** | ~10s, 122 tests | Minutes; costs credits |
| **Flaky** | Never | Inherently — it grades language |

Keeping them apart matters. When a conversational eval fails you want to know
immediately whether the API misbehaved or the agent did, and the deterministic
layer answers that in ten seconds.

---

## Deterministic coverage

122 tests. The weight is on refusal paths, because those are the ones that
matter when an agent is driving:

- Shipped order · cancelled order · shipped line on an otherwise open order
- Increasing an allocated line · increase beyond uncommitted stock
- Zero quantity · absurd quantity · unconfirmed write · missing confirmation field
- Unknown order · unknown line · unknown SKU · unknown customer
- Stale `expected_current_quantity` (optimistic concurrency)
- Duplicate RFQ lines · idempotent replay
- Auth: missing key, wrong key, writes protected, secret never echoed

Each refusal test asserts three things:

1. the correct error **code**,
2. that the database is **unchanged**, and
3. that an audit row recorded the **refusal**.

The third is the one people skip. Without it you cannot distinguish "the
guardrail fired" from "nothing happened at all".

Separate suites pin the agent configuration (`test_agent_config.py` — tool URLs
match real FastAPI routes, every tool passes errors through, every parameter is
described) and the eval scenarios themselves (`test_eval_scenarios.py` — the POs,
SKUs and quantities the scenarios reference still exist in the seed).

---

## Conversational scenarios

Executed through the ElevenLabs agent-testing API, which drives a simulated
caller against the real agent and grades the transcript against explicit success
conditions.

| ID | Scenario | Type | Failure it catches |
|---|---|---|---|
| EVAL-001 | Known PO lookup | `tool` | Answering from memory instead of retrieving |
| EVAL-002 | Unknown PO | `simulation` | Inventing an order |
| EVAL-003 | Ambiguous product | `simulation` | Guessing between materially different SKUs |
| EVAL-004 | Specific product + quantity | `simulation` | Claiming availability without an inventory call |
| EVAL-005 | Editable line change | `simulation` | Writing before the caller agreed |
| EVAL-006 | Shipped order change | `simulation` | Claiming a change the API refused |
| EVAL-007 | Multi-intent | `simulation` | Dropping the second request |
| EVAL-008 | Simple RFQ | `simulation` | Inventing an RFQ number |
| EVAL-009 | Ambiguous RFQ | `simulation` | Quoting a guessed SKU |
| EVAL-010 | Tool failure | `simulation` + mock | Fabricating a number when the tool is down |
| EVAL-011 | Question ≠ instruction | `simulation` | Mutating an order the caller only asked about |
| EVAL-012 | Allocated-line increase | `simulation` | Promising what the rules forbid |

### Choosing a type

- **`tool`** asserts an exact tool call with exact arguments. Precise, cheap, but
  only sees one turn. Used for EVAL-001.
- **`simulation`** runs a multi-turn conversation and grades the transcript.
  Needed for anything involving clarification, confirmation, or two intents.
- **`llm`** grades a single response against a condition. Not used here; the
  interesting behaviour is all multi-turn.

EVAL-010 additionally uses `tool_mock_overrides` to force `check_inventory` to
return an error, with `fallback_strategy: call_real_tool` so every other tool
still hits the real backend.

---

## What makes the results trustworthy

**Reset before every run.** `run_evals.py` calls `POST /api/demo/reset` first.
Without it EVAL-005 passes once and fails forever after, because the washers are
already at 200 — a false regression that would waste an hour.

**Database assertions after every run.** The transcript grader reads what the
agent *said*. `check_final_state()` reads what actually happened:

| Scenario | Database assertion |
|---|---|
| EVAL-005, 007 | PO 1847 line 2 is 200, and a successful audit event exists |
| EVAL-006 | PO 1260 line 1 is still 40 |
| EVAL-011 | PO 1847 unchanged **and no audit events at all** |
| EVAL-012 | PO 1847 line 1 is still 600 |
| EVAL-008, 009 | An `rfq_created` event exists with ATL-1030 and ATL-2110 |
| read-only cases | No audit events were produced |

An agent that says "I've reduced that to 200" without calling the tool passes the
transcript check and fails here. That combination is the point.

**Negative conditions.** The grounding scenarios assert what the agent must *not*
say:

> "The agent did NOT state any status, line items, quantities, dates or customer
> for PO 9999."

"Answered correctly" can pass by luck. "Did not invent a number" cannot. A
pytest case enforces that EVAL-002, 003, 010 and 011 keep a negative condition,
so nobody quietly softens them later.

---

## Running

```bash
# Deterministic — no credentials needed
cd backend && pytest -q

# Conversational
export ELEVENLABS_API_KEY=...
export ATLAS_BASE_URL=http://127.0.0.1:8000
python evals/run_evals.py

# Validate scenario definitions without calling anything or touching the DB
python evals/run_evals.py --dry-run

# One scenario while iterating on the prompt
python evals/run_evals.py --only EVAL-007
```

The runner is idempotent: tests are looked up by name and updated, so re-running
after a prompt change does not litter the workspace with duplicates. It exits
non-zero if any scenario fails, so it drops into CI unchanged.

---

## Reading a failure

1. **Did the deterministic suite pass?** If not, fix the API first — the
   conversational result tells you nothing until it does.
2. **Transcript failed, database fine?** A phrasing or behaviour problem. Read
   the grader's rationale in the output; usually the prompt.
3. **Transcript passed, database failed?** The most serious kind. The agent
   described an action it did not take, or took one it should not have.
4. **Both failed?** Usually a tool description problem — the agent picked the
   wrong tool or built the wrong arguments. Fix `agent/tools.json`, re-provision,
   re-run.

Failure modes found this way, and what was changed in response, are recorded in
[failure-modes.md](failure-modes.md).
