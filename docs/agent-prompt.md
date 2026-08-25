# The agent prompt

The prompt itself lives at [`agent/prompt.md`](../agent/prompt.md) — one file,
version-controlled, deployed by `scripts/provision_agent.py`. This document
explains how it is put together.

---

## What belongs in the prompt, and what does not

The prompt is not the place for anything that can be enforced or computed.

| Concern | Where it lives | Why |
|---|---|---|
| Can this line be changed? | `rules.py` + the `modifiable` flag on every line | A rule in a prompt is a suggestion |
| Are these products ambiguous? | `search_products` returns `resolved` and the differing attributes | Deterministic and testable |
| Is this quantity valid? | Pydantic + `rules.py` | Rejected before it reaches the database |
| What does this SKU cost? | The API | The model has no way to know |
| When to ask a clarifying question | **The prompt** | Judgement |
| How to handle two requests at once | **The prompt** | Judgement |
| How much to say | **The prompt** | Judgement |

The test is simple: *if the model ignored this instruction, would the system
still be correct?* If yes, it belongs in code, and the prompt line is a
convenience. If no, it should not have been a prompt line in the first place.

---

## Structure

Nine sections, ordered by how much they matter:

1. **Identity** — who the agent is and who it is talking to.
2. **The grounding rule** — first, because it is the one that matters most:
   never state a business fact you have not retrieved, with an explicit list of
   what must never be invented.
3. **Tools** — a table of when to use each, plus the sequencing chains
   (`search_products` → `check_inventory`; `lookup_order` → confirm → write).
4. **Ambiguity** — how to read `resolved`, and to ask about what *differs*.
5. **Reads and writes** — reads free, writes confirmed, with example phrasing.
6. **Multiple requests** — handle in order, do not drop the second.
7. **Identity** — what is needed before a write.
8. **Errors** — what each code means conversationally, and never to read a code
   aloud.
9. **Style** — brevity, leading with the answer, no tool narration, no filler.

Then one worked example, annotated with what did *not* happen.

---

## Choices worth explaining

**The grounding rule is first and stated as a prohibition.** "Never state a
business fact you have not retrieved" is easier to follow than a list of things
to remember to do, and it is followed immediately by the concrete list of
things that must never be invented — order contents, stock, dates, RFQ numbers.

**Tool guidance is a table, not prose.** Tool selection is a lookup, and a table
reads like one. The prose that follows covers only the *chains*, which are the
part a table cannot express.

**The prompt tells the agent how to read tool responses.** It explicitly
describes `resolved`, `distinguishing_attributes` and `clarification_hint`,
because a well-designed response field is useless if the model does not know
what it means.

**Error handling names codes and their conversational meaning.** Not so the
agent can recite them — it is explicitly told not to — but so it can translate
`QUANTITY_INCREASE_NOT_ALLOWED` into "that stock is already committed, so we can
reduce it but not add to it".

**Style guidance is mostly negative.** "Do not open with Absolutely", "do not
narrate your tools", "do not repeat their request back". Voice agents fail
towards verbosity, and named anti-patterns are more actionable than "be concise".

**The worked example ends with what did not happen.** "No field names, no tool
names, no change made before the customer said yes." The absences are the part
worth demonstrating.

---

## Tool descriptions are prompt surface too

`agent/tools.json` carries as much behavioural instruction as the prompt does,
and it is closer to the decision. Each description says when the tool applies,
what its response means, and what not to do with it. For example
`search_products` ends:

> This tool does NOT report stock levels; use check_inventory for that.

That sentence sits exactly where the model is choosing a tool, which makes it
more reliable than the same rule buried in a prompt section. Every parameter
carries a description too — `test_every_parameter_is_described_for_the_model`
fails the build otherwise, because an undescribed parameter is one the model has
to guess at.

---

## Changing it

```bash
$EDITOR agent/prompt.md
python scripts/provision_agent.py          # idempotent; updates in place
python evals/run_evals.py --only EVAL-007  # re-run the affected scenario
```

Record what changed and why in [failure-modes.md](failure-modes.md). A prompt
that has quietly absorbed twenty bug fixes is brittle — when a fix belongs in
code, put it in code.
