# Retrieval fragility probe — the frozen paraphrase set

**PRE-REGISTRATION. Written 2026-07-21, BEFORE the probe harness existed.**

These 54 paraphrases were authored blind: at the time of writing, no probe script
existed and not one of them had been run. That ordering is the bias control — if the
author could test a paraphrase while writing it, the measurement would record the
author's persistence rather than the system's fragility.

**The git commit timestamp of this file is the evidence that it predates the results.**
Once committed, the set is FROZEN: no paraphrase may be edited, added, or removed,
whatever the results look like.

Spec: `docs/superpowers/specs/2026-07-21-retrieval-phrasing-fragility-probe-design.md`

## Categories

Each case gets exactly three paraphrases, one per category, each targeting a distinct
plausible failure mode:

- **P1 colloquial** — short, how a grower would actually type it; academic framing dropped.
- **P2 inflected** — same question, different Turkish case/possessive/plural endings on the key nouns. This is the axis that broke the lexicon matcher.
- **P3 synonym** — a natural alternative term for the key domain concept.

## Validity rule applied to every entry

Same information need as the eval query. No paraphrase names its source document, and
none contains the value the case asserts (`answer_any`) — either would make it a
leading query and inflate the result. Checked entry by entry in Task 1 Step 4.

## Scoring

A probe is a **HIT** if any of its case's expected sources appears among the retrieved
chunks; **MISS-EMPTY** if nothing cleared the 0.36 floor; **MISS-WRONG** if chunks came
back without the expected source.

Note: four cases (`local_santamaria_pear`, `local_ankara_pear`,
`local_beurrehardy_pear`, `local_bpmorettini_pear`) share the source `dp_19393`, so
these 18 cases cover **16 distinct documents**.

---

### disease_fireblight_resistant
- **Expected sources:** `dp_1399494`
- **Eval query (control):** Ateş yanıklığı hastalığına dayanıklı armut çeşitleri hangileridir?
- **P1 colloquial:** Ateş yanıklığına dayanıklı armut var mı?
- **P2 inflected:** Armutta ateş yanıklığına dayanıklılığıyla bilinen çeşitler neler?
- **P3 synonym:** Ateş yanıklığına toleranslı armut tipleri hangileri?

### disease_rhizoctonia_biocontrol
- **Expected sources:** `dp_21748`, `dp_1004550` (any one counts as HIT)
- **Eval query (control):** Rhizoctonia solani kaynaklı kök çürüklüğüne karşı biyolojik mücadelede hangi antagonist mikroorganizmalar kullanılır?
- **P1 colloquial:** Kök çürüklüğüne karşı hangi faydalı mikroorganizmalar kullanılır?
- **P2 inflected:** Rhizoctonia solani'nin yol açtığı kök çürüklüğünde biyolojik mücadelede neler kullanılıyor?
- **P3 synonym:** Rhizoctonia kök çürüklüğüne karşı biyolojik savaşımda hangi mikrobiyal ajanlar var?

### local_deveci_pear
- **Expected sources:** `dp_21747`
- **Eval query (control):** Deveci armudu ne zaman hasat edilmeli ve soğukta ne kadar depolanabilir?
- **P1 colloquial:** Deveci armudu ne zaman toplanır, kaç ay dayanır?
- **P2 inflected:** Deveci armudunun hasadı ve soğukta saklanması nasıl olmalı?
- **P3 synonym:** Deveci armudu ne zaman derilmeli ve soğuk hava deposunda ne kadar muhafaza edilebilir?

### local_santamaria_pear
- **Expected sources:** `dp_19393`
- **Eval query (control):** Santa Maria armudu kendine verimli mi, bahçeye dölleyici çeşit dikmek gerekir mi?
- **P1 colloquial:** Santa Maria armuduna tozlayıcı gerekir mi?
- **P2 inflected:** Santa Maria armudunun bahçesinde başka bir çeşide ihtiyaç duyulur mu?
- **P3 synonym:** Santa Maria armudu kendi kendine meyve bağlar mı, yanına tozlayıcı çeşit dikmeli mi?

