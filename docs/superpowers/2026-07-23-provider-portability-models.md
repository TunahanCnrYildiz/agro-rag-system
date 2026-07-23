# Provider portability: chosen OpenRouter models and cost estimate

Source: live fetch of `https://openrouter.ai/api/v1/models` on 2026-07-23 (342 models returned, no API key needed). Raw catalogue saved to `/tmp/openrouter-models.json` for this session; prices below are read directly from that response, not from prior knowledge.

Context-length rule: the local baseline (a Gemma-class ~12B build served by LM Studio) runs the assistant's chat context at 8,192 tokens. Any OpenRouter model with `context_length` **below** 8,192 is disqualified for this measurement, since a smaller window would change what fits in the prompt and confound the comparison.

## Chosen models

### Strong — `openai/gpt-5.1`
- Class: strong (frontier-class).
- Prompt price: $1.25 / million tokens. Completion price: $10.00 / million tokens.
- Context length: 400,000 tokens.
- Why over the nearest alternative: the closest competitor is `anthropic/claude-sonnet-5` ($2.00 / $10.00 per million, 1,000,000 ctx) — same completion price, but 60% higher prompt price, and our calls are prompt-heavy (2,500 prompt tokens vs 400 completion tokens per call), so the prompt-price gap dominates the real cost difference. `google/gemini-3.1-pro-preview` ($2.00 / $12.00 per million) is both pricier and carries a `-preview` tag, which risks the id being replaced or changed mid-measurement — avoided for that reason too. `anthropic/claude-opus-4.8` ($5.00 / $25.00 per million) is also frontier but roughly 4x the cost of gpt-5.1 for the same call volume, which would matter a lot if phase 2 is triggered.

### Mid — `google/gemini-2.5-flash-lite`
- Class: mid (cheap/fast, production-plausible).
- Prompt price: $0.10 / million tokens. Completion price: $0.40 / million tokens.
- Context length: 1,048,576 tokens.
- Why over the nearest alternative: `openai/gpt-4o-mini` ($0.15 / $0.60 per million, 128,000 ctx) is the obvious production-grade comparison, but is 50% pricier on prompt tokens and 33% pricier on completion tokens, with an 8x smaller context window, for no offsetting benefit for this workload. Gemini 2.5 Flash Lite is a stable (non-preview) id in the same "cheap/fast" tier.

### Near-peer — `google/gemma-3-12b-it`
- Class: near-peer (open model close in size/class to the local Gemma-class ~12B baseline).
- Prompt price: $0.05 / million tokens. Completion price: $0.15 / million tokens.
- Context length: 131,072 tokens.
- Why over the nearest alternative: `mistralai/mistral-nemo` (also ~12B, $0.019 / $0.03 per million, 131,072 ctx) is actually cheaper, but it is a different model family (Mistral, not Gemma). Since the point of this class is to bridge directly to the local baseline, staying inside the same model family isolates "hosted vs local" as the only variable, instead of adding a second confound (different architecture family) on top of it. `google/gemma-3-27b-it` (27B, $0.10 / $0.30 per million) was also considered but rejected: at 27B it is more than twice the size of the ~12B local build, so it no longer represents the same size class.

## Prices read from the catalogue (summary)

| id | class | prompt $/M tok | completion $/M tok | context length |
|---|---|---|---|---|
| `openai/gpt-5.1` | strong | 1.25 | 10.00 | 400,000 |
| `google/gemini-2.5-flash-lite` | mid | 0.10 | 0.40 | 1,048,576 |
| `google/gemma-3-12b-it` | near-peer | 0.05 | 0.15 | 131,072 |

## Cost estimate

Per-call token assumption (given in the brief, used for every hosted call below): ~2,500 prompt tokens + ~400 completion tokens per call (four retrieved chunks of ~1,000 characters plus the system prompt; `max_tokens` capped at 2,048).

Per-call cost formula: `2,500 × prompt_price_per_token + 400 × completion_price_per_token`.

- `openai/gpt-5.1`: 2,500 × $0.00000125 + 400 × $0.00001 = $0.007125 / call
- `google/gemini-2.5-flash-lite`: 2,500 × $0.0000001 + 400 × $0.0000004 = $0.00041 / call
- `google/gemma-3-12b-it`: 2,500 × $0.00000005 + 400 × $0.00000015 = $0.000185 / call

