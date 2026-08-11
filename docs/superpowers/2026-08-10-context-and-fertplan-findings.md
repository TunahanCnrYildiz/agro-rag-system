# Context and fertplan — gate results

Plan: `docs/superpowers/plans/2026-08-10-context-and-fertplan.md`
Spec: `docs/superpowers/specs/2026-08-09-routing-and-context-design.md`
Branch: `context-and-fertplan`, head `c411bb9`

This is the first plan in which a route changes what a user receives. `fert_plan`
answers now carry the user's province, the month and season, and the coming week's
weather. The fertilization table that would turn that into a calendar ships **empty**
and stays empty until an agricultural engineer reviews rows.

---

## 1. Environment — the speed gate was NOT met

The plan's own gate for this step is "verify above 40 tok/s". **It was not met.**
Every number below was measured at ~14 tok/s, and that is recorded here rather than
worked around.

| Configuration | tok/s |
|---|---|
| As found | 8.1 |
| After `lms unload` + `lms load` (Vulkan, other apps running) | 13.7 / 13.6 |
| ROCm runtime, other apps closed, 19.8 GB RAM free | 14.4 (median, warm-up excluded) |

Three levers were pulled and **all three were measured, and none of them worked**:

- **Model eject/reload** — the project's documented remedy for the 2026-07-28 and
  2026-08-10 slowdowns. Recovered 8.1 → 13.7. Real but small.
- **Runtime selection** (Vulkan → ROCm). 13.65 → 14.4. That is noise. The standing
  warning in this project's notes — *do not switch runtimes to chase speed* — held
  up, and this time there is a number behind it rather than an assertion.
- **Background load.** Closing BlueStacks and the browser took free system RAM from
  5.9 GB to 19.8 GB and dropped `llama-server`'s host working set from 11.2 GB to
  1.33 GB. **Throughput did not move.**

### What was ruled out, by measurement

- **Not a VRAM spill.** `Get-Counter '\GPU Process Memory(*)\Shared Usage'` — the
  counter the routing-foundation findings named as the discriminator and did not run
  — shows `llama-server` holding **8.57 GB dedicated (VRAM) against 0.9 GB shared
  (system RAM)**. The model is resident on the card. This is the measurement that
  earlier rounds inferred instead of taking.
- **Not a CPU fallback.** During generation the GPU compute engine sat at **90.3%**
  while the CPU sat at 57%. The work is on the GPU and the GPU is busy.
- **Not host-memory pressure.** See the background-load lever above.

### What is not explained

`docs/superpowers/2026-08-10-routing-foundation-findings.md` records **61.3 tok/s**
on this same machine earlier the same day, on the Vulkan runtime. Today the same
model on the same machine does 14.4 and none of the three levers recovers it. The
cause is **not established** and is deliberately not guessed at here — the last time
a plausible-sounding cause was written down as fact in this project it cost a day.

One cell of the comparison is still empty: **Vulkan on a cleaned machine** was never
measured. Vulkan is the configuration that produced 61.3, so that is the next thing
to try, and this section should be amended when it is.

Practical consequence for this run: none. `evals/run_eval.py` sets
`request_timeout = 400.0`, which at 14.4 tok/s is roughly 5,700 tokens of headroom,
so the timeout failures that destroyed the Faz 0 measurement at 8.2 tok/s did not
recur. Every case below completed and was scored. The full run took ~70 s per case,
~65 minutes total.

---

## 2. Unit suite

```
PYTHONIOENCODING=utf-8 python -m pytest -q
411 passed
```

Baseline at the start of this plan was 334. The plan added 77 tests across eight
tasks.

---

## 3. Routing gates

```
PYTHONIOENCODING=utf-8 python -m evals.run_routing

dogruluk : 37/42 (88%)   kapi: >= 90%
model katmani kapisi (<= 30%) GECERSIZ: src.router.classify() yalnizca how='rule'
  veya how='default' donduruyor, model katmani hic calismiyor - bu kapi karara katilmiyor.
kural disi (varsayilan rota) orani : 13/42 (31%)   bilgi amacli, kapi degil
karar dagilimi : {'default': 13, 'rule': 29}

kacirilanlar:
  beklenen=nutrition    gelen=plant_info   Domates yapraklarım sararıyor, ne önerirsiniz?
  beklenen=nutrition    gelen=plant_info   Toprağımın pH değeri çok yüksek, nasıl düzeltebilirim?
  beklenen=nutrition    gelen=plant_info   Bitkilerde demir eksikliği nasıl giderilir?
  beklenen=budget       gelen=plant_info   Zeytinlikten yıllık ne kadar gelir beklerim?
  beklenen=offscope     gelen=plant_info   Bu akşam hangi filmi izleyeyim?

sevke uygun rotalar (sifir yanlis giris): budget, crop_choice, fert_plan, nutrition, offscope
yanlis giris alan rotalar: {'plant_info': 5}   <- bunlar davranis ayristiramaz

KAPILAR: GECMEDI
```