### local_ankara_pear
- **Expected sources:** `dp_19393`
- **Eval query (control):** Ankara armudu kendine verimli mi, bahçeye tozlayıcı çeşit dikmek gerekir mi?
- **P1 colloquial:** Ankara armuduna dölleyici lazım mı?
- **P2 inflected:** Ankara armudunun kendine verimli olup olmadığı ve tozlayıcıya ihtiyacı biliniyor mu?
- **P3 synonym:** Ankara armudu kendi kendine meyve tutar mı, dölleyici çeşit şart mı?

### local_beurrehardy_pear
- **Expected sources:** `dp_19393`
- **Eval query (control):** Beurre Hardy armudu kendine verimli mi, bahçeye tozlayıcı çeşit dikmek gerekir mi?
- **P1 colloquial:** Beurre Hardy armuduna tozlayıcı şart mı?
- **P2 inflected:** Beurre Hardy armudunun döllenmesinde başka çeşide ihtiyacı var mı?
- **P3 synonym:** Beurre Hardy armudu kendi kendine meyve bağlar mı, dölleyici gerekir mi?

### local_bpmorettini_pear
- **Expected sources:** `dp_19393`
- **Eval query (control):** B.P. Morettini armudu kendine verimli mi, bahçeye tozlayıcı çeşit dikmek gerekir mi?
- **P1 colloquial:** B.P. Morettini armuduna tozlayıcı gerekir mi?
- **P2 inflected:** B.P. Morettini armudunun bahçesinde dölleyici çeşide ihtiyaç duyulur mu?
- **P3 synonym:** B.P. Morettini armudu kendi kendine meyve bağlar mı?

### local_scarletspur_apple
- **Expected sources:** `dp_1292456`
- **Eval query (control):** Scarlet Spur elma çeşidinde kabuk yanıklığını önlemek için hasat ne zaman yapılmalıdır?
- **P1 colloquial:** Scarlet Spur elmayı ne zaman toplamalı ki kabuk yanıklığı olmasın?
- **P2 inflected:** Scarlet Spur elmasının hasadını ne zaman yaparsam kabuk yanıklığından korunurum?
- **P3 synonym:** Scarlet Spur elma çeşidinde yüzeysel kabuk lekelenmesini önlemek için derim zamanı nedir?

### local_hachiya_persimmon
- **Expected sources:** `dp_1797532`
- **Eval query (control):** Hachiya Trabzon hurması kurutulduktan sonra raf ömrünü uzatmak için hangi ön işlem uygulanmalı?
- **P1 colloquial:** Hachiya hurmasını kurutmadan önce ne yapmalı ki uzun dayansın?
- **P2 inflected:** Hachiya Trabzon hurmasının kurutulmasında raf ömrünü uzatan ön işlem nedir?
- **P3 synonym:** Hachiya cennet hurması kurutulurken hangi ön uygulama yapılır?

### local_canernar_pomegranate
- **Expected sources:** `dp_19373`
- **Eval query (control):** Canernar-1 nar tipi soğukta kaç ay süreyle depolanabilir?
- **P1 colloquial:** Canernar-1 narı soğukta ne kadar durur?
- **P2 inflected:** Canernar-1 nar tipinin soğukta depolanma süresi nedir?
- **P3 synonym:** Canernar-1 nar çeşidi soğuk hava deposunda kaç ay muhafaza edilebilir?

### local_diyarbakir_safflower
- **Expected sources:** `dp_1514564`
- **Eval query (control):** Diyarbakır koşullarında hangi aspir çeşidi önerilir?
- **P1 colloquial:** Diyarbakır'da hangi aspir ekilir?
- **P2 inflected:** Diyarbakır'ın koşullarına uygun aspir çeşidi hangisidir?
- **P3 synonym:** Diyarbakır ekolojisinde hangi aspir tipi tavsiye edilir?

