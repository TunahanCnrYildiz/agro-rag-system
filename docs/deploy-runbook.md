# Deploy Runbook (local → hosted)

A short, ordered checklist for the actual go-live step. Strategy/tradeoffs live
in `roadmap-deployment.md`; this file is the "what to do" once you decide to
deploy. Nothing here changes local dev — local stays the default.

## Prerequisites
- A host: Fly.io / Render / Railway / a VPS. Platform TLS provides HTTPS.
- An OpenRouter account + key (hosted chat).
- A hosted bge-m3 embedding endpoint (e.g. DeepInfra `BAAI/bge-m3`) + key,
  **or** keep embeddings on a reachable LM Studio. Embeddings must stay bge-m3
  or the store needs a full re-ingest.

## Steps
1. **Persistent disk for the store.** `data/vector_store` (~1.4 GB) is gitignored.
   Attach a persistent volume and copy or re-ingest the store onto it. The
   container mounts it (see `docker-compose.yml` / your host's volume config).
2. **Backend env (host secret store, never committed):**
   - `CHAT_PROVIDER=openrouter`, `OPENROUTER_API_KEY=...`, `OPENROUTER_MODEL=...`
   - `EMBEDDING_BASE_URL=...`, `EMBEDDING_API_KEY=...`, `EMBEDDING_MODEL=BAAI/bge-m3`,
     `EMBEDDING_IDENTITY=bge-m3`
   - `CORS_ALLOW_ORIGINS=https://your-site.example` (narrow it — the backend logs
     a warning while it is `*`).
3. **Deploy the backend** (Docker image builds from the repo `Dockerfile`).
   Confirm `GET /health` returns the expected provider + model.
4. **Mobile build:** set `EXPO_PUBLIC_API_BASE` to the hosted URL (EAS build env
   or `mobile-app/.env`) and rebuild. See `mobile-app/.env.example`.
5. **Web widget:** point its backend URL at the hosted API.
6. **Verify quality held:** run `python -m evals.run_eval` against the hosted
   config before announcing the deploy.

## Rollback
- Local dev is unaffected at all times. To revert a host to local-style behavior,
  clear the hosted env vars (chat falls back to `local`, embeddings to LM Studio).
