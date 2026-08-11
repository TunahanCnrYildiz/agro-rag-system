# Context and fertplan — gate results

Plan: `docs/superpowers/plans/2026-08-10-context-and-fertplan.md`
Spec: `docs/superpowers/specs/2026-08-09-routing-and-context-design.md`
Branch: `context-and-fertplan`, head `6a396fa` + the post-review fixes

This is the first plan in which a route changes what a user receives. `fert_plan`
answers now carry the user's province, the month and season, and the coming week's
weather. The fertilization table that would turn that into a calendar ships **empty**
and stays empty until an agricultural engineer reviews rows.

---

## 1. Environment — a SECOND slowdown fault, with a different cause and a different fix

This project already had a documented throughput fault: model layers spill from VRAM
to system RAM, throughput drops ~8×, and the fix is to eject and reload the model
(2026-07-28, and again in the routing-foundation findings). **What happened here was
not that fault, and that fix did not work.** Both are recorded because telling them
apart is what saves the next day.

Every lever, in the order pulled, each measured:

| Lever | tok/s | Verdict |
|---|---|---|
| — (as found) | 8.1 | |
| `lms unload` + `lms load` — the documented remedy | 13.7 | partial, did not hold |
| Runtime switched to ROCm, then back | 14.4 | see the caveat below — **not a valid comparison** |
| Closed all other apps (free RAM 5.9 → 19.8 GB) | 14.4 | no change |
| Restarted LM Studio | 9.5, then 16.4 | unstable, no fix |
| **Rebooted the machine** | **66.2** | **fixed** |

**Reboot was the fix. Nothing short of it worked.**

### How this fault differs from the documented one

- **It is not a VRAM spill.** `Get-Counter '\GPU Process Memory(*)\Shared Usage'` —
  the counter the routing-foundation findings named as the discriminator and did not
  run — shows `llama-server` holding **8.57 GB dedicated (VRAM) against 0.9 GB shared
  (system RAM)**. That is one reading, taken while the machine was slow; it says the
  model was resident *then*, not across the whole period. Note also that "under the
  documented spill fault this number is large" is theory — this project has never
  actually taken the reading during a confirmed spill, so the discriminator proposed
  below is a reasonable one, not a validated one.
- **It is not a CPU fallback.** During generation the GPU compute engine sat at
  **90.3%** while the CPU sat at 57%. The work was on the GPU, and the GPU was busy —
  just slow per token.
- **The runtime comparison was botched and proves nothing.** ROCm was selected
  mid-session and switched back before the timings were repeated, and which engine was
  active for which measurement was never recorded — `lms runtime ls` was only run at
  the end, by which point Vulkan 2.28.2 was selected. So "Vulkan 13.65 vs ROCm 14.4"
  is not a comparison; both figures may be the same engine. What the numbers do show
  is that **nothing in that whole 13–16 tok/s band mattered** — the reboot is what
  moved it, from 16.4 to 66.2. The project's standing note against switching runtimes
  to chase speed is still the right advice; this session did not add evidence for it,
  and claiming otherwise in an earlier draft of this document was wrong.
- **It is not host-memory pressure or background load.** Closing BlueStacks and the
  browser took free RAM from 5.9 GB to 19.8 GB and dropped `llama-server`'s host
  working set from 11.2 GB to 1.33 GB. Throughput did not move.

### What it appears to be

Accumulated GPU driver / WDDM memory-manager state. The corroborating observation:
`AMDRSServ` — the AMD Radeon Software **system service** — reported **27.49 GB** of
dedicated GPU memory on a 16 GB card. Once the committed total across processes
exceeds physical VRAM the driver must evict and page, which produces exactly the
signature seen: GPU busy, model resident, throughput a quarter of normal. That
service is not restarted by restarting LM Studio, which is why every user-space
lever failed.

This is the mechanism the evidence points to, not a mechanism that was proven —
the counter reading and the reboot result are the measurements; the causal link
between them is inference. Recorded at that strength deliberately.

### The independent confirmation

Two full 55-case eval runs of identical work, same model
(`local:google/gemma-4-12b-qat` in both jsonl headers), same answer lengths (~900
characters mean):

| Run | Median seconds per case |
|---|---|
| 2026-08-09 22:47 | **24 s** |
| 2026-08-10 14:45 | **68 s** |

A 2.8× regression on identical work. A code change *can* produce 2.8× in general —
longer prompts, a different `k`, more retrieved context — so the comparison only
carries here because **zero of the 55 eval cases route to `fert_plan`** (measured:
`{plant_info: 40, nutrition: 13, offscope: 2}`). This branch therefore adds nothing
to any of the 55 prompts, which is what makes the two runs the same work. That is the
clause the argument rests on.

The `66.2` figure is the median of the last four of five consecutive 400-token
completions, warm-up excluded (58.8 / 66.2 / 66.0 / 66.2 / 66.2).

### For next time

**If throughput is low, check `\GPU Process Memory(*)\Shared Usage` first.** A large
shared figure means the documented spill fault — eject and reload the model. A small
one (like the 0.9 GB here) means this second fault, and **the only fix measured to
work is a full reboot.** Do not spend the afternoon on runtimes and background apps;
this session did, and the measurements above are what that afternoon bought.

The plan's own gate for this step is "verify above 40 tok/s". After the reboot it is
met at 66.2. All gates below were re-run at that speed.

---

## 2. Unit suite

```
PYTHONIOENCODING=utf-8 python -m pytest -q
451 passed
```

Baseline at the start of this plan was 334. The plan added 117 tests across eight
tasks plus the post-review fixes.

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

