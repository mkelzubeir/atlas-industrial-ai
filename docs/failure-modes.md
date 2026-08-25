# Failure modes

A running record of the ways this system can go wrong, what was changed in
response, and what has actually been verified.

**Status honesty:** the deterministic suite (122 pytest tests) has been run and
passes. The conversational suite in `evals/` has been authored and validated
offline (`--dry-run`), but **has not yet been executed against a live agent** —
that needs an ElevenLabs workspace and a publicly reachable backend. Everything
below is labelled accordingly. Section 3 is the honest to-do list.

---

## 1. Found and fixed during the build

Real defects, caught by building or testing rather than by reasoning.

### 1.1 Tool errors were invisible to the agent

**Found:** reading the ElevenLabs tool schema while writing `agent/tools.json`.

`tool_error_handling_mode` defaults to `auto`, which for webhook tools means
errors are **hidden** from the agent. It would have known only that something
failed — not that the order had shipped.

That would have broken EVAL-006, EVAL-010 and EVAL-012 silently, and worse, the
symptom would have looked like a model failure ("why won't it explain the
refusal?") rather than a configuration one.

**Fix:** every tool sets `tool_error_handling_mode: "passthrough"`.
`test_agent_config.py::test_every_tool_passes_errors_through_to_the_agent`
prevents it regressing.

### 1.2 Tool arguments never reached the Developer View

**Found:** building the Developer View against the real SDK types.

`AgentToolRequestClientEvent` carries `tool_name`, `tool_call_id`, `tool_type`
and `event_id` — **no parameters**. The panel would have shown that
`lookup_order` ran but not which PO it looked up, which is most of the value.

**Fix:** the backend keeps a per-conversation ring buffer of tool calls with
their arguments, exposed at `/api/demo/activity` and joined to client events by
the `X-Conversation-Id` header the tools forward.

### 1.3 ContextVar set in a route was invisible to the middleware

**Found:** three activity-feed tests failing with `tool == None`.

Starlette's `BaseHTTPMiddleware` runs the downstream app in a **separate task**,
so a `ContextVar.set()` inside a route handler does not propagate back up.

**Fix:** the middleware seeds a *mutable dict* into the context variable and the
route mutates it. The object is shared even though the context copy is not.
(`request.state` also works — it is backed by the shared ASGI scope — which is
why the error-code path worked while the tool-name path did not.)

### 1.4 `--dry-run` wiped the database

**Found:** running `evals/run_evals.py --dry-run` and watching it reset the demo
data before validating anything.

A flag whose entire purpose is "change nothing" was performing the single most
destructive action in the project.

**Fix:** the reset is skipped under `--dry-run`, and the dry run stubs tool ids
so it can still validate all twelve scenario bodies with no network at all.

### 1.5 Foreign keys were declared but unenforced

**Found:** writing `db.py`.

SQLite ships with foreign-key enforcement **off**. A schema full of `ForeignKey`
declarations would have been decorative, with orphaned rows accepted silently.

**Fix:** `PRAGMA foreign_keys=ON` on every connection.

---

## 2. Designed against (deterministically verified)

Failure modes the design anticipates. The **backend half of each is covered by a
passing test**; the conversational half awaits a live run.

| Failure mode | Design response | Verified by |
|---|---|---|
| Agent modifies a shipped order | `rules.py` refuses; API returns 409 | `test_shipped_order_modification_is_rejected` |
| Agent invents an order | 404 with a speakable message; prompt forbids invention | `test_unknown_order_returns_structured_not_found` |
| Agent guesses between similar SKUs | Search returns tied matches + `resolved: false` + differing attributes | `test_underspecified_fastener_is_ambiguous_by_length` |
| Agent claims stock from a product search | Inventory is a separate tool; search returns no stock data | `test_specific_description_resolves_to_one_sku` |
| Agent invents an RFQ number | Server assigns it; the model never sees one until the call returns | `test_creating_an_rfq_returns_a_server_generated_number` |
| Agent writes without confirmation | `customer_confirmed` required by the schema | `test_unconfirmed_write_is_refused` |
| Agent increases committed stock | Allocated lines are decrease-only | `test_increasing_an_allocated_line_is_rejected` |
| "Make it zero" read as a cancellation | Zero rejected explicitly, not reinterpreted | `test_zero_quantity_is_rejected_rather_than_treated_as_cancellation` |
| Mis-transcribed number becomes a real order | Quantity ceiling of 100,000 | `test_absurd_quantity_is_rejected` |
| Retried tool call double-books a quote | `idempotency_key` replays the original | `test_idempotency_key_prevents_a_duplicate_quote` |
| Order moves during a long call | Optional `expected_current_quantity` | `test_stale_expected_quantity_blocks_a_blind_overwrite` |
| Caller says "PO 1847" / "po-1847" / "#1847" | Server-side normalisation | `test_po_number_is_normalised` |
| Backend down, agent invents an answer | Fault injector + `SERVICE_UNAVAILABLE` with a speakable message | `test_armed_fault_makes_the_next_call_fail` |
| UI mutates an order directly | Proxy allow-list excludes the business API | Verified in-browser: `/api/atlas/orders/1847` → 404 `NOT_PROXYABLE` |

---

## 3. Not yet verified — needs a live agent

Honest gaps. These are exactly the questions the first live eval run should
answer.

**Prompt-level, unverified:**

1. **Does the agent actually ask instead of guessing?** EVAL-003 and EVAL-009.
   The API makes ambiguity *visible*; whether the model acts on it is untested.
2. **Does it hold both intents?** EVAL-007 is the flagship claim and the most
   likely thing to break. Dropping the second request is a common failure.
3. **Does it wait for confirmation?** EVAL-005 and EVAL-011. An eager agent that
   treats "what's on that line?" as an instruction is the risk.
4. **Does it read error codes aloud?** The prompt forbids it; unverified.
5. **Is `customer_confirmed` sent honestly?** The model could set it to `true`
   unconditionally. Nothing detects that today — see below.

**Configuration-level, unverified:**

6. **Dynamic-variable assignments.** `active_po_number` and friends are declared
   in `tools.json` but have never round-tripped through a live call. The
   `search_customer` assignment uses `customers.0.account_number`, which has no
   defined behaviour when the search returns zero matches.
7. **Latency.** Tool timeouts are set to 15–20s. Whether a real call feels
   responsive at that budget is unmeasured. If it drags, `response_filter` can
   trim payloads before they reach the LLM.
8. **ASR on SKUs.** `agent.json` boosts terms like "M8", "nitrile" and "ATL", but
   whether "A-T-L one-oh-three-oh" survives transcription is unknown.

**Known weaknesses with no fix yet:**

9. **`customer_confirmed` is an attestation, not proof.** A model that always
   sends `true` would defeat it. A stronger design would require the agent to
   echo back a server-issued confirmation token from the preceding read, so the
   write is cryptographically tied to a specific quoted change. Not built.
10. **Identity is a company name.** Anyone who knows "Northstar Manufacturing"
    can change PO 1847. Fine for a demo, unacceptable otherwise.
11. **The activity buffer is per-process.** Two backend workers would each hold a
    partial view and the Developer View would show gaps.

---

## 4. How to update this document

When a live eval fails:

1. Record the scenario, the transcript excerpt, and which layer failed
   (transcript, database, or both).
2. Decide where the fix belongs — **prompt**, **tool description**, or **code**.
   Prefer code: a rule enforced in `rules.py` cannot be talked out of, and a
   clearer tool description usually beats another prompt paragraph.
3. Add or tighten a test so the fix is pinned.
4. Move the entry from section 3 to section 1, with what changed.

The instinct worth resisting is patching every failure with another sentence in
the system prompt. A prompt that has absorbed twenty bug fixes is brittle, and
the twenty-first fix starts breaking the earlier ones.
