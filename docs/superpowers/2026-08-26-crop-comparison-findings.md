# Crop comparison: driven for real (2026-08-26)

Task 6, Steps 1-3. The route was driven in a real browser (headless Chrome
over CDP, driving Expo web on `:8081` against uvicorn on `:8000`) rather than
trusted on test output alone, because P1 and P2b both shipped a defect that
every test passed and only a person driving the app found. This run found
**no such defect**: all eight checklist items in `.superpowers/sdd/task-6-brief.md`
Step 1 passed on the first pass, with no source change required.

Two screenshots are attached: `docs/screenshots/compare-card.png` (the card,
freshly drawn under the router's own sentence) and
`docs/screenshots/compare-answer.png` (a computed answer for
`Domates (Sofralık)` vs `Biber (Salçalık, Kapya)`, Konya).

## The detector against the real 187-family table (Task 1 Step 5)

Run from the repo root:

```
PYTHONIOENCODING=utf-8 python -c "
from src import crop_compare as cc
for m in ('Bu yıl domates mi biber mi ekmeliyim?',
          'Narenciye bahçesi kurmak istiyorum',
          'Tereyağı nasıl saklanır?',
          'Gülmekten karnım ağrıdı',
          'Nar mı dut mu daha kârlı?',
          'Bu yıl tarlama ne eksem iyi olur?'):
    print(f'{str(cc.named_crops(m)):40s} <- {m}')"
```

Output, over the shipped table (still 187 crop families, `data/crop_norms.json`):

```
('Domates', 'Biber')                     <- Bu yıl domates mi biber mi ekmeliyim?
()                                       <- Narenciye bahçesi kurmak istiyorum
()                                       <- Tereyağı nasıl saklanır?
()                                       <- Gülmekten karnım ağrıdı
('Nar', 'Dut')                           <- Nar mı dut mu daha kârlı?
()                                       <- Bu yıl tarlama ne eksem iyi olur?
```

The two-crop question routes correctly. All three ambush sentences that plant
a short crop name (`Nar`, `Tere`, `Gül`) inside an ordinary Turkish word
(`Narenciye`, `Tereyağı`, `Gülmekten`) come back empty — the bounded-suffix
matcher holds. The one case that DOES name two short crops deliberately
(`Nar mı dut mu`) correctly fires, which is the intended behaviour, not a
false positive: the plan's own risk note says a false positive needs TWO
ambush words in one message, and this run found none.

## The rendered answer (Task 3 Step 6)

Run from the repo root:

```
PYTHONIOENCODING=utf-8 python -c "
from src import crop_compare as cc, norms
t = norms.province_table('Konya')
i, _ = cc.validate({'first': 'domates (sofralik)', 'second': 'biber (salcalik, kapya)'}, t)
i = cc.CompareInputs(i.first, i.second, 'Konya')
print(cc.render(i, cc.compute(i, t, norms.latest_year())))"
```

Output:

```
İki ürünün yayımlanmış rakamları (Konya):

**Domates (Sofralık)** · dekara brüt gelir **115.664 TL**
   verim 5.492,1 kg/da (TÜİK 2025, Konya) × fiyat 21,06 TL/kg (TÜİK 2025)
   verimde önceki 5 yıl: 4.930,6–6.473,1 kg/da

**Biber (Salçalık, Kapya)** · dekara brüt gelir **125.841 TL**
   verim 3.154,7 kg/da (TÜİK 2025, Konya) × fiyat 39,89 TL/kg (TÜİK 2025)
   verimde önceki 5 yıl: 2.997,5–3.732,6 kg/da

Rakamlar TÜİK'in yayımladığı il ortalamalarıdır; tek bir tarlanın verimi veya
sizin alacağınız fiyat için öngörü değildir.

Bu rakamlar dekara BRÜT gelirdir, masraf içermez. İki ürünün girdi ve işçilik
masrafı aradaki farktan çok daha fazla ayrışabilir, bu yüzden kârlılık
sıralamasını bu tablodan söyleyemem. Kendi masrafınızı girerek bütçe hesabı
yaptırırsanız kâr karşılaştırmasını yapabilirsiniz.
```

This matches spec §3's worked example figure for figure (115.664 TL vs
125.841 TL, nine percent apart) and is exactly what
`docs/screenshots/compare-answer.png` shows rendered in the real app.

## Step 1: the checklist, driven live, with evidence

Driven with a scratch CDP script (not committed — per the brief, in the
scratchpad only), same headless-Chrome/CDP mechanics as
`scripts/capture_screenshots.js`: one device-metrics session, no fixed
sleeps. This route makes no model call (spec §2.5), so the same trap the
dose-route findings hit applies here too — the round trip can finish inside
a single poll gap. The script snapshots the `/api/chat`
`Network.requestWillBeSent` count **before** the triggering click/Enter and
waits for a matching `Network.loadingFinished` after that snapshot, rather
than polling the DOM's `readOnly` flag.

One mechanical trap found and fixed **in the driving script**, not the app:
the register/login screens are a scrollable `ScrollView` (a `div` with
`overflow`, not window scroll), so the submit button sits below the 812px
viewport fold and `getBoundingClientRect()` returns a real but off-screen
`y`. A click dispatched at that coordinate lands on nothing. Fixed by calling
`scrollIntoView({block:'center'})` on the matched element before reading its
rect, then constraining the accepted rect to the visible viewport. This is a
one-time driver fix — `scripts/capture_screenshots.js` never hits it because
none of its click targets are below the fold — recorded here since it cost
real debugging time and would bite the next person who copies this pattern
for a scrollable form.

