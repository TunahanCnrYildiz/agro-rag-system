# Redeploy Runbook Section Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `docs/deploy-runbook.md` a section covering the redeploy of the host that is already live and stale, so whoever owns the deployment can do it in one pass and knows what changes underneath the features they asked for.

**Architecture:** Two tasks, and the split is the point. Task 1 runs every verification command and records the raw output to a scratch evidence file. Task 2 writes the prose using only what that file contains, then checks mechanically that every figure in the new section appears in it. No code, no tests — the deliverable is one section of one Markdown document.

**Tech Stack:** Markdown. The verification commands use git, grep and a one-line Python `TestClient` probe.

**Spec:** `docs/superpowers/specs/2026-09-03-redeploy-runbook-design.md`

## Global Constraints

- **Every figure in the new prose must come from Task 1's evidence file.** Do not compute, estimate, round or recall a number. This project has shipped seven false prose sentences across three rounds, every one a small overstatement of something almost true, and every one was caught by measurement rather than by rereading.
- The section is titled `## Redeploying an existing host` and sits between the existing `## Steps` and `## Rollback` sections of `docs/deploy-runbook.md`.
- **Do not modify** `Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh`, `.github/workflows/`, `mobile-app/eas.json`, `mobile-app/app.json`, or any file under `src/` or `tests/`. This round changes one Markdown file. `docker-entrypoint.sh` is READ in Task 1 and never written.
- Do not repeat the CORS instruction; step 2 of the existing checklist already carries it, and a second copy is a second thing to go stale. Cross-reference it.
- The `--proxy-headers` note must say plainly that adding the flag does **not** change the current rate limit. It is a note, not a step, so nobody adds it expecting today's behaviour to improve.
- Do not claim the round makes the live endpoint safer. It does not; the rate limit is in `main` and not in production until someone redeploys.
- English, matching the runbook's existing voice: an ordered checklist that states the reason a step exists, not just the step.
- Commit messages: short, natural, English, no body, **no `Co-Authored-By` trailer**.
- Run any Python from the repo root. Prefix with `PYTHONIOENCODING=utf-8` if output contains Turkish characters — the Windows console default raises `UnicodeEncodeError` on `İ`.

## Files

- Create (scratch, gitignored, not committed): `.superpowers/sdd/redeploy-evidence.md` — the raw command output Task 2 writes from.
- Modify: `docs/deploy-runbook.md` — one new section.

## Orientation for every implementer

This project is a Turkish agricultural assistant with a FastAPI backend. A copy of that backend is deployed at `poc.runiksoft.com` and has been serving a build dated 2026-08-04 — before the budget, dose and compare cards existed, and before `/api/chat` had any rate limit. Every open lead in the project's handoff currently ends at "someone has to redeploy".

`docs/deploy-runbook.md` is 60 lines and describes the *first* deploy. It is not wrong; it simply does not cover refreshing a host that already exists. The reader of the new section is whoever owns that deployment, who is not the author of this repository and will not read the source to find out what changed.

---

### Task 1: Gather the evidence

**Files:**
- Create: `.superpowers/sdd/redeploy-evidence.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `.superpowers/sdd/redeploy-evidence.md`, which Task 2 treats as the only permitted source of figures.

Nothing is written into the runbook in this task. The whole job is to run eight commands and paste their real output, verbatim, under a heading each. Where a command's output surprises you relative to the label, write the surprise down — that is a finding, not a nuisance.

- [ ] **Step 1: Confirm which commit the deployed build predates**

```bash
git rev-list -1 --before=2026-08-05 main
```

Expected: a commit hash beginning `fd40d06`. If it differs, record what you got and use YOUR value for the diff in Step 2 — the plan's hash was resolved on 2026-09-03 and the history may have moved.

- [ ] **Step 2: Capture the config defaults that changed since then**

```bash
git diff fd40d06..main -- src/config.py | grep -E "^[+-] *(max_tokens|vector_store_url|vector_store_sha256|rate_limit_per_minute)"
```

Expected: `max_tokens` moving from 2048 to 3072, `vector_store_url` and `vector_store_sha256` gaining defaults, and `rate_limit_per_minute` appearing at 60.

- [ ] **Step 3: Capture the measured context-window headroom**

```bash
grep -n "8,192\|8192\|439 tokens\|3,452\|4,681" src/config.py
```

Record every matching line. These are the figures behind the `max_tokens` warning, and Task 2 may use no others.

- [ ] **Step 4: Capture the other value that cannot move independently**

```bash
grep -n "SEND_BUDGET_CHARS = " mobile-app/src/chatStore.ts
```

- [ ] **Step 5: Capture the uvicorn invocation**

```bash
grep -n "exec uvicorn" docker-entrypoint.sh
```

Read only. This file must not be modified by this round.

- [ ] **Step 6: Confirm the limiter reads no client address**

```bash
grep -n "def allow" -A 3 src/rate_limit.py
```

Expected: `def allow(self) -> bool:` — no request, no address, no key parameter. This is what makes the `--proxy-headers` note true.

- [ ] **Step 7: Capture the exact startup line**

```bash
grep -n "rate limit:" src/main.py
```

- [ ] **Step 8: Run the openapi discriminator against the current build**

```bash
python -c "import sys; sys.path.insert(0, '.'); from fastapi.testclient import TestClient; from src import main; s = TestClient(main.app).get('/openapi.json').json(); print('fields:', sorted(s['components']['schemas']['ChatRequest']['properties'])); print('payloads:', sorted(k for k in s['components']['schemas'] if 'Payload' in k))"
```

Expected: six field names including `budget`, `compare` and `dose`, and three payload schema names. This is the check that will distinguish a redeployed build from the live one, so it must be run rather than assumed.

- [ ] **Step 9: Write the evidence file**

Create `.superpowers/sdd/redeploy-evidence.md` with one `##` heading per step above, each followed by the command you ran in a fenced block and its **verbatim** output in another. Add a final `## Surprises` heading; if nothing surprised you, write "none" under it rather than omitting it.