### Phase 0 (local baseline)
54 calls, cost **$0.00** (runs locally against the LM Studio Gemma build).

### Phase 1 (all three models, 54 calls each = 162 calls total)

| model | calls | cost |
|---|---|---|
| `openai/gpt-5.1` | 54 | $0.3848 |
| `google/gemini-2.5-flash-lite` | 54 | $0.0221 |
| `google/gemma-3-12b-it` | 54 | $0.0100 |
| **Phase 1 total (162 calls)** | **162** | **$0.4168** |

### Phase 2 (conditional, per model — needs its own approval if triggered)

184 calls (`--faithfulness --repeat 4` over 23 `corpus_fact` cases × normal+ablated × 4 repeats = 184) are billed to the hosted model under test. A further 12 calls (`--no-context --only local`) are, per their `--only local` flag, run against the local LM Studio model only — they are $0 regardless of which hosted model phase 2 targets, and are listed here only because the brief groups them under the phase-2 call count.

| model | billed calls (184) | cost | + local-only calls (12, $0) | total calls shown |
|---|---|---|---|---|
| `openai/gpt-5.1` | 184 | $1.3110 | 12 ($0) | 196 |
| `google/gemini-2.5-flash-lite` | 184 | $0.0754 | 12 ($0) | 196 |
| `google/gemma-3-12b-it` | 184 | $0.0340 | 12 ($0) | 196 |

If phase 2 were ever run against all three models in the same window (not the plan — it's per-model, conditional, and each needs its own approval), the combined billed cost across all three would be $1.3110 + $0.0754 + $0.0340 = **$1.4204**.

## Models disqualified on the context-length rule

Considered and rejected because `context_length < 8,192`:

- `undi95/remm-slerp-l2-13b` — 13B, same rough size class as the near-peer candidates, but `context_length` = 6,144. Disqualified.
- `openai/gpt-4` — a legacy frontier candidate, `context_length` = 8,191 — one token short of the 8,192 cutoff. Disqualified (moot in practice, since `gpt-5.1` is both cheaper and current).

Note on a boundary case that was *not* disqualified: a few small models report `context_length` of exactly 8,192 (e.g. `sao10k/l3-lunaris-8b`, `gryphe/mythomax-l2-13b`). The brief's rule disqualifies context **below** 8,192, so 8,192 itself passes; none of these were chosen anyway, but the exact wording of the rule was applied literally.

## Ambiguities resolved

1. **Whether the phase-2 "+12 `--no-context --only local`" calls are billed to the hosted model.** The `--only local` flag reads as restricting those 12 calls to the local provider, i.e. they are free and not part of the hosted-model bill. Resolved by treating the 184-call faithfulness batch as the only billed portion of phase 2, and showing the 12 local-only calls at $0 for completeness of the call count.
2. **Whether the phase-1 per-call token estimate (2,500 prompt / 400 completion) also applies to the phase-2 calls.** The brief only states this estimate for phase 1. Since phase 2 reuses the same retrieval setup (four ~1,000-character chunks + system prompt) just repeated across normal/ablated conditions and repeats, the same per-call estimate was reused for phase 2's 184 billed calls. This likely slightly overstates the ablated-condition cost (which may carry less context), so the phase-2 figures above should be read as a conservative (upper-bound) estimate, appropriate for a pre-approval cost ceiling.
3. **Free-tier (`:free`) model variants.** Several candidates (e.g. Gemma, DeepSeek, Qwen, gpt-oss) have zero-cost `:free` siblings in the catalogue. These were deliberately not chosen: free-tier endpoints on OpenRouter carry tighter rate limits and lower availability guarantees, which is a bad fit for a scheduled, unattended measurement run of this call volume. Paid ids were used throughout.
4. **"Strong" interpreted as frontier-but-not-most-expensive.** The brief's class label is "a frontier-class model," not "the most expensive model." Among genuinely frontier-tier candidates, `openai/gpt-5.1` was preferred over pricier peers (`claude-opus-4.8`, `gpt-5.2`, `gemini-3.1-pro-preview`) on the grounds that all are comparably frontier-class, so the cheaper one under a fixed call budget is the better pick.