A throwaway profile (`task6tester<timestamp>` / `test1234`) was created to
reach the chat screen, same local on-device auth gate as the dose-route run.
Sign-up lands on the tabs' **home** screen, not chat directly — the home
screen's own description card ("...Bitkileriniz hakkında sorularınızı
yanıtlayalım") is a near-miss substring for the chat input's placeholder, so
the script matches on the actual `<input>` element rather than body text
containing that phrase, and reaches chat via the "Asistan" tab button (a
client-side SPA transition) rather than `Page.navigate`, which would have
been a real browser reload and dropped the in-memory profile the same way
item 7 exercises deliberately.

1. **Ask `Konya'dayım, bu yıl domates mi biber mi ekmeliyim?` → sentence +
   card + province named.** PASS. Body text contained the exact
   `ASK_FOR_CROPS` sentence ("Karşılaştırayım: hangi iki ürünü
   düşünüyorsunuz? İkisini seçerseniz ilinizde yayımlanmış verim ve fiyat
   rakamlarını yan yana koyarım."), the card's two labelled rows ("Birinci
   ürün", "İkinci ürün") were present, and the card's own province line read
   exactly "Konya için yayımlanmış rakamlar". See `compare-card.png`.
2. **Typing `domates` in the first select finds both variants; picking one
   fills the box.** PASS. After typing, body text contained both
   `Domates (Sofralık)` and `Domates (Salçalık)`. After clicking
   `Domates (Sofralık)`, the first select input's `.value` read exactly
   `Domates (Sofralık)`.
3. **Submitting with only one crop chosen returns the card with the error on
   the empty select and the first choice still there.** PASS. The returned
   card's body text contained the exact field error `İkinci ürün seçin.`
   and the first select's `.value` was still `Domates (Sofralık)` —
   confirming `form_spec`'s echo of the submitted payload, not just that an
   error string appeared somewhere on the page.
4. **Picking the same crop twice returns the "iki farklı ürün" error.**
   PASS. Selecting `Domates (Sofralık)` in the second box too and
   submitting produced the exact field error
   `Karşılaştırma için iki farklı ürün seçin.`
5. **A full submit shows the user's bubble as the two crop names, then an
   answer carrying both crops' yield, price, gross revenue, the five-year
   range, and BOTH closing sentences.** PASS. The user bubble read
   `Domates (Sofralık) ↔ Biber (Salçalık, Kapya)` (the `CompareCard.submit()`
   summary, not the typed question). The answer contained
   `dekara brüt gelir` twice (once per crop), the five-year range phrase
   `önceki 5 yıl` for both crops, and both code-written sentences — `TÜİK`
   (the `ATTRIBUTION` sentence) and `kârlılık sıralamasını` (the
   `NOT_PROFIT` sentence). See `compare-answer.png`.
6. **The card is gone after submit and cannot be submitted twice.** PASS.
   After the successful submit, zero elements matched the crop-select
   input's placeholder — nothing left to press, same as the dose route's
   Task 7 finding for the identical "consumed card" pattern.
7. **After a reload the conversation restores with no interactive card.**
   PASS (after re-authenticating — a hard reload drops the in-memory
   `AuthProvider` session, same as the dose-route run: `profile` is React
   state, not re-derived from storage on load, while the chat history is a
   separate `AsyncStorage` key and survives independently). Once back on the
   chat tab, both crop names (`Domates (Sofralık)`, `Biber (Salçalık,
   Kapya)`) were present in the restored text, and zero crop-select inputs
   existed anywhere in the DOM — exactly what `chat.tsx`'s
   `messages.map(({ form, doseForm, compareForm, ...rest }) => rest)`
   guarantees by never persisting `compareForm`.
8. **Ask `Konya'dayım, bu yıl tarlama ne eksem iyi olur?` → no card.** PASS.
   Zero crop-select inputs existed anywhere in the DOM after this turn.
   LM Studio was **not running** during this session, so the response was
   the server's own connection-failure fallback text
   ("Uzgunum, su anda dil modeline ulasamiyorum...", `engine._llm_unavailable_message`)
   rather than a real factors answer — the brief calls this an acceptable
   substitute, since what matters is that no card appears, and it did not.

No item required a source fix. No new defect was found this run.

## The routing gate, before and after

`src/router.py` and `evals/routing_set.py` are absent from this branch's
diff by design — the fork lives inside `crop_choice`, never in the router
(spec §6). From `.superpowers/sdd/progress.md` (P4, Task 4): wiring the
comparison fork left routing at **46/51 unchanged**, and the reviewer
re-scored the original 42 frozen cases in isolation and found zero moved.
This driving session made no code change, so there is nothing to re-measure
here beyond confirming the diff still carries no router/eval-set edit —
which it does not (`git log` for this branch shows no commit touching either
file since `a9f41c0`).

## Still open (not built, named on purpose)

Per spec §10, two things this route deliberately does not do:

- **Ranking a province's crops.** The pitch's broadest reading, and the one
  the missing cost data cannot support — a gross-revenue ranking would tell
  every farmer to plant strawberries.
- **Profit, margin, or any cost figure.** This project holds no cost data
  anywhere. The budget form (P1/P2b), where the farmer supplies their own
  costs, is the only place a real profit comparison can happen — the
  `NOT_PROFIT` sentence points there by name.

Also unchanged from spec §10: no ranking beyond two crops, and no
prefilling the card's selects from the question's own crop names (a
convenience that needs a Turkish matcher whose wrong guesses would land on
figures — deferred to its own round if the two searches prove annoying in
practice).