**The accuracy gate is still red at 88% against the pre-registered 0.90, and it was
not relaxed.** This plan did not touch the routing rules, so the number is unchanged
from the routing-foundation branch. Unchanged is the correct outcome; a *moved*
number here would have needed explaining.

**The condition that actually governed this plan is the second one.** `fert_plan`
has **zero wrong entries** — no case belonging to another route lands on it — so it
was permitted to diverge. All five misses flow the same way, from some other route
into `plant_info`, which is why `plant_info` is the one route that may not
dispatch. Since every route still runs the corpus path except `fert_plan`, the five
misses currently change nothing a user sees.

---

## 4. Regression shield

```
PYTHONIOENCODING=utf-8 python -m evals.run_eval --fast
=== 55/55 cases passed ===
  retrieval: 55/55 | context: 55/55
```

```
PYTHONIOENCODING=utf-8 python -m evals.run_eval
=== 55/55 cases passed ===
  retrieval: 55/55 | context: 55/55 | product-gating: 55/55 | grounding: 55/55 | guardrail: 55/55
[answers] wrote 55 samples -> evals/runs/20260810T144554Z-full.jsonl
```

**Zero reds, so there is no red analysis to report.** This matters more here than in
previous rounds: the `fert_plan` system prompt genuinely changed, and a green shield
is the evidence that the change did not leak into the other 54 cases or into the
product gate, the grounding check or the guardrails.

An aborted earlier attempt at this run is retained as
`evals/runs/20260810T142516Z-full.ABORTED-1of55.jsonl` and renamed so it cannot be
mistaken for a result. It stopped because it was competing for the GPU with the
throughput measurements above, not because of a defect.

---

## 5. Live context, measured against the real APIs

`_context_block` on 2026-08-10, with a real Open-Meteo call:

```
--- province given ---
Tarih: Ağustos ayı, yaz.
Kullanicinin ili: Manisa.
Hava durumu: önümüzdeki hafta toplam 0.0 mm yağış bekleniyor, sıcaklık 20-38 °C aralığında.
Bitkinin fenolojik donemi bilinmiyorsa cevabinda sor (fide, cicek, meyve tutumu gibi).

--- no province given ---
Tarih: Ağustos ayı, yaz.
Kullanicinin ili BILINMIYOR - cevabinda hangi ilde oldugunu sor, tavsiyeni genel tut.
Bitkinin fenolojik donemi bilinmiyorsa cevabinda sor (fide, cicek, meyve tutumu gibi).

--- any other route ---
''
```

The weather figures are plausible for Manisa in mid-August, which is the only check
available — Open-Meteo is the source of truth here, not something this project can
verify independently.

---

## 6. What a real answer looks like

A green suite is not evidence that the output reads well. Both paths were run on
`"Manisa'dayim, domatese ne zaman gubre vermeliyim?"`.

**Non-streaming** (`answer()`), route `fert_plan` / `rule`:

> Domates bitkisinde gübreleme zamanı, bitkinin şu anki gelişim aşamasına (fenolojik
> dönemi) göre büyük farklılık gösterir. Size en doğru öneriyi sunabilmem için
> domateslerinizin şu an hangi aşamada olduğunu belirtebilir misiniz? (Örneğin; henüz
> fide aşamasında mı, çiçek açma döneminde mi, meyve tutumu mu var yoksa meyveler
> olgunlaşma evresinde mi?)
>
> Genel bir bilgilendirme yapmak gerekirse:
>
> *   **Vejetatif Dönem (Gelişim):** Bitki boy atıyor ve yaprak oluşturuyorsa azot
>     ağırlıklı besleme ön plandadır.
> *   **Çiçeklenme ve Meyve Tutumu:** Bu dönemde fosfor ve potasyum ihtiyacı artar;
>     meyve kalitesi için kalsiyum dengesi kritik önem taşır.
> *   **Meyve Olgunlaşması:** Bitki enerjisini meyveye yönlendirdiği için potasyum
>     ağırlıklı besleme tercih edilir.
>
> Manisa'daki 38 °C'ye ulaşan sıcaklıklar ve yağışsız hava durumu göz önüne
> alındığında, gübreleme yaparken bitkinin su stresine girmemesi çok önemlidir.
> Gübreleme genellikle sulama ile birlikte veya hemen sonrasında yapılmalıdır ki besin
> maddeleri kök bölgesi tarafından verimli şekilde alınabilsin. Bitkinizin aşamasını
> paylaşırsanız daha spesifik önerilerde bulunabilirim.

Products: `HIGRO DENGELİ`, `HİGRO® SPEED`, `ZİNCER`.