Do not commit this file — `.superpowers/sdd/` is gitignored, and that is deliberate: it is working evidence, not a deliverable.

- [ ] **Step 10: Report**

There is nothing to commit in this task. Report the evidence file's path and anything under `## Surprises`.

---

### Task 2: Write the section

**Files:**
- Modify: `docs/deploy-runbook.md`

**Interfaces:**
- Consumes: `.superpowers/sdd/redeploy-evidence.md` from Task 1 — the only permitted source of figures.
- Produces: nothing further.

Read the whole of `docs/deploy-runbook.md` first. It is 60 lines. Match its voice: numbered steps that say why they exist, with the sharp warnings set off in bold the way the embedding-migration note in step 2 is.

- [ ] **Step 1: Read the evidence and the runbook**

Read `.superpowers/sdd/redeploy-evidence.md` and `docs/deploy-runbook.md` in full before writing anything.

- [ ] **Step 2: Write the section**

Insert a new section between the end of `## Steps` and the `## Rollback` heading. It must contain, in this order:

**A short opening** saying the existing checklist covers the first deploy, that `poc.runiksoft.com` is serving a build dated 2026-08-04, and that its `openapi.json` carries only `message, history, stream` on `ChatRequest` — so the budget, dose and compare cards stay dormant whichever client connects.

**What the live build predates**: the three cards, the `/api/chat` rate limit, and the two crop-norms rounds that rewrote `data/crop_norms.json`.

**Three defaults that change underneath the features**, from Step 2 of the evidence:

1. `max_tokens` 2048 → 3072. **Set off in bold as the one needing a decision.** Use the measured figures from evidence Step 3 and say what `src/config.py` says: the bound rests on an 8.192-token context window, the headroom was measured end to end, and if the hosted model's window is smaller the failure moves from a visibly truncated ANSWER to a silently truncated PROMPT, which drops the system instructions rather than cutting a sentence. Say that this repository does not know what `OPENROUTER_MODEL` names, so this is a check the reader must perform, not an assertion. Name `SEND_BUDGET_CHARS` in `mobile-app/src/chatStore.ts` (evidence Step 4) as the other value that cannot move independently of it.
2. `vector_store_url` and `vector_store_sha256` now carry real defaults, so a container starting on an empty volume downloads the real archive instead of falling back to the fetch-and-ingest path. An improvement, and still a behaviour change worth knowing before it happens.
3. `rate_limit_per_minute` = 60 is new. Nothing needs setting; `RATE_LIMIT_PER_MINUTE=0` disables it.

**A `--proxy-headers` note, not a step.** Quote the uvicorn line from evidence Step 5. State that adding the flag does **not** change the rate limit, because the limiter is global and reads no client address — cite `SlidingWindowLimit.allow()` taking no arguments, from evidence Step 6. Say it would only make a future per-IP limit possible, and only alongside a trusted-proxy list, since `X-Forwarded-For` is client-settable. Say plainly that it is worth nothing on its own, so nobody adds it expecting an improvement today.

**A one-line cross-reference to step 2 of the existing checklist for CORS.** Do not restate the instruction.

**Three verification checks**, in this order: `GET /health` for provider and model; `GET /openapi.json` as the check that separates the new build from the old, with the exact six field names and three payload schema names from evidence Step 8; and the startup log line from evidence Step 7.

**A closing paragraph** saying what this does not do. Two sentences:

- The rate limit lives in `main`, not in production, so the live endpoint stays open until the redeploy happens.
- An API key or shared secret was considered on 2026-09-03 and rejected for this architecture, so nobody has to raise it again: `web-widget/widget/agro-chat-widget.js` is a single `<script>` embedded on a public site, so any secret it carries sits in page source, and the mobile app's copy ships inside an APK. Such a secret filters automated scanners and nothing else — worth having one day, but it is not authentication and must not be described as such.

- [ ] **Step 3: Check every figure against the evidence**

This is the step that replaces a test run, so do it mechanically rather than by rereading.

List every number, quoted string, file path and line reference that appears in the section you just wrote. For each one, point at the line of `.superpowers/sdd/redeploy-evidence.md` it came from. Anything you cannot point at is either wrong or unverified — delete it or go measure it, and say in your report which you did.

- [ ] **Step 4: Confirm the diff touches one file**

```bash
git status --short
git diff --stat
```

Expected: `docs/deploy-runbook.md` only. If anything under `src/`, `tests/` or the deployment files appears, stop and report.

- [ ] **Step 5: Commit**

```bash
git add docs/deploy-runbook.md
git commit -m "Write down what a redeploy of the live host brings"
```
