# Product-dose route: driven for real (2026-08-25)

Task 7, Steps 1-3. The route was driven in a real browser (headless Chrome over
CDP, driving Expo web at `:8081` against uvicorn at `:8000`, no LM Studio - this
route makes no model call) rather than trusted on test output alone, because P1
and P2b both shipped a defect that every test passed and only a person driving
the app found. This run found **no such defect**: all ten checklist items in
`.superpowers/sdd/task-7-brief.md` Step 1 passed on the first pass, with no
source change required.

Two screenshots are attached: `docs/screenshots/dose-card.png` (the card, freshly
drawn under the router's own sentence) and `docs/screenshots/dose-answer.png`
(a computed answer for `HİGRO FUBBY · Sebze · 2 dönüm`).

## The routing gate, before and after

From `.superpowers/sdd/progress.md` (P3B, Task 5): wiring the `product_dose`
route moved the router's score from **37/42 to 43/48** against
`evals/run_routing`, and the reviewer re-scored the **original 42 cases in
isolation and found them unchanged** - the six new cases are the ones the dose
route itself added coverage for. `run_routing` still exits 1 on its internal
90% gate, but that is pre-existing (37/42 was already 88% before this route
existed), not a regression introduced here.

## The reviewed `hepsi` scope decision

Deferred from P3a, closed in P3B Task 1 (commit range `cafa526..fa6a4e2`) and
recorded in `data/dose_group_scope.json`. A `hepsi` row means the parser found
no group heading on the page, and that is two different facts a regex cannot
tell apart: the page named no crop at all (answers every group), or it named
crops the parser does not map to a group (answers none of them). A person
(Tunahan Yıldız, 2026-08-25) read both panels:

- **FLY AZOT** → scoped to `["tarla", "sebze"]`. Panel quote: *"Panel her rakamı
  ürün adıyla niteliyor: 'Tahıllarda ve Hububatlarda kıraç üretimde dekara 200
  cc yapraktan', 'Mısır ve Ayçiçeği', 'Pancar, patates, soğan, havuç gibi
  toprak altı yumrulu bitkilerde ... yapraktan 250 cc', 'Yeşil yapraklıların
  (marul, maydanoz, tere, roka, vb.)'. Sayfada tek bir meyve türü geçmiyor."*
  This run's checklist item 10 exercises exactly this: `FLY AZOT` + `Meyve`
  prints the no-figure refusal, not a cereal number borrowed from `hepsi`.
- **HIGRO 8 MN** → scoped to all three groups (`["sebze", "meyve", "tarla"]`).
  Panel quote: *"Panel hiçbir bitki adı vermiyor: 'DAMLAMA SULAMA: Mangan
  eksikliğinde bir dekara (1.000 m²) 2 – 2,5 litre dozunda'. Rakam bir gruba
  bağlı değil."* Here the figure genuinely is unqualified, so it answers every
  group.

## Step 1: the checklist, driven live, with evidence

Driven with a scratch CDP script (not committed - per the brief, in the
scratchpad only), same headless-Chrome/CDP mechanics as
`scripts/capture_screenshots.js`: one device-metrics session, no fixed
sleeps (waited on DOM content and, for this route, on the actual
`Network.loadingFinished` event for the `/api/chat` request - the dose route
makes no model call, so the whole round trip can finish faster than a
`readOnly` DOM-poll loop can observe the true→false edges the brief describes
for the streaming chat route).

One prerequisite the brief's two-terminal setup doesn't mention: the app now
gates every screen behind a local, on-device-only profile
(`mobile-app/src/auth.tsx` - no server call, nothing leaves the device). A
fresh browser profile lands on "Profil oluştur" before it ever reaches
`/chat`, so the drive script first created a disposable local test profile
(`task7tester` / local password, never transmitted) to get past that gate.
Not a route defect - just new since `scripts/capture_screenshots.js` was
written - noted here so a future re-run isn't surprised by it.

1. **Ask `HİGRO FUBBY dekara ne kadar kullanmalıyım?` → sentence + card.**
   PASS. Body text contained `ASK_FOR_INPUTS`'s exact sentence ("Hangi
   üründen ne kadar almanız gerektiğini hesaplayabilirim...") and the card's
   product-search input (`placeholder="Ürün arayın (örn. higro)"`) was present
   directly under it. See `dose-card.png`.
2. **Product search finds `HİGRO FUBBY` on `fubby`, `HİGRO BARF` on `barf`.**
   PASS. Typing `fubby` into the card's product field made
   `document.body.innerText` include `HİGRO FUBBY`; typing `barf` made it
   include `HİGRO BARF`.
3. **Three group buttons; pressed one filled green.** PASS. After clicking
   `Sebze`, its computed `background-color` was `rgb(96, 169, 69)` (=
   `colors.green` / `#60a945`); `Meyve` and `Tarla bitkisi` stayed
   `rgba(0, 0, 0, 0)`.
4. **`dönüm`/`hektar` switch; hektar genuinely multiplies by ten.** PASS,
   checked with real numbers rather than reading the label: `HİGRO FUBBY` ·
   `sebze` publishes 250 gr/dönüm (damlama). Area = 2 dönüm → answer contains
   "500 gr". Same product/group, area = 2 hektar → answer contains "5 kg"
   (5000 gr = 500 gr × 10, and it's the promoted unit at the 1000 g→kg
   boundary, `dose_answer._promote`). Confirms the multiplication, not just
   that the label changed.
5. **Submit → user bubble shows the entered values, not the question
   repeated.** PASS. The bubble read `HİGRO FUBBY · Sebze · 2 hektar` (the
   `DoseCard.submit()` summary), not the typed question.
6. **Answer names the method, the published dose and the total, and closes
   with both sentences.** PASS. The rendered answer contained "Damlamadan"
   (method), the published "250 gr" dose, the "5 kg" total, the attribution
   sentence ("...üreticinin yayımladığı dozdur..."), and the season refusal
   ("Doz TEK bir uygulama içindir..."). See `dose-answer.png` for the dönüm
   case (same shape).
7. **Card gone after submit; cannot be submitted twice.** PASS. After
   submitting, zero elements matched the product-search input's placeholder
   and zero elements had the exact text `Hesapla` anywhere in the DOM - there
   is nothing left to press.
8. **Reload → conversation restores with no interactive card.** PASS (after
   re-authenticating past the local-profile gate above - a full page reload
   drops the in-memory auth session, since `profile` in `auth.tsx` is React
   state, not re-derived from storage on load; the *chat* history is a
   separate `AsyncStorage` key and survives independently). Once back on the
   chat tab, both earlier product names (`HİGRO FUBBY`, `FLY AZOT`) were
   present in the restored text, and zero product-search inputs / zero
   `Hesapla` buttons existed - exactly what `chat.tsx`'s
   `messages.map(({ form, doseForm, ...rest }) => rest)` guarantees by never
   persisting `doseForm`.
9. **Submit with area empty → card returns with the area error, product and
   group still selected.** PASS. The returned card's body text included
   "Alan alanını doldurun." (`dose_answer._read_area`'s message), the
   product-search input's value was still `HİGRO FUBBY`, and `Sebze`'s
   background was still green - `form_spec`'s echo of the submitted payload
   confirmed live, not just read from source.
10. **`FLY AZOT` + `Meyve` → no published figure, no number at all.** PASS.
    The answer was exactly `no_dose_for_group`'s text: *"FLY AZOT için
    meyvede dekara bir doz yayımlanmamış. Bu ürünün sayfasında bu gruba ait
    bir rakam yok, başka bir grubun rakamını da buraya taşımıyorum."* - no
    digit anywhere in it, and (correctly, per `no_dose_for_group`'s own
    doc-comment) neither the attribution nor the season-refusal sentence is
    appended, since there is no figure for either to point at.

No item required a source fix. No new defect was found this run - unlike P1
and P2b, this pass came back clean.

## Still open (not built, named on purpose)

- **`HİGRO FERRY`'s one figure for two groups.** Its page writes "tarla ve
  endüstri bitkileri ile sebzelerde" for one figure; only "sebzelerde" opens a
  segment, so `doses.lookup("HİGRO FERRY", "tarla")` returns `()` - and the
  product appears in **neither** `unparsed` **nor** `dropped_slots` in
  `data/product_doses.json`'s meta, so nothing currently surfaces that the
  `tarla` half was silently dropped. Widening the `tarla` pattern to span
  intervening words also swallows "Tarla sebzelerinde" in `HİGRO FERFORCE`, so
  this needs a design decision, not a wider regex (per P3a's final review and
  `docs/superpowers/specs/2026-08-22-product-dose-design.md`).
- **Elemental → product mass** stays out of scope: converting a nutrient
  figure (e.g. "16 kg saf azot/dekar") into a mass of this product needs a
  guaranteed-content analysis, and only **3 of 48** panels carry an
  NPK-looking triple (7 more carry some percentage). Unchanged from the
  original P3 blocker (spec §10).
