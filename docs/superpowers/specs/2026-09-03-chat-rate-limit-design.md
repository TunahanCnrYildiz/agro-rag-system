# `/api/chat` is deployed publicly with no auth and no rate limit

Design, 2026-09-03.

## The exposure

`poc.runiksoft.com` is serving the API today. Measured in the code:

| | |
|---|---|
| auth on `/api/chat` | none |
| rate limit | none |
| `cors_allow_origins` default | `*` |
| `chat_provider` | `local` (free) **or** `openrouter` (paid) |

Anyone who knows the URL can call `/api/chat` without limit. What that costs depends on an
environment variable this repository does not control: with `CHAT_PROVIDER=openrouter` it is an
open wallet, with `local` it is an open GPU. The 2026-08-11 key leak is why the first case is not
hypothetical.

This sat in the handoff under "pre-live checklist (only if going live)". The premise expired
when the host went live.

**Why this is ours to fix.** A rate limit is application code — `src/main.py` and a new module
beside it — not deployment configuration. It does not touch the Dockerfile, the compose file, the
entrypoint or the workflow, all of which are Emirhan's.

## The finding that shapes the design: this service cannot identify its clients

`docker-entrypoint.sh` runs `uvicorn src.main:app --host 0.0.0.0 --port 8000` with **no
`--proxy-headers`**, and the application speaks plain HTTP while the host serves HTTPS — so a
TLS-terminating proxy sits in front. `request.client.host` is therefore the proxy's address on
every request.

Two per-IP designs are available and both are worse than useless:

- **Key on `request.client.host`.** Every request shares one key. The code would say "per IP"
  and behave globally — a sentence describing something that does not happen, which is the
  defect class this project has spent two rounds removing from its comments. It would also be
  the *confusing* kind of wrong: it throttles all users together while reading as if it
  isolates them.
- **Key on `X-Forwarded-For`.** The header is client-settable. An attacker rotates it per
  request and the limit never fires. Trusting XFF safely requires trusting it only from known
  proxies, and the proxy topology belongs to a deployment this repository does not configure.
  A limiter that can be bypassed by setting a header is protection in name only.

**So the limit is global, and says so.** It counts requests to `/api/chat` regardless of who
sent them, because "who" is not knowable here. That is the honest instrument, and it bounds the
bill exactly, which is the thing at risk.

## Design

### A counter of its own, `src/rate_limit.py`

A small module holding one class: a sliding window over request timestamps. `main.py` gains only
a dependency, so it stays thin.

Sliding rather than fixed-window: a fixed window lets twice the limit through across a boundary
(60 at 11:59:59 and 60 at 12:00:00), and the whole point is a ceiling that holds.

**It takes its clock as a parameter.** The tests inject time rather than sleeping, so they are
fast and deterministic; only the wiring in `main.py` passes the real clock.

**It locks.** `chat()` is a synchronous `def`, so FastAPI runs it in a threadpool and concurrent
requests genuinely interleave. A `threading.Lock` around the check-and-record makes the ceiling
hold under concurrency instead of approximately.

### Only `/api/chat`

`/api/products` and `/api/articles` read a JSON file from disk. No model call, no money. The
limit guards the expensive path; widening it would add test surface and protect nothing.

### Default on, and generous: 60 requests per minute

Three people at a demo cannot produce sixty chat turns in a minute. A script produces them in
seconds. So the ceiling is invisible to the use the system has today and immediate for the use it
is exposed to.

`RATE_LIMIT_PER_MINUTE=0` disables it entirely. Emirhan's running deployment needs no change and
sees no behaviour change.

### A startup line, the way open CORS already gets one

`_warn_if_open_cors` already prints a one-time reminder when a dangerous default is in force.
The rate limit prints the ceiling that is active — or, at `0`, that there is none. Making a
dangerous configuration visible at boot is an established habit in this file, not a new one.

### 429 with a Turkish `detail`

Consistent with the rest of the service, whose user-visible text is Turkish.

**What today's clients do with it, stated rather than discovered later:** they render it as a
generic failure. `mobile-app/src/api.ts:45` throws `API error: ${resp.status}`, and the SSE path
at line 217 does the same. Making the client show the real message needs a client change, a new
APK, and a device to verify on — all blocked on the same redeploy this round exists to work
around. Out of scope, and named here so nobody reports it as a surprise.

## The trade-off, stated rather than buried

**A global limit converts an unbounded bill into a denial-of-service opening.** An attacker can
hold 60 requests a minute indefinitely and keep real users out. That is accepted deliberately:
the alternative on offer is an unbounded bill, and this is a proof of concept whose URL is known
to few people.

**The real fix is authentication** — a shared secret the app sends bounds both the bill and the
denial of service. It is not this round because it needs the client to send the secret (a new
APK), the deployment to carry it (Emirhan's environment), and a device to verify on. The rate
limit is the only measure that works today without anyone else's cooperation, which is precisely
why it is the one being built.

## Testing

The counter is a pure class with an injected clock, so it is tested without sleeping:

- a request under the ceiling is allowed
- the request that exceeds the ceiling is refused
- the ceiling is exact at its own edge — the Nth request passes and the N+1th does not, both
  inside one window
- a refused window admits again once the oldest timestamp falls out of it
- a limit of `0` never refuses
- the window is a rolling one, not a fixed bucket: requests spread across a boundary are counted
  against the last 60 seconds and not reset by the clock

Through `TestClient`, on the app itself:

- `/api/chat` returns 429 once the ceiling is crossed, with the Turkish detail
- `/api/products` and `/api/articles` are not limited, however many times they are called
- the startup line reports the active ceiling, and reports its absence at `0`

Concurrency is asserted rather than assumed: a test drives the counter from several threads at
once and checks that no more than the ceiling is admitted. A lock that is never contended looks
identical to one that is not there, so the test is pinned by mutation — remove the lock and it
must go red.

**One honest caveat about that mutation.** The unlocked race is a real interleaving between
reading the window's length and appending to it, but whether it manifests depends on thread
scheduling, so the test could pass without the lock by luck. The implementer must run the
unlocked mutation enough times to see it fail, and **report it if it does not** rather than
declaring the lock pinned. An unreliable red is a finding about the test, not a detail to smooth
over: it would mean the test cannot distinguish a locked counter from an unlocked one, and the
lock's necessity would then rest on the argument above rather than on evidence.
