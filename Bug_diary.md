### Bug #1 — Safety false-positive on normal shipping/status language

**Repro:** Do you ship internationally?" was blocked as an unauthorized completed-action claim.
**Root cause:** ction-claim regex in safety.py matched any fulfillment- adjacent word ("ship")
instead of only genuine completion phrasing.
**Fix:** narrowed the regex to match only explicit completion phrasing
(e.g. `order|refund|cancellation ... (approved|completed|processed)`)
rather than any sentence containing a fulfillment-adjacent verb.
**Regression test:**international shipping case asserts no false handoff=True

### Bug #2 — Order-status routing leaked prior session refusals

**Repro:** After a refused injection attempt, a later unrelated "where is
my order" (no ID) returned the same injection-refusal text instead of
asking for an order ID.
**Cause:** ID resolution wasn't isolated per-turn; a broad safety check
evaluated session history instead of the current turn.
**Fix:** added `_resolve_order_id_for_turn` (current message first, then
`last_order_id` only on elliptical reference), decoupled from the
action-claim check.
**Regression test:** 3-part case — valid ID, missing ID, missing ID after
prior injection.

### Bug #3 — Ungrounded answer on an out-of-scope question

**Repro:** "Do you offer price matching with Amazon?" got a confident
"No" citing an unrelated policy chunk instead of stating insufficiency.
**Cause:** a tangential chunk scored just above `SIMILARITY_THRESHOLD`;
prompt didn't distinguish direct coverage from inferred coverage.
**Fix:** tuned threshold + added a relevance guard + strengthened prompt
to require explicit insufficiency over inference.
**Regression test:** Amazon case asserts `insufficient`/`handoff=True`,
no confident claim. Re-verified no false negative on a genuinely sparse
but covered topic (unsupported shipping destination).
**Beyond visible cases** — found via manual adversarial testing.

### Bug #4 — Eval score instability traced to Groq daily token quota (Rate limit issue)

**Repro:** three consecutive clean reruns degraded 8/15 → 5/15 → 2/15,
including previously-passing cases losing sources (for only visible-tests).
**Cause:** `errors.log` showed a Groq daily TPD quota exhaustion
(`llama-3.3-70b-versatile` or `openai/gpt-oss-120b`, also since deprecated by Groq), silently
caught and returned as a degraded fallback — looked like a regression,
wasn't.
**Fix:** retry-with-backoff on Groq/Pinecone calls, structured
`RATE_LIMIT` log entries, inter-case eval delay, switched
`LLM_MODEL` to `qwen/qwen3.6-27b` (separate quota pool).
**Regression test:** none at case level (infra, not logic) — standard is
now "3-5 stable consecutive runs" before trusting a score.

### Bug #5 — Verbose/over-informative responses beyond what was asked

**Repro:** simple factual questions (e.g. a single order-status lookup or
a yes/no policy question) sometimes returned multi-paragraph answers
padded with unrequested detail — extra policy caveats, unrelated
adjacent fields, or restating the full order object — rather than a
direct, scoped answer.
**Cause:** the prompt instructs the model to be thorough and cite sources
but doesn't bound response scope to what was actually asked, so the model
defaults to maximal disclosure of everything it retrieved/received from
a tool call.
**Fix:** Added concise-answer instructions to the system/user prompts,
disabled Qwen reasoning with reasoning_effort="none", and reduced max_tokens to 350.
**Regression test:** Ask a narrow question such as “How many days do I have to return an item?”
and verify the response contains only the direct answer, no <think> block,
no reasoning, and no unrelated policy details.

### Bug #6 — Conflict detection inconsistent across phrasing of the same scenario (NOT YET COMPLETELY FIXED)

**Repro:** the Breeze Tumbler hand-wash/dishwasher-safe conflict passes
under one case's phrasing (`custom-breeze-care-conflict`) but fails under
another (`genuine-active-source-conflict`) for the same underlying
contradiction.
**Cause:** conflict detector or prompt instruction is still phrase-
sensitive rather than robustly triggering on the underlying contradiction
regardless of how the question is asked.
**Fix:** Make the conflict detector check the underlying chunk content/metadata directly (not the user's phrasing) so it fires consistently regardless of how the question about the same contradiction is worded.
**Regression test:** keep both cases — the discrepancy itself is useful
diagnostic signal until resolved.

### Bug #7 — Missing source citations on some groundedness/conflict cases (NOT YET COMPLETELY FIXED)

**Repro:** `retrieved-prompt-injection` and `genuine-active-source-conflict`
cases failed on missing `required_sources`, despite substantively correct
answer content.
**Cause:** inconsistent citation behavior across query types — not yet
fully isolated whether this is a prompt-following gap or a `sources`
population gap in `agent.py`.
**Fix:** Fix agent.py to always populate sources from the retrieved chunks regardless of which response branch fires (normal, refusal, or conflict), instead of only on the happy path.
**Regression test:** existing cases already assert `required_sources`;
keep as-is once fixed.