The full run was made twice, once before the reboot and once after. **Both are
reported.**

```
# 14.4 tok/s, before the reboot
=== 55/55 cases passed ===
  retrieval: 55/55 | context: 55/55 | product-gating: 55/55 | grounding: 55/55 | guardrail: 55/55
  -> evals/runs/20260810T144554Z-full.jsonl

# 66.2 tok/s, after the reboot
=== 54/55 cases passed ===
  retrieval: 55/55 | context: 55/55 | product-gating: 55/55 | grounding: 54/55 | guardrail: 55/55
  -> evals/runs/20260811T084737Z-full.jsonl
```

### The red, and why it is not a regression from this branch

`local_bpmorettini_pear` lost grounding in the second run. Escalated **once** at
`--repeat 8`, per the two-stage rule — and the verdict stands both ways, no re-running
until green:

```
[FAIL] local_bpmorettini_pear  ret=True ctx=True prod=8/8 ground=6/8 guard=8/8
```

**As a gate this is a fail and it is recorded as one.** What it is not is a
consequence of this branch, and that was measured rather than assumed:

```
ROUTE                : plant_info / default
CONTEXT BLOCK        : ''
FRAMING SUFFIX       : ''
PROMPT IDENTICAL TO PRE-BRANCH: True
```

The case is on `plant_info`, so `_context_block` returns `""`, and the message list
this branch builds is **byte-identical** to the one it built before the branch (pinned
by `test_build_messages_without_a_block_is_unchanged`, not just by this one probe).
There is no mechanism by which **this branch's code** could have changed the answer.
That is deliberately narrower than "nothing changed": the runtime and driver state
were not controlled between the two runs — see §1 — and a different backend can change
numerics and therefore which tokens get sampled at `temperature=0.4`.

What it is instead: this case's grounding is intermittent. It was pooled at **23/25
(~0.92)** on 2026-07-29, and the project's own notes record that two of its runs then
read **6/8 and 8/8**, with the explicit warning that either alone would mislead
("weak guard at 0.75" / "perfect at 1.0"). Today's 6/8 is one of those two readings —
and at p = 0.92, P(X ≤ 6 | n = 8) ≈ **0.13**, so this reading is not distinguishable
from the historical rate. That is positive evidence for "intermittent", not merely an
absence of evidence for "regressed".
Reading the answer confirms the mode: the model answers the pollination question
correctly but qualitatively ("yıllara ve çeşide göre değişen oranlarda") instead of
carrying the source's figure.

Both runs used the same model (`local:google/gemma-4-12b-qat`, recorded in both jsonl
headers). The active runtime at the time of each run was not recorded — see §1 — so
that variable is uncontrolled between them. It does not change the conclusion, which
rests on the prompt being byte-identical, not on the two runs being comparable.

The `--fast` shield passed 55/55 in both configurations.

An aborted earlier attempt is retained as
`evals/runs/20260810T142516Z-full.ABORTED-1of55.jsonl`, renamed so it cannot be
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

**But the table is not yet wired to do anything useful, and an earlier draft of this
document said otherwise.** Correcting that here, because it is the sentence a
non-programmer would act on:

- The only consumer of `fertplan.lookup()` is the framing gate. **Row content —
  `stage`, `note` — never reaches the prompt.** The calendar assembly this plan's goal
  describes ("adds a calendar only for crops whose table rows have passed agronomic
  review") is **not implemented**.
- So adding one reviewed row today produces exactly one user-visible change: the
  disclaimer "Bu program bir tahmindir" appended to an answer that still contains no
  programme. That reads worse than not having the row.
- `_load` is `@lru_cache(maxsize=1)`, so even that change needs a process restart. It
  is not a live data edit.

**Do not add rows to the table until the assembly step exists.** Adding a crop will
become a review task rather than a programming task once it does; it is not one yet.
The review gate, the drop-unreviewed-rows rule and the framing sentence are the parts
that are finished.

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
- **A bare province name is no longer evidence of location, and that costs recall.**
  Requiring a case suffix is what stops `Trabzon hurması`, but it also drops any
  phrasing that puts an unmarked province before a noun. A whitelist of place nouns
  (`il`, `bölge`, `yöre`, `civar`, `koşul`, `taraf`, `ilçe`, `ova`, `havza`) rescues
  the common ones — "Diyarbakır koşullarında", "Antalya bölgesinde" — but
  province + district ("Manisa Salihli'de") is still missed. **This trade is
  deliberate:** a missed province makes the assistant ask, which the user recovers
  from in one turn; a wrong province produced confidently wrong weather, which they
  cannot detect at all.
- **The collision problem is closed for ONE branch of the regex, not in general.**
  Ordinary Turkish words that are a province plus a legal case suffix still resolve:
  `kilise` (church) → Kilis, `hataya` (mistake) → Hatay, **`mersini` (myrtle — a
  plant, in a plant assistant) → Mersin**, `tokatı` → Tokat, `sıvası` → Sivas. Same
  harm shape as the produce names, lower frequency, and **pre-existing rather than
  introduced here**, which is why it was not treated as blocking. Do not read the
  produce-name fix as having solved province matching.
- **A one-word user turn is read as a province regardless of what was asked.**
  `_find` sees one turn at a time, so an assistant question about which *plant* the
  user means, answered "Mersin" (myrtle), yields the province Mersin. The
  whole-message rule's stated rationale ("the natural reply to *hangi ildesiniz?*")
  does not actually hold; it is a heuristic that happens to be right most of the time.