### local_oltu_raspberry
- **Expected sources:** `dp_30474`
- **Eval query (control):** Erzurum Oltu yöresinde hangi ahududu çeşitleri iyi adapte olur?
- **P1 colloquial:** Oltu'da hangi ahududu yetişir?
- **P2 inflected:** Erzurum Oltu'nun koşullarına hangi ahududu çeşitleri uyum sağlar?
- **P3 synonym:** Erzurum Oltu yöresinde hangi ahududu tipleri iyi uyum gösterir?

### local_chickpea_blight_cultivars
- **Expected sources:** `dp_1559843`
- **Eval query (control):** Nohutta yanıklık hastalığına dayanıklılık bakımından hangi çeşitler öne çıkıyor?
- **P1 colloquial:** Yanıklığa dayanıklı nohut çeşidi hangisi?
- **P2 inflected:** Nohudun yanıklık hastalığına dayanıklılığında hangi çeşitler öne çıkar?
- **P3 synonym:** Nohutta antraknoz hastalığına dirençli çeşitler hangileridir?

### technique_carob_graft_diameter
- **Expected sources:** `dp_19394`
- **Eval query (control):** Keçiboynuzu (harnup) aşılamasında anaç çöğür çapı en az ne kadar olmalıdır?
- **P1 colloquial:** Keçiboynuzu aşılarken çöğürün kalınlığı ne olmalı?
- **P2 inflected:** Keçiboynuzunun aşılanmasında anacın çapı en az kaç olmalıdır?
- **P3 synonym:** Harnup aşısında anaç fidanın gövde kalınlığı asgari ne kadar olmalı?

### technique_grape_bud_load
- **Expected sources:** `dp_19531`
- **Eval query (control):** Trakya İlkeren üzüm çeşidinde en yüksek verim için asma başına kaç göz bırakılmalıdır?
- **P1 colloquial:** Trakya İlkeren'de asmaya kaç göz bırakılır?
- **P2 inflected:** Trakya İlkeren üzümünde asmanın göz yükü ne kadar olmalı?
- **P3 synonym:** Trakya İlkeren bağında en yüksek ürün için omca başına kaç tomurcuk bırakmalı?

### technique_maize_sowing_date
- **Expected sources:** `dp_21713`
- **Eval query (control):** Alaşehir koşullarında ana ürün mısırda en uygun ekim zamanı nedir?
- **P1 colloquial:** Alaşehir'de mısır ne zaman ekilir?
- **P2 inflected:** Alaşehir'in koşullarında ana ürün mısırın ekim zamanı nedir?
- **P3 synonym:** Alaşehir'de birinci ürün mısır için en uygun tohumlama tarihi nedir?

### quant_wheat_nitrogen_dose
- **Expected sources:** `dp_21735`
- **Eval query (control):** Ekmeklik buğdayda yüksek ve ekonomik tane verimi için dekara kaç kilogram saf azot uygulanmalıdır?
- **P1 colloquial:** Ekmeklik buğdaya dekara kaç kilo azot atmalı?
- **P2 inflected:** Ekmeklik buğdayın dekarına uygulanacak saf azot miktarı nedir?
- **P3 synonym:** Ekmeklik buğdayda iyi ve kârlı tane verimi için dekara ne kadar saf azot verilmeli?

### quant_mera_nitrogen_dose
- **Expected sources:** `dp_30475`
- **Eval query (control):** Meranın otlatma kapasitesini artırmak için dekara kaç kilogram azotlu gübre uygulanmalıdır?
- **P1 colloquial:** Meraya dekara kaç kilo azot gübresi atılır?
- **P2 inflected:** Meranın otlatma kapasitesinin artırılması için dekarına ne kadar azotlu gübre gerekir?
- **P3 synonym:** Meranın hayvan taşıma kapasitesini yükseltmek için dekara ne kadar azotlu gübre uygulanır?