**Streaming** (`stream_answer()` — the path both real clients use):

> Manisa'nın Ağustos ayı sıcaklıkları ve önümüzdeki hafta beklenen kurak hava
> koşulları göz önüne alındığında, domates bitkisinin besleme programı gelişim
> aşamasına göre değişiklik gösterir. Size en doğru öneriyi sunabilmem için
> domateslerinizin şu anki fenolojik dönemini (fide, çiçeklenme, meyve tutumu veya
> meyve olgunlaşması gibi) belirtebilir misiniz?
>
> Genel bir çerçevede ise şu noktalar önemlidir:
>
> *   **Meyve Tutumu ve Gelişimi:** Eğer bitkileriniz meyve verme aşamasındaysa,
>     özellikle potasyum ağırlıklı besleme meyve kalitesini ve boyutunu artıracaktır.
> *   **Sıcaklık Stresi:** 38 °C'ye ulaşan sıcaklıklarda bitki hızlı su kaybeder; bu
>     durum besin alımını zorlaştırabilir. Bu nedenle düzenli sulama ile desteklenen
>     dengeli bir besleme kritik önem taşır.
> *   **Besleme Seçenekleri:** Bitkinin genel sağlığını ve gelişimini desteklemek için
>     **HIGRO DENGELİ** gibi dengeli çözeltiler veya hızlı gelişim dönemlerinde
>     **HİGRO® SPEED** ürünlerini inceleyebilirsiniz.
>
> Bitkilerinizin durumunu paylaşırsanız daha spesifik bir yönlendirme yapabilirim.

Event types: `['token', 'products', 'done']` — the SSE wire format is unchanged.

Against what the plan asked for, both answers:

- **use the location** — Manisa by name, and the actual forecast figures (38 °C, dry)
  rather than a generic "consider your local conditions";
- **use the season** — the streaming answer names Ağustos explicitly;
- **ask for the phenological stage** instead of assuming one;
- **do not claim a fertilization programme** and give no doses;
- **do not refuse** for the missing table row, which was the constraint that mattered
  most. The corpus answer is still there, now situated.

No framing sentence appears, which is correct: it is gated on reviewed rows actually
found for the question, and there are none.

---

## 7. Still blocked on agronomic review

`data/fertplan_table.json` is exactly `{}` and must stay that way until an
agricultural engineer reviews rows. Neither the developer nor the author of these
plans is one, and **the correctness of a fertilization calendar cannot be established
by testing** — a green suite would prove only that a wrong number was returned
reliably.

The mechanism around it all ships and is tested: rows without a `reviewed_by` field
are dropped at load time, so an unreviewed line cannot reach a user even if someone
edits the file; `detect_crop` matches against the table's own keys, so an empty table
can only return `None` and there is no second crop list to drift; and the framing
sentence is appended by code, never requested in the prompt, so no model can omit it.

**Adding a crop is therefore a review task, not a programming task.** Append rows with
`reviewed_by` filled in by the person who checked them. No code changes, no deploy.

---

## 8. Minor findings carried to the final branch review

Both are test-only and neither blocks the merge.

- `tests/test_engine.py` — the event-index ordering check for the framing sentence
  **replaced** the `endswith` check instead of joining it, so "framing is the last
  answer token" is no longer pinned. A refactor moving the framing yield above the
  blank-answer backstop would put the disclaimer in the middle of the answer and this
  test would still pass.
- `tests/test_engine.py` — the blank-answer backstop test asserts only that the
  framing is present. Changing the stub's `finish` from `"stop"` to `"length"` would
  silently move it onto a different recovery branch while staying green.

## 9. Known limits, recorded so they are not rediscovered

- **Open-Meteo is free for non-commercial use only.** This is a commercial product. A
  key must be budgeted before go-live. `src/context/weather.py` says so at the top.
- **Province extraction has spec-forced homonym collisions.** "Orduda askerlik
  yaptım" → Ordu, "Muşta dövdü adamı" → Muş. These are not substring bugs; *ordu*
  (army) and *muşta* (knuckle-duster) are real Turkish words that inflect exactly like
  a province mention, and they come from the same regex branch that makes the required
  "Vanda"/"Siirtte"/"Rizede" work. Accepted deliberately: the province feeds a weather
  lookup and one context line, not a diagnosis, and the user can correct it next turn.
  Not fixable without semantic disambiguation.
- **A cold province costs up to two sequential 2.0 s timeouts** before the first
  streamed token — geocode then forecast — on the first `fert_plan` question for that
  province per process. Cached for the process lifetime afterwards.
- **`budget` and `crop_choice` do not dispatch.** They are dispatch-safe by the wrong-
  entry measure but were deliberately left on the corpus path; they need the numeric
  data layer, which is a separate spec.
