# The runbook covers going live, and the thing that is live is stale

Design, 2026-09-03. A documentation round: no code, no tests.

## The gap

`docs/deploy-runbook.md` is an ordered checklist for the *first* deploy. It is good at that job
and nothing here changes it.

What it does not cover is the situation that actually exists. `poc.runiksoft.com` is serving a
build dated 2026-08-04, which predates everything the last month produced. Its
`openapi.json` shows `ChatRequest` carrying only `message, history, stream` — no `budget`,
`dose` or `compare`, and none of the `*Payload` schemas — so the server never emits `form`,
`dose_form` or `compare_form` and the three cards stay dormant whichever APK is installed.

Every open lead in the project's handoff now ends at the same sentence: *someone has to
redeploy*. Nothing anywhere records what that redeploy brings besides the features being waited
for. This spec fills that in.

## Where it goes

A new section in `docs/deploy-runbook.md`, `## Redeploying an existing host`, after `## Steps`
and before `## Rollback`. Same file, same voice, same ordered-checklist shape.

Not a new document: a second file about deploying would split the answer to one question across
two places, and the existing `## Rollback` section already assumes the reader is holding this
one.

## What the section must say

### 1. What the live build predates

The deployed build carries none of: the budget, dose and compare cards; the `/api/chat` rate
limit; the crop-norms data layer at all.

**Corrected after review.** This section first said "the two crop-norms rounds that changed
`data/crop_norms.json`" — the eighth false prose sentence in four rounds, and written by me
rather than by an implementer. Measured: `data/crop_norms.json` is ABSENT at `fd40d06`, created
`77c80c6` on 2026-08-19 — fifteen days after the deployed build — and rewritten by thirteen
commits since, across four dates. The correction is also the more useful sentence for the
reader: the deployed backend has no crop-norms data whatsoever, not merely stale data.

### 2. Three defaults changed underneath the features

A redeploy is not only the features someone asked for. Verified by diffing `src/config.py`
against `fd40d06`, the last commit before 2026-08-05:

**`max_tokens` 2048 → 3072, and this one needs a decision rather than a nod.** The value is
bounded by an **8192-token context window**, and the bound was measured end to end: the longest
context block is 3.452 prompt tokens on its own and 4.681 once the mobile client's 3.000-character
history budget rides along, so 4.681 + 3.072 = 7.753 of 8.192 — **439 tokens spare**.

That measurement was taken against the local model. The hosted deployment runs whatever
`OPENROUTER_MODEL` names, which this repository does not know. If that model's context window is
smaller than 8.192, the headroom is gone, and `src/config.py`'s own comment says what happens
then: the failure moves from a visibly truncated **answer** to a silently truncated **prompt**,
which drops the system instructions instead of cutting a sentence. So the runbook asks the
reader to confirm the hosted model's window, and names `SEND_BUDGET_CHARS` in
`mobile-app/src/chatStore.ts` as the other value that cannot move independently.

**`vector_store_url` and `vector_store_sha256` now carry real defaults** rather than empty
strings. A container that starts with an empty volume now downloads the real archive instead of
falling back to the ~1,5-hour fetch-and-ingest that produces a corpus roughly a tenth the size.
That is an improvement, and it is still a behaviour change worth knowing before it happens.

**`rate_limit_per_minute` = 60 is new.** Nothing needs setting; `RATE_LIMIT_PER_MINUTE=0`
disables it.

### 3. `--proxy-headers`, stated precisely

`docker-entrypoint.sh:69` runs `exec uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}"`
with no `--proxy-headers`, and the app speaks plain HTTP behind an HTTPS host.

**Adding the flag does not change the rate limit.** The limiter is global and reads no client
address at all — `SlidingWindowLimit.allow()` takes no arguments. The flag would only make a
future per-IP limit *possible*, and only alongside a trusted-proxy list, since `X-Forwarded-For`
is client-settable.

This is written as a note rather than a step, precisely so nobody adds the flag expecting
today's behaviour to improve. It is the highest-leverage thing available to whoever owns the
deployment, and it is worth nothing on its own.

### 4. CORS

Already covered by step 2 of the existing checklist. The section cross-references it rather than
repeating it — a second copy is a second thing to go stale.

### 5. How to tell the redeploy landed

Three checks, in order of what they distinguish:

- `GET /health` — provider and model, as the existing checklist already says.
- **`GET /openapi.json` — the check that separates the new build from the old one.**
  `components.schemas.ChatRequest.properties` must carry six names (`budget`, `compare`, `dose`,
  `history`, `message`, `stream`) and `components.schemas` must carry `BudgetPayload`,
  `DosePayload` and `ComparePayload`. Verified against the current build on 2026-09-03; the live
  build shows three names and no payload schemas, so the check discriminates rather than merely
  passing.
- The startup log carries the rate-limit line, `[main] rate limit: 60 requests/minute on
  /api/chat`, or its `WARNING` form when the ceiling is disabled.

## What this round does not claim

It does not make the live endpoint safer. The rate limit is in `main` and not in production, and
it stays that way until someone redeploys — which is the point of writing the redeploy down.

It also does not add authentication. A shared secret was considered and rejected for this
architecture on 2026-09-03: `web-widget/widget/agro-chat-widget.js` is a single `<script>` embedded
on a public WordPress site, so any secret it carries is in page source, and the mobile app's copy
sits in an APK whose strings this project has already demonstrated it can dump. Such a secret
filters automated scanners and nothing else, and calling it authentication would be the most
expensive false sentence available here.

## Testing

There is nothing to assert in pytest — this round adds prose to a document.

Every factual claim in the new section was verified against the repository before being written,
and the verification is the deliverable's quality gate: the `openapi.json` discriminator was run
against the current build, the three default changes come from a real `git diff` against
`fd40d06`, and the `--proxy-headers` claim was read off `docker-entrypoint.sh:69` and
`src/rate_limit.py`. A reviewer should re-run those rather than re-read them.
