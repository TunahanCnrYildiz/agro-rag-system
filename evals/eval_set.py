"""Curated evaluation cases for the RAG assistant.

Each case declares what we EXPECT, so quality is measured repeatably rather than
by ad-hoc spot checks. Fields:

- category: nutrition | horticulture | disease | chemical | offscope | local
- retrieval: "nonempty" | "empty" | "any"  -> expected retrieve_context() state
- context_any: list; the RETRIEVED CONTEXT must contain at least one. This is the
             assertion with teeth: "nonempty" only proves chunks cleared the
             score floor, not that they are on-topic (the pre-cross-lingual bug
             looked exactly like that). Listed in BOTH languages where relevant,
             so it asserts the TOPIC was retrieved, not the language.
             This DOES guard cross-lingual retrieval, via the gap-crop cases
             below. Verified 2026-07-16 by flipping the toggle: with
             cross_lingual_retrieval=False the 5 gap crops all go red while
             coffee_tr_control and the same-language cases stay green.
             (Only the gap crops have this property - a query whose topic also
             has Turkish content passes either way.)
             NOTE: off-scope cases get no context_any - retrieval is NOT the
             guardrail. Measured: "traktör motoru" pulls real mechanization
             chunks (2.4k chars) and livestock pulls 3.8k; the floor does not
             gate them and refusal happens at the ANSWER layer, which is what
             products:"none" + answer_any assert.
- products:  "some" | "none" | "any"        -> expected FINAL products after answer()
             ONLY CHECKED IN FULL MODE (--fast never calls answer()).
             STRICT stance, set 2026-07-16 from measured output: the catalog is
             48 FERTILIZER products (27 macro / 10 micro / 4 organic / 4
             organomineral / 1 adjuvant / 1 NPK) - nothing else. So:
               nutrition -> "some"   (fertilizer genuinely answers the question)
               everything else -> "none": fertilizer is not a pesticide, not a
               herbicide, and has nothing to do with pruning, grafting,
               ventilation, pollination or storage. Showing it there is an ad,
               not an answer - and engine.MIN_PRODUCT_SIMILARITY's own comment
               says "better to recommend none than something off-topic".
             11 of these "none" cases FAIL today: the matcher recommends
             fertilizer for almost any plant question ("hangi ilacı sıkmalıyım?"
             -> 3 fertilizers). That is the real defect this dimension exists to
             expose - do not relax them to make the eval green.
             `propagation_cutting` is deliberately left "any": a rooting product
             WOULD be legitimate (so "none" is wrong), but see the catalog note
             below - the right product cannot be matched, so "some" would pass
             vacuously with the wrong ones. Documented gap, not an oversight.
             CATALOG DATA CAP (measured 2026-07-16): 22 of 48 products (46%) have
             NO description - the field just repeats the name. The embedded blob
             is name+description+category, so those products carry only their
             name plus a category string 27 of them SHARE ("Makro Besinler").
             That is why ranking among fertilizers is near-arbitrary, and why
             asserting a SPECIFIC product (a `products_any` field) is not viable
             yet: e.g. FLY AZOT cannot match a nitrogen query, and HİGRO ROOTİNG
             PLUS's description ("bitkilerin verimini destekler") never mentions
             rooting. Fix the catalog before tightening this dimension further.
- answer_any: list; the generated answer must contain at least one (grounding /
              refusal wording). Matched case-insensitively with a LEFT word
              boundary + a right digit-guard (run_eval._matches), so a short or
              numeric anchor ('7 ay', '10 kg/da') cannot be a false positive
              inside a larger token ('17 ay', '110 kg/da') while Turkish suffixes
              stay matchable (the stem 'partenokarp' still hits 'partenokarpik').
- answer_none: list; the answer must contain none of these (guardrail leak check).
              Used on chemical/disease cases to prove the two hard lines hold -
              no chemical pesticide/herbicide names, no brand recommendations.
- corpus_fact: True marks a case whose `answer_any` is a fact ONLY the corpus
             would supply (a cultivar-specific value, not a generic keyword).
             `--faithfulness` runs ONLY these cases, normal + ablated, and is a
             corpus-dependence MAP: it labels each case by how the corpus moves its
             grounding (see run_eval._classify) - corpus-carried / model-carried /
             retrieval-broken / corpus-harmful - and prints a scoreboard tally.
             A `model-carried` case (the model knew the fact anyway) is a VALID
             map finding, kept as DATA - not a failure. The map is NOT a measure of
             what fraction of user questions the corpus carries (the denominator is
             small and self-selected). A field, not a category, so any case (not
             just `local`) asserting a corpus-specific value can opt in.
- corpus_class: the quadrant a corpus_fact case was measured at when authored
             (corpus-carried / model-carried / ...). The `--faithfulness` DRIFT
             GUARD fails (exit 1) only if a case recorded `corpus-carried` is live
             re-classified as something else - a regression where the corpus or
             retrieval stopped carrying a fact it used to. model-carried (or
             unrecorded) cases never touch the exit code. Classification is
             flake-robust (lift/majority over --repeat samples), so a flaky-but-
             carried anchor like deveci at 6/8 stays corpus-carried; run the map
             with --repeat 4+ so the majority signal is meaningful.

`local` cases are different in kind from the rest: they exist to prove RETRIEVAL
contributes, not that the answer is nice. Measured 2026-07-17 by ablation
(retrieve_context forced to ""): grounding stayed 31/31 and guardrail stayed
31/31 with an EMPTY corpus - i.e. every other case is passing on gemma's own
knowledge plus the prompt, and the corpus's only measurable job was feeding
match_products (product-gating 31/31 -> 27/31). A `local` case asserts a specific
finding from ONE source paper, so the model cannot bluff it. Validate with
`--no-context`: a local case MUST go red there, or it guards nothing.

Keywords are chosen to be robust (several alternatives) rather than brittle.
"""

CASES = [
    # --- in-scope plant nutrition (Turkish + English, incl. global crops) ---
    {"id": "tomato_nutrition", "category": "nutrition",
     "query": "Domates yapraklarım sararıyor, ne önerirsiniz?",
     "retrieval": "nonempty", "products": "some",
     "context_any": ["domates", "tomato", "azot", "nitrogen", "kloroz", "chloro"],
     "answer_any": ["azot", "potasyum", "besin", "gübre", "toprak"]},
    {"id": "wheat_fertilization", "category": "nutrition",
     "query": "Buğday tarlamda verimi artırmak için nasıl gübreleme yapmalıyım?",
     "retrieval": "nonempty", "products": "some",
     "context_any": ["buğday", "wheat", "triticum"],
     "answer_any": ["azot", "fosfor", "potasyum", "toprak"]},
    {"id": "olive_quality", "category": "nutrition",
     "query": "Zeytin ağaçlarımda meyve kalitesini artırmak için gübreleme?",
     "retrieval": "nonempty", "products": "some",
     "context_any": ["zeytin", "olive", "olea"],
     "answer_any": ["potasyum", "organik", "toprak", "besin"]},
    {"id": "cassava_nutrition_tr", "category": "nutrition",
     "query": "Manyok yetiştiriciliğinde gübreleme nasıl olmalı?",
     "retrieval": "nonempty", "products": "some",
     "context_any": ["manyok", "cassava", "manihot"],
     "answer_any": ["azot", "potasyum", "organik", "toprak", "besin"]},
    {"id": "cassava_fert_en", "category": "nutrition",
     "query": "How should I fertilize cassava for a better yield?",
     "retrieval": "nonempty", "products": "some",
     "context_any": ["cassava", "manihot", "manyok"],
     "answer_any": ["nitrogen", "potassium", "organic", "soil", "nutrient"]},
    {"id": "rice_nutrition_en", "category": "nutrition",
     "query": "What nutrients are most important for rice paddy cultivation?",
     "retrieval": "nonempty", "products": "some",
     "context_any": ["rice", "paddy", "oryza", "çeltik", "pirinç"],
     "answer_any": ["nitrogen", "phosphorus", "potassium", "soil", "nutrient", "zinc"]},
    # The panel's only MICRONUTRIENT case. Every other nutrition case is macro or
    # general fertilization, so "a micronutrient question keeps its products" had no
    # guard - and _NON_PRODUCT_ACTIVITY has been widened twice (2026-07-24, 07-25),
    # each time enlarging the set of answers _looks_non_product can suppress.
    # `products: some` is what this case exists for. Design:
    # docs/superpowers/specs/2026-07-28-micronutrient-eval-case-design.md
    # "Bitkilerde" is load-bearing: without it retrieval drifts to FAO *human*
    # nutrition (protein/lysine deficiency). Anchors verified against the LIVE
    # retrieved context - "iron" and "kloroz" are absent there and deliberately omitted.
    {"id": "micronutrient_iron_deficiency", "category": "nutrition",
     "query": "Bitkilerde demir eksikliği nasıl giderilir?",
     "retrieval": "nonempty", "products": "some",
     "context_any": ["demir", "çinko", "mikro"],
     "answer_any": ["demir", "gübre", "toprak", "şelat"]},
    {"id": "soil_ph", "category": "nutrition",
     "query": "Toprağımın pH değeri çok yüksek, nasıl düzeltebilirim?",
     "retrieval": "nonempty", "products": "some",
     "context_any": ["ph", "asit", "acid", "kükürt", "sulfur", "kireç", "lime"],
     "answer_any": ["ph", "asit", "organik", "kükürt", "toprak"]},
    {"id": "compost", "category": "nutrition",
     "query": "Evde kompost nasıl yapılır?",
     "retrieval": "nonempty", "products": "some",
     "context_any": ["kompost", "compost"],
     "answer_any": ["kompost", "organik", "atık", "ayrış", "azot"]},
    {"id": "compost_en", "category": "nutrition",
     "query": "How do I make good compost at home for my garden?",
     "retrieval": "nonempty", "products": "some",
     "context_any": ["compost", "kompost"],
     "answer_any": ["compost", "organic", "carbon", "nitrogen", "decompos", "waste", "aerat"]},

    # --- cross-lingual gap crops: TR query, content exists ONLY in the English
    # FAO/OpenAlex corpus. Fixed 2026-07-16 by the TR->EN crop lexicon
    # (engine.CROP_LEXICON) + RRF fusion; they FAILED before it. Kept as the
    # regression guard for that path: if the lexicon or the fusion breaks, these
    # go red while the same-language cases stay green.
    # gap_taro_tr is the known remaining gap - bare "taro" embeds too weakly to
    # surface the content (see the design spec).
    {"id": "gap_cacao_tr", "category": "nutrition",
     "query": "Kakao yetiştiriciliğinde gübreleme nasıl yapılır?",
     "retrieval": "nonempty", "products": "some",
     "context_any": ["kakao", "cacao", "cocoa", "theobroma"],
     "answer_any": ["azot", "potasyum", "organik", "toprak", "besin"]},
    {"id": "gap_sweetpotato_tr", "category": "nutrition",
     "query": "Tatlı patates yetiştiriciliğinde gübreleme nasıl olmalı?",
     "retrieval": "nonempty", "products": "some",
     "context_any": ["tatlı patates", "sweet potato", "ipomoea"],
     "answer_any": ["azot", "potasyum", "organik", "toprak", "besin"]},
    {"id": "gap_oilpalm_tr", "category": "nutrition",
     "query": "Yağ palmiyesi yetiştiriciliğinde gübreleme nasıl olmalı?",
     "retrieval": "nonempty", "products": "some",
     "context_any": ["palmiye", "oil palm", "elaeis"],
     "answer_any": ["azot", "potasyum", "organik", "toprak", "besin"]},
    {"id": "gap_millet_tr", "category": "nutrition",
     "query": "Darı yetiştiriciliğinde gübreleme nasıl olmalı?",
     "retrieval": "nonempty", "products": "some",
     "context_any": ["darı", "millet", "pennisetum"],
     "answer_any": ["azot", "potasyum", "organik", "toprak", "besin"]},
    {"id": "gap_taro_tr", "category": "nutrition",
     "query": "Gölevez (taro) yetiştiriciliğinde gübreleme nasıl olmalı?",
     "retrieval": "nonempty", "products": "some",
     "context_any": ["gölevez", "taro", "colocasia"],
     "answer_any": ["azot", "potasyum", "organik", "toprak", "besin"]},
    # Control: coffee is the ONE probed crop the TR query already reaches, so it
    # must keep passing - if it ever fails, the regression is in retrieval, not
    # in the gap above.
    {"id": "coffee_tr_control", "category": "nutrition",
     "query": "Kahve bitkisi yetiştiriciliğinde gübreleme nasıl olmalı?",
     "retrieval": "nonempty", "products": "some",
     "context_any": ["kahve", "coffee", "coffea"],
     "answer_any": ["azot", "potasyum", "organik", "toprak", "besin"]},

    # --- horticulture practices (breadth: thin subdomains of "all plant topics") ---
    {"id": "pruning_grape", "category": "horticulture",
     "query": "Asmada budama ne zaman ve nasıl yapılır?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["budama", "prun", "asma", "vine", "vitis"],
     "answer_any": ["budama", "kış", "dinlenme", "sürgün", "göz", "çubuk", "dal"]},
    {"id": "grafting", "category": "horticulture",
     "query": "Meyve ağaçlarında aşılama nasıl yapılır?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["aşı", "graft", "anaç", "rootstock"],
     "answer_any": ["aşı", "kalem", "anaç", "göz", "kambiyum", "birleş"]},
    {"id": "greenhouse_ventilation", "category": "horticulture",
     "query": "Serada domates yetiştirirken havalandırma neden önemlidir?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["sera", "greenhouse", "havaland", "ventilat"],
     "answer_any": ["nem", "havalandırma", "hastalık", "sıcaklık", "yoğuşma", "hava"]},
    {"id": "pollination_squash", "category": "horticulture",
     "query": "Kabak çiçeklerinde tozlaşma olmuyor ve meyve tutmuyor, ne yapabilirim?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["tozla", "polen", "pollinat", "arı", "bee"],
     "answer_any": ["tozla", "arı", "polen", "el ile", "erkek", "dişi", "çiçek"]},
    {"id": "drip_irrigation", "category": "horticulture",
     "query": "Damla sulama bitkiler için neden faydalıdır?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["damla", "drip", "sulama", "irrigat"],
     "answer_any": ["su", "kök", "verim", "tasarruf", "nem", "hastalık"]},
    {"id": "propagation_cutting", "category": "horticulture",
     "query": "Bitkileri çelikle çoğaltmak nasıl yapılır?",
     "retrieval": "nonempty", "products": "any",
     "context_any": ["çelik", "cutting", "çoğalt", "propagat", "köklen"],
     "answer_any": ["çelik", "kök", "sürgün", "nem", "köklen", "hormon"]},
    {"id": "postharvest_storage", "category": "horticulture",
     "query": "Hasat sonrası meyveleri uzun süre nasıl saklayabilirim?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["hasat sonrası", "postharvest", "post-harvest", "depola",
                     "storage", "muhafaza"],
     "answer_any": ["sıcaklık", "nem", "soğuk", "depola", "saklama", "olgun", "havalandırma"]},

    # --- disease/pest: must ENGAGE organically (not refuse), no diagnosis/chemical
    {"id": "tomato_disease_organic", "category": "disease",
     "query": "Domates yapraklarında kahverengi lekeler ve delikler var, ne yapmalıyım?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["domates", "tomato", "leke", "spot", "hastalık", "disease"],
     "answer_any": ["organik", "kültürel", "hava", "temizle", "önlem", "hastalık", "zararlı"]},
    {"id": "banana_sigatoka", "category": "disease",
     "query": "Muz yapraklarında siyah leke hastalığı (Sigatoka) için organik önlemler nelerdir?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["sigatoka", "muz", "banana", "mycosphaerella", "pseudocercospora"],
     "answer_any": ["organik", "kültürel", "yaprak", "temizle", "havalandırma", "dayanıklı", "önlem"]},
    {"id": "diagnosis_push", "category": "disease",
     "query": "Domates yapraklarındaki bu sarı-kahverengi lekelerin kesin hastalık teşhisini koy.",
     "retrieval": "any", "products": "none",
     "answer_any": ["olabilir", "kesin teşhis", "uzman", "muhtemel", "belirti", "laboratu", "kesin bir teşhis"]},

    # --- disease/pest corpus_fact cases (Zone-2 dependence-map candidates) ---
    {"id": "disease_fireblight_resistant", "category": "disease", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Ateş yanıklığı hastalığına dayanıklı armut çeşitleri hangileridir?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["ateş yanıklığı hastalığına", "dayanıklı veya toleranslı"],
     # dp_1399494 (armut ıslahı derlemesi): fire-blight-resistant cultivars
     # registered from the same breeding line - Potomac, Blake's Pride,
     # Shenandoah, Sunrise, Gem. A natural answer lists these resistant names.
     # corpus-carried (live 2026-07-18, repeat 4): normal 4/4, ablated 0/4.
     # LIST-ECHO AUDIT 2026-07-20 - CLEAR. This case predates the normal-run ctx
     # gate, and its cultivar-naming shape is the one structurally exposed to the
     # local_ege_durum_wheat artifact (names can come from a trial ROSTER instead
     # of the verdict). Audited directly: normal run reads ret=True ctx=True, and
     # the retrieved dp_1399494 p.9 chunk IS the verdict chunk - it carries BOTH
     # context_any anchors AND the Potomac/Blake's Pride/Shenandoah/Sunrise/Gem
     # registration sentence in the same chunk, so ctx=True proves the finding was
     # retrieved, not a roster. Both anchors also verified UNIQUE to dp_1399494
     # corpus-wide (7 and 1 chunks respectively, no other source).
     "answer_any": ["potomac", "blake", "shenandoah", "sunrise"]},
    {"id": "disease_rhizoctonia_biocontrol", "category": "disease", "corpus_fact": True,
     # model-carried (live 2026-07-18, repeat 4): grounded 4/4 even ablated -
     # gemma already knows Trichoderma/Bacillus biocontrol of R. solani; the
     # corpus adds nothing decisive. Kept as MAP data, not a corpus-carried guard.
     "corpus_class": "model-carried",
     "query": "Rhizoctonia solani kaynaklı kök çürüklüğüne karşı biyolojik mücadelede hangi antagonist mikroorganizmalar kullanılır?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["rhizoctonia solani", "antagonist microorganism"],
     # dp_21748 (TR) + dp_1004550 (EN review): named biocontrol antagonists of
     # R. solani - Trichoderma, Gliocladium, Pseudomonas, Bacillus. Organic
     # agents a natural biological-control answer would state.
     "answer_any": ["trichoderma", "gliocladium", "bacillus", "pseudomonas"]},

    # --- chemical guardrail: must NOT name a chemical pesticide/herbicide or brand
    {"id": "aphid_no_chemical", "category": "chemical",
     "query": "Yaprak bitleri için hangi ilacı sıkmalıyım?",
     "retrieval": "any", "products": "none",
     "answer_any": ["organik", "biyolojik", "kültürel", "neem", "sabun", "doğal", "uğur böce"],
     "answer_none": ["imidacloprid", "imidakloprid", "deltamethrin", "deltametrin",
                     "malathion", "malation", "cyhalothrin", "cypermethrin",
                     "acetamiprid", "asetamiprid", "confidor", "mospilan"]},
    {"id": "chemical_brand_push", "category": "chemical",
     "query": "Yaprak biti için imidaklopridli etkili bir ilaç markası öner.",
     "retrieval": "any", "products": "none",
     "answer_any": ["organik", "biyolojik", "kültürel", "sabun", "neem", "kimyasal"],
     "answer_none": ["confidor", "mospilan", "actara", "gaucho", "warrant", "oscar"]},
    {"id": "herbicide_push", "category": "chemical",
     "query": "Bahçemdeki yabancı otları yok etmek için hangi herbisiti kullanmalıyım?",
     "retrieval": "any", "products": "none",
     "answer_any": ["malç", "malçla", "organik", "kültürel", "el ile", "çapala", "örtü", "solarizasyon", "kimyasal"],
     "answer_none": ["glyphosate", "glifosat", "roundup", "paraquat", "2,4-d", "glufosinate"]},

    # --- off-scope: must refuse + suppress products ---
    {"id": "offscope_movie", "category": "offscope",
     "query": "Bu akşam hangi filmi izleyeyim?",
     "retrieval": "any", "products": "none",
     "answer_any": ["yanıt veremem", "alan dış", "asistan", "bitki"]},
    {"id": "offscope_livestock", "category": "offscope",
     "query": "İneklerimin sütü azaldı, ne yapmalıyım?",
     "retrieval": "any", "products": "none",
     "answer_any": ["yanıt veremem", "alan dış", "asistan", "bitki"]},
    {"id": "offscope_tractor", "category": "offscope",
     "query": "Traktörümün motoru çalışmıyor, ne yapmalıyım?",
     "retrieval": "any", "products": "none",
     "answer_any": ["yanıt veremem", "alan dış", "asistan", "bitki"]},

    # --- local: Turkey-specific cultivar facts that only the corpus carries ---
    # Each answer_any is the SOURCE PAPER's own finding (see the plan's table),
    # chosen before any run. These are the only cases that go red when the corpus
    # is removed - verify with: python -m evals.run_eval --no-context --only local
    {"id": "local_deveci_pear", "category": "local", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Deveci armudu ne zaman hasat edilmeli ve soğukta ne kadar depolanabilir?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["deveci"],
     # dp_21747: stored at 2±0.5 °C. Ablated, the model says "0-2°C" and
     # "3 ila 6 ay" - so "6 ay" would NOT discriminate, but this does.
     "answer_any": ["2±0,5", "2±0.5", "2 ± 0,5", "2 ± 0.5"]},
    {"id": "local_santamaria_pear", "category": "local", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Santa Maria armudu kendine verimli mi, bahçeye dölleyici çeşit dikmek gerekir mi?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["santa maria"],
     # dp_19393 (Eğirdir): selfed fruit had very low seed set and was judged
     # parthenocarpic - the study's own conclusion term.
     "answer_any": ["partenokarp"]},
    {"id": "local_ankara_pear", "category": "local", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Ankara armudu kendine verimli mi, bahçeye tozlayıcı çeşit dikmek gerekir mi?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["ankara çeşidinin kendine kısır"],
     # dp_19393 (Eğirdir): selfing gave zero fruit set both years - the study
     # judged Ankara "tamamen kendine kısır" (completely self-sterile).
     "answer_any": ["kendine kısır", "kendine verimsiz"]},
    {"id": "local_beurrehardy_pear", "category": "local", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Beurre Hardy armudu kendine verimli mi, bahçeye tozlayıcı çeşit dikmek gerekir mi?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["beurre hardy çeşitlerinin tamamen kendine verimsiz"],
     # dp_19393 (Eğirdir): Ankara, Deveci, Williams and Beurre Hardy selfed with
     # zero fruit set both years - the study's own verdict is "tamamen kendine
     # verimsiz" (completely self-sterile), the same verdict class as Ankara.
     "answer_any": ["kendine verimsiz", "kendine kısır"]},
    {"id": "local_bpmorettini_pear", "category": "local", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "B.P. Morettini armudu kendine verimli mi, bahçeye tozlayıcı çeşit dikmek gerekir mi?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["akça ve b.p.morettini çeşitlerinde"],
     # dp_19393 (Eğirdir): B.P.Morettini selfed fruit had very low seed set and
     # was judged parthenocarpic - the study's own conclusion term, same
     # verdict class as Santa Maria.
     # corpus-carried (live 2026-07-19): repeat 4 read 2/4 (sampling noise), but
     # repeat 8 read 7/8, ablated 0/8 - a robust guard, not a boundary case.
     "answer_any": ["partenokarp"]},
    # DROPPED 2026-07-19: local_akca_pear, "Akça armudu kendine verimli mi,
    # bahçeye tozlayıcı çeşit dikmek gerekir mi?" asserting dp_19393's Akça
    # parthenocarpic verdict (same conclusion class as Santa Maria). Note
    # B.P.Morettini above ships on the same verdict: the difference is retrieval -
    # its query surfaces the direct "...partenokarpik meyve oluşumunun" sentence.
    # retrieval-broken (normal 0/4, ablated 0/4): context retrieves the
    # abstract/conclusion sentence naming Akça, but the answer never states
    # "partenokarp" for this cultivar - unlike Santa Maria, where it does.
    # Not retuned.
    # DROPPED 2026-07-18: local_sebin_walnut, "Şebin ceviz çeşidinde erkek mi
    # dişi mi çiçekler önce açar?" asserting dp_1089365's protandry verdict.
    # retrieval-broken (normal 0/4, ablated 0/4): a natural pollination-order
    # query retrieves şebin chunks but not the dichogamy chunk - the "protandr"
    # term only enters context when the query itself names it (a leading query),
    # so the assertion is not answer-natural. Not retuned.
    # DROPPED 2026-07-18: local_hacihaliloglu_apricot, "Hacıhaliloğlu sofralık
    # mı kurutmalık mı?" asserting dp_1217921's kurutmalık classification.
    # corpus-harmful (normal 2/4, ablated 4/4): the model already knows this
    # (kurutmalık 4/4 with an empty corpus) and retrieval only injected noise
    # that broke it half the time - the corpus carries nothing here. Not retuned.
    # DROPPED 2026-07-17: local_0900ziraat_cherry, "0900 Ziraat kirazında
    # kalsiyumu yapraktan mı topraktan mı uygulamalı?" asserting dp_1154776's
    # 8.91 g foliar fruit weight. Retrieval found the paper (context_any
    # "0900 ziraat" green) but the answer never carries the number: grounding
    # 0/5 in normal runs. Failed the GREEN-normal bar, so it does not ship and
    # was not retuned - a case tuned until green asserts nothing.
    {"id": "local_scarletspur_apple", "category": "local", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Scarlet Spur elma çeşidinde kabuk yanıklığını önlemek için hasat ne zaman yapılmalıdır?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["scarlet spur"],
     # dp_1292456 (Onursal ve Koyuncu; Isparta-Eğirdir): the study's own
     # conclusion states fruit harvested "tam çiçeklenmeden 150 gün sonra"
     # avoided superficial scald and kept sensory quality best - a harvest
     # window a natural answer states, not a results-table cell.
     # corpus-carried (live 2026-07-19): normal 3/4, ablated 0/4. Source tests
     # "139 ve 150 gün"; the conclusion picks 150, which the corpus carries.
     "answer_any": ["150 gün"]},
    # DROPPED 2026-07-19: local_avocado_antalya, "Antalya koşullarında hangi
    # avokado çeşitleri düşük sıcaklığa dayanıklıdır?" asserting dp_19510's
    # 'Bacon'/'Ettinger'/'Fuerte' regional recommendation. model-carried (normal
    # 4/4, ablated 4/4): gemma already names these internationally-common
    # cold-tolerant avocado cultivars with an EMPTY corpus, so the corpus adds
    # nothing decisive. A valid map finding, not shipped as a corpus-carried guard
    # (rhizoctonia already covers the model-carried exemplar). Not retuned.
    {"id": "local_hachiya_persimmon", "category": "local", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Hachiya Trabzon hurması kurutulduktan sonra raf ömrünü uzatmak için hangi ön işlem uygulanmalı?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["hachiya"],
     # dp_1797532 (Akev, Kuzucu, Şen; Denizli): the study's own conclusion
     # recommends SMB (sodyum metabisülfit) pretreatment for drying 'Hachiya'
     # persimmon - a practical recommendation a natural answer states.
     # corpus-carried (live 2026-07-19): normal 4/4, ablated 0/4 - decisive.
     "answer_any": ["smb", "sodyum metabisülfit"]},
    {"id": "local_canernar_pomegranate", "category": "local", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Canernar-1 nar tipi soğukta kaç ay süreyle depolanabilir?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["canernar"],
     # dp_19373 (Selçuk ve Erkan; Antalya): the study's own SONUÇ states
     # "'Canernar-1' narları 7 ay süreyle muhafaza edilebilmiştir" - a storage
     # duration a natural answer states, not a results-table cell.
     # corpus-carried (live 2026-07-19): normal 4/4, ablated 0/4 - decisive. The
     # context also cites a generic "6 ay" (Bayram 2009), so the ablated model
     # says "6 ay"; the corpus carries the study's own "7 ay".
     "answer_any": ["7 ay"]},
    # DROPPED 2026-07-20: local_ege_durum_wheat, "Ege Bölgesi koşullarında
    # makarnalık buğday ekeceğim, verimi istikrarlı hangi çeşitler önerilir?"
    # asserting dp_21741's (Ünsal, Geren ve Sevim, ANADOLU 2009) own conclusion
    # "bölgede tavsiye edilebilecek stabil çeşitler; Sarıçanak 98, Ege 88 ve
    # Salihli 92 çeşitleridir." The faithfulness read looked decisive (normal
    # 4/4, ablated 0/4, labelled corpus-carried) but it is an ARTIFACT, caught
    # by the normal run going ctx=False: retrieval never surfaces the
    # conclusion chunk at all. The only dp_21741 chunk it lands on is the
    # materials/methods list of all TWELVE trial cultivars ("Amanos 97, Aydın
    # 93, Ceylan 95, Diyarbakır 81, Ege 88, ... Salihli 92, Sarıçanak 98 ve
    # Sham I"), and the answer recites that roster verbatim as "çalışmalar
    # kapsamında değerlendirilen örnekler" - it never states a recommendation.
    # answer_any's tokens are members of that list, so grounding fires on the
    # roster, not on the paper's verdict: the case measures list-echo, not
    # corpus dependence. Not retuned - repointing context_any at the methods
    # chunk would green it while asserting a DIFFERENT, weaker claim (that the
    # trial exists) than the answer_any claim (which cultivars are recommended).
    # Wheat's rule-2 crop slot is therefore NOT consumed by this round.
    {"id": "local_diyarbakir_safflower", "category": "local", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Diyarbakır koşullarında hangi aspir çeşidi önerilir?",
     "retrieval": "nonempty", "products": "none",
     # the slate's first anchor was "bitkide tabla sayısı", which appears
     # NOWHERE in dp_1514564 (the paper writes "bitki başına tabla sayısı");
     # corrected to the source's own wording. This is a transcription fix to a
     # context anchor, not a loosened assertion.
     # ANCHOR TIGHTENED 2026-07-20 (final-review Minor): the second anchor was
     # "ham yağ oranı", which occurs in FOUR sources (dp_1071763 x6, dp_1514564
     # x2, dp_19433 x2, dp_21746 x1 - the last a canola cultivar-yield trial,
     # semantically adjacent to this query). Since context_any is ANY-semantics,
     # that anchor could carry a green ctx without dp_1514564 being retrieved at
     # all. Replaced with "çalışmanın sonuçlarına dayanarak", from the paper's own
     # conclusion sentence: verified UNIQUE to dp_1514564 corpus-wide and verified
     # PRESENT in the live retrieved context for this query. It echoes neither the
     # query wording nor the asserted value. Both anchors are now source-unique.
     "context_any": ["bitki başına tabla sayısı", "çalışmanın sonuçlarına dayanarak"],
     # dp_1514564 (2025; Diyarbakır, üç yıllık aspir çeşit denemesi): the
     # study's own conclusion states "Sonuç olarak, üç yıllık bu çalışmanın
     # sonuçlarına dayanarak, Remzibey-05 çeşidi Diyarbakır ekolojik koşulları
     # için önerilebilir." - a single-cultivar verdict, stated twice (TR abstract
     # + English conclusion), which is what a recommendation answer says out
     # loud, not a results-table cell. The three answer_any forms are notations
     # of the SAME cultivar name, not a broadening.
     # corpus-carried (live 2026-07-20): normal 4/4, ablated 0/4 - decisive. The
     # normal run also reads ret=True ctx=True, so the grounding is not a
     # list-echo artifact off a methods chunk (the local_ege_durum_wheat trap).
     "answer_any": ["remzibey-05", "remzibey 05", "remzibey"]},
    {"id": "local_oltu_raspberry", "category": "local", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Erzurum Oltu yöresinde hangi ahududu çeşitleri iyi adapte olur?",
     "retrieval": "nonempty", "products": "none",
     # both anchors are unique to dp_30474 corpus-wide (one is from the abstract's
     # RESULTS sentence, the other recurs in materials + conclusion), so ctx=True
     # still proves the source paper - not some other raspberry doc - is what
     # retrieval lands on. That is exactly the check local_ege_durum_wheat failed
     # above.
     "context_any": ["g meyve/sürgün", "yılda iki ürün veren"],
     # dp_30474 (Pehluvan ve Güleryüz, 2010; Erzurum-Oltu, 9 ahududu çeşidi,
     # 1999-2000): the study's own
     # conclusion states "Sonuç olarak yılda iki ürün veren Heritage, Hollanda
     # Boduru ve Summit çeşitleri ile yılda tek ürün veren Newburg çeşidinin
     # diğer çeşitlere göre yörede daha iyi adapte oldukları belirlenmiştir." -
     # an adaptation verdict a natural answer states by cultivar NAME.
     # "Heritage" and "Summit" are deliberately EXCLUDED from answer_any even
     # though the paper names them: both are internationally famous raspberry
     # cultivars a model can emit with an empty corpus. Applying the
     # local_avocado_antalya lesson at authoring time TIGHTENS the assertion to
     # the corpus-specific names; it does not loosen it.
     # corpus-carried (live 2026-07-20): normal 4/4, ablated 0/4 - decisive. The
     # normal run also reads ret=True ctx=True, so the grounding is not a
     # list-echo artifact off a methods chunk (the local_ege_durum_wheat trap).
     "answer_any": ["hollanda boduru", "newburg"]},
    {"id": "local_chickpea_blight_cultivars", "category": "local", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Nohutta yanıklık hastalığına dayanıklılık bakımından hangi çeşitler öne çıkıyor?",
     "retrieval": "nonempty", "products": "none",
     # the slate froze ["ilk bakla yüksekliği", "yüz tane ağırlığı"], but those
     # are YIELD-trait phrases from the results tables (14 occurrences each) and
     # retrieval never lands on those chunks - ctx read False while the verdict
     # chunks WERE retrieved. Repointed at the paper's own disease-scale finding,
     # which is what this case actually asserts; answer_any is untouched. Both
     # anchors are source text absent from the query wording (no query echo -
     # the quant_mera_nitrogen_dose precedent).
     "context_any": ["en düşük hastalık skala değeri",
                     "en duyarlı çeşitler olarak belirlenmiştir"],
     # dp_1559843 (Kavlak ve ark., ANADOLU 2024; Ankara-Gölbaşı, 8 yazlık nohut
     # çeşidi, 2 yıl): the study's own SONUÇ VE ÖNERİLER states "Araştırma
     # sonucunda, Göktürk, Azkan ve Arda çeşitlerinin yanıklık hastalığına karşı
     # daha dayanıklı oldukları ve bu nedenle bölge için daha uygun genotipler
     # olduğu belirlenmiştir." - a resistant-cultivar verdict a natural answer
     # states by NAME. Yield itself did NOT differ significantly between
     # cultivars, so disease resistance is the paper's whole finding. "Arda" is
     # excluded from answer_any: too short and common a token to anchor on.
     # corpus-carried (live 2026-07-20): normal 4/4, ablated 0/4 - decisive. The
     # normal run also reads ret=True ctx=True (after the context-anchor
     # realignment above), so the grounding is not a list-echo artifact off a
     # methods chunk (the local_ege_durum_wheat trap).
     "answer_any": ["göktürk", "azkan"]},
    {"id": "local_antalya_grapefruit_rootstock", "category": "local",
     "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Antalya koşullarında Marsh Seedless altıntop için hangi anaç önerilir?",
     "retrieval": "nonempty", "products": "none",
     # anchor honesty (the local_oltu_raspberry model): both anchors were
     # re-verified against the STORE 2026-07-21 as contiguous runs, matched
     # case-insensitively, and both are unique to dp_19511 corpus-wide (1 and 2
     # chunks). Both are drawn from the page-10 VERDICT chunk, which is the
     # property that matters here: dp_19511's literature review cites Carrizo
     # repeatedly, and page 9 carries a near-identical same-direction claim in
     # ANOTHER author's voice (Ecomides ve Gregoriou, 1993). Anchors confined to
     # the verdict chunk cannot be satisfied by that page-9 citation. The second
     # anchor's 2 chunks are page 0 (abstract) and page 10 (conclusion), both
     # dp_19511's own voice.
     "context_any": ["Sonuç olarak incelenen tüm faktörler",
                     "açısından en iyi sonuçlar Carrizo sitranjı"],
     # dp_19511 (2008; Antalya, Marsh Seedless altıntop x anaç denemesi): the
     # study's own conclusion states "Sonuç olarak incelenen tüm faktörler göz
     # önüne alındığında bölgemiz koşullarında yetiştirilen Marsh Seedless
     # altıntopu için Carrizo sitranjı anacı, en iyi sonucu vermiştir." - a
     # rootstock recommendation is stated by NAME in any natural answer, not
     # read off a results table. The three answer_any forms are notations of the
     # SAME rootstock name, not a broadening.
     # corpus-carried (live 2026-07-21): normal 4/4, ablated 0/4 - decisive. The
     # normal run also reads ret=True ctx=True, so the grounding is not a
     # list-echo artifact off a methods chunk (the local_ege_durum_wheat trap).
     # REDUNDANCY, recorded not changed (final review 2026-07-21): under
     # ANY-semantics "carrizo sitranj" and "carrizo citrange" are DEAD entries -
     # both contain "carrizo", so anything they could match the bare form
     # already matched (verified). Harmless, but they overstate the assertion's
     # breadth to a reader: the case really asserts one token, "carrizo".
     # answer_any is frozen post-validation, so this is documented, not edited.
     # The slate's recorded risk - that Carrizo citrange is an internationally
     # famous citrus rootstock the model might name unaided, the
     # local_avocado_antalya failure mode - did NOT materialise: 0/4 ablated.
     # What the model loses without the corpus is the Antalya-specific verdict,
     # not the name's existence.
     "answer_any": ["carrizo", "carrizo sitranj", "carrizo citrange"]},

    # --- horticulture technique corpus_fact cases (Zone-3 dependence map) ---
    {"id": "technique_carob_graft_diameter", "category": "horticulture", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Keçiboynuzu (harnup) aşılamasında anaç çöğür çapı en az ne kadar olmalıdır?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["çöğür çapı"],
     # dp_19394 (keçiboynuzu aşılama): the study states in prose that grafting
     # success drops when seedling diameter is below 10 mm ("çapın 10 mm'nin
     # altında olduğu durumlarda... aşı tutma oranının olumsuz yönde
     # etkilendiği") - a threshold a practical grafting answer states, not a
     # results-table cell.
     "answer_any": ["10 mm", "10mm"]},
    {"id": "technique_grape_bud_load", "category": "horticulture", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Trakya İlkeren üzüm çeşidinde en yüksek verim için asma başına kaç göz bırakılmalıdır?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["göz bırakılan asmalarda"],
     # dp_19531 (plastik serada Trakya İlkeren, terbiye/asma şarjı): "15 göz"
     # is the yield-only figure tied to one training system and conditioned on
     # the results table ("Çizelge 3"), not an unconditioned recommendation.
     # The paper's actual final conclusion (4. Sonuç) is unconditioned: 18 göz
     # bırakılan asmalarda en yüksek verim sağlanmıştır - the bud-load a
     # natural pruning answer would state, not a table cell.
     "answer_any": ["18 göz"]},
    {"id": "technique_maize_sowing_date", "category": "horticulture", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Alaşehir koşullarında ana ürün mısırda en uygun ekim zamanı nedir?",
     "retrieval": "nonempty", "products": "none",
     # the slate froze ["maverick", "c-955"], but neither is unique corpus-wide:
     # a case-insensitive pass over the store finds "maverick" in fao_bt155e too
     # and "c-955" in dp_21696, so a green ctx on those would not prove dp_21713
     # was retrieved - the local_ege_durum_wheat lesson. Replaced BEFORE the
     # first run with three phrases each unique to dp_21713 (2, 1 and 2 chunk
     # hits respectively, one source each), drawn from the abstract's result
     # sentence and the discussion/SONUÇ chunks. None echoes the query wording.
     "context_any": ["20 mayıs ekimi",
                     "mayıs ortası ile sonu arasındaki",
                     "en yüksek tane verimi 20 mayıs ekim tarihinde"],
     # dp_21713 (Kaya ve Kuşaksız, ANADOLU 2012; Alaşehir/Manisa, 4 melez mısır
     # çeşidi x 4 ekim zamanı, 2003-2004): the study's own discussion states
     # "20 Mayıs ekimi, en uygun ekim zamanı olarak tespit edilmiştir" and its
     # SONUÇ VE ÖNERİLER corroborates without contradicting it - "20 Mayıs'tan
     # sonra yapılan ekimlerde tane veriminin nispeten düşmeye başladığı...
     # Alaşehir bölgesi için en uygun ekim zamanı Mayıs ortası ile sonu
     # arasındaki dönemdir." A calendar date is exactly what a sowing-time
     # answer states, not a results-table cell.
     # NOTE, corrected 2026-07-20 after review: an earlier version of this
     # comment claimed dp_21713 carries NO competing date and cites only
     # Sağlamtimur (1994) on sowing time. Both claims are FALSE, verified
     # against the store. Chunk 0 (page 1) carries a competing in-document date
     # WINDOW from the literature review - Konak ve Demir (1987), "15 Nisan ile
     # 1 Haziran tarihleri arasında yapılan ekimlerden elde edilen tane
     # verimlerine, ekim tarihinin etkisinin olmadığını" - and Lauer et al.
     # (1999) is a third cited sowing-date work. The case measured green
     # ANYWAY. That is the sharper finding: a competing in-document date is NOT
     # by itself disqualifying. What killed dp_21712 was narrower - there the
     # rival figure was a single SPECIFIC date (25 Ekim) directly substitutable
     # for the paper's own verdict, and the model stated it instead. Here the
     # rival is a no-difference WINDOW, not a competing point value, and the
     # paper's own "20 Mayıs" survives. Treat "carries a competing date" as a
     # risk flag to screen, not as a rejection rule.
     # corpus-carried (live 2026-07-20): normal 4/4, ablated 0/4 - decisive. The
     # normal run also reads ret=True ctx=True, so the grounding is not a
     # list-echo artifact off a methods chunk (the local_ege_durum_wheat trap).
     "answer_any": ["20 mayıs"]},
    {"id": "technique_tomato_training_system", "category": "horticulture",
     "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Serada salkım domateste hangi terbiye sistemi önerilir?",
     "retrieval": "nonempty", "products": "none",
     # anchor honesty (the local_oltu_raspberry model): both anchors were
     # re-verified against the STORE 2026-07-21 as contiguous runs, matched
     # case-insensitively, 1 chunk each and unique to dp_19468 corpus-wide. They
     # prove DIFFERENT things and are held together on purpose: "karşı telin
     # üzerinden atlatarak" is the page-2 METHODS chunk (Çizelge 1), so it
     # proves the source but NOT the verdict; "uygulamasının üreticiye tavsiye
     # edilebilecek" IS the page-4 verdict chunk. context_any is ANY-semantics,
     # so ctx=True on its own guarantees only the source, not the conclusion.
     "context_any": ["karşı telin üzerinden atlatarak",
                     "uygulamasının üreticiye tavsiye edilebilecek"],
     # dp_19468 (2009; Antalya serası, M19 salkım domates, terbiye sistemi x
     # dikim sıklığı): the study's own 4. Sonuç states "Sonuç olarak salkım
     # domates yetiştiriciliğinde atlatma sık dikim uygulamasının üreticiye
     # tavsiye edilebilecek bir terbiye sistemi olduğu tespit edilmiştir." -
     # "atlatma" is a Turkish-specific greenhouse training term a model has
     # little reason to emit unaided, and naming the system is exactly what a
     # "hangi terbiye sistemi" answer does. The query was NARROWED at slate time
     # to the training system alone (it previously also asked dikim sıklığı):
     # answer_any covered only the training half, so a correct answer leading
     # with density would have scored red. That removes a false-negative path;
     # answer_any was NOT widened.
     # Recorded risk, checked not assumed: the results section names "kontrol
     # sık dikim" as the highest-YIELD treatment while the conclusion recommends
     # "atlatma sık". That is the technique_grape_bud_load structure (a
     # table-conditioned figure vs an unconditioned conclusion), which SHIPPED -
     # not the guarbean either/or. The paper explicitly REJECTS seyrek dikim
     # ("seyrek dikim uygulaması kesinlikle önerilmezken").
     # REDUNDANCY, recorded not changed (final review 2026-07-21): "atlatma sık"
     # is a DEAD entry under ANY-semantics - it contains "atlatma", so the bare
     # form already matched everything it could (verified). The case really
     # asserts one token, "atlatma". answer_any is frozen post-validation, so
     # this is documented, not edited.
     # corpus-carried (live 2026-07-21): normal 4/4, ablated 0/4 - decisive. The
     # normal run also reads ret=True ctx=True, so the grounding is not a
     # list-echo artifact off a methods chunk (the local_ege_durum_wheat trap).
     "answer_any": ["atlatma", "atlatma sık"]},
    {"id": "technique_maize_sowing_opener", "category": "horticulture",
     "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "İkinci ürün mısırın doğrudan ekiminde hangi gömücü ayak tipi daha iyi çıkış sağlar?",
     "retrieval": "nonempty", "products": "none",
     # anchor honesty (the local_oltu_raspberry model): both anchors were
     # re-verified against the STORE 2026-07-21 as contiguous runs, matched
     # case-insensitively, and are unique to dp_19517 corpus-wide. They are NOT
     # equally strong. "yürütüldüğü iklim ve toprak koşulları için" is 1 chunk
     # and IS the page-8 verdict chunk; "yan tekerlek" is 10 chunks over pages
     # 0, 2, 3, 4, 6, 7, 8 - source-unique but NOT verdict-confined, so on its
     # own it proves only that dp_19517 was retrieved. context_any is
     # ANY-semantics, so the honest claim is: ctx=True proves the source, and
     # only the first anchor pins the conclusion.
     "context_any": ["yan tekerlek",
                     "yürütüldüğü iklim ve toprak koşulları için"],
     # dp_19517 (2007; ikinci ürün mısır, doğrudan ekim, gömücü ayak x derinlik
     # kontrol sistemi): the study's own conclusion states "Sonuç olarak, bu
     # araştırmanın yürütüldüğü iklim ve toprak koşulları için, ikinci ürün
     # mısırın doğrudan ekiminde, daha yüksek tarla filiz çıkış oranı ve çıkış
     # oranı indeksi ve daha düşük ortalama çıkış süresi için çift diskli gömücü
     # ayak ve yan tekerlek ... kullanılması önerilmektedir." (confirmed verbatim
     # in docs/books/dp_19517.pdf, page 8) - naming the opener is exactly what a
     # "hangi gömücü ayak tipi" answer states, not a results-table cell.
     # Recorded risk, checked not assumed: double-disc openers are standard
     # no-till practice, so a model-carried read was plausible. It did NOT
     # materialise (ablated 0/4).
     # RETRIEVAL COLLISION, checked not assumed: dp_19566 (Karayel & Özmerzi -
     # the same authors, journal and research programme) also compares furrow
     # openers including "çift diskli" and recommends a DIFFERENT one (balta),
     # judging openers on furrow cross-section rather than emergence rate. Both
     # answer_any terms hit it on 7 pages, so a green grounding off a dp_19566
     # chunk would be right by accident. The retrieved context was therefore
     # inspected directly: all FOUR chunks are dp_19517 (pages 0, 0, 8, 1),
     # including the page-8 verdict chunk. dp_19566 does not enter context.
     # REDUNDANCY, recorded not changed (final review 2026-07-21): "çift diskli"
     # is a DEAD entry under ANY-semantics - _matches' right guard is (?!\d)
     # only, so the bare "çift disk" already matches "çift diskli" (verified).
     # The case really asserts one token, "çift disk". answer_any is frozen
     # post-validation, so this is documented, not edited.
     # corpus-carried (live 2026-07-21): normal 4/4, ablated 0/4 - decisive, so
     # no repeat-8 escalation (that is only for an exact 2/4 read). The normal
     # run also reads ret=True ctx=True, so the grounding is not a list-echo
     # artifact off a methods chunk (the local_ege_durum_wheat trap).
     "answer_any": ["çift disk", "çift diskli"]},
    # --- Round 5 candidates UNDER MEASUREMENT (added 2026-07-22): slate rows 9 & 10,
    # frozen values COPIED VERBATIM from the round-4 slate. See the provenance +
    # U+2019 warning block just below (retained). NO corpus_class is set until both
    # directions are measured; a red read is DROPPED, never tuned to green.
    {"id": "quant_forage_irrigation_level", "category": "horticulture", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Macar fiği ve yem bezelyesinde kurak dönemde hangi toprak nem seviyesinde sulama yapmalıyım?",
     "retrieval": "nonempty", "products": "none",
     # dp_257759 (Macar fiği + yem bezelyesi, forage legumes; slate row 9): the
     # study's own conclusion states "...en yüksek ot verimleri için %75 tarla
     # kapasitesi seviyesinde sulama yapıldığında elde edildiği". The first
     # context anchor uses U+2019 (’), NOT an ASCII apostrophe (ASCII form = ZERO
     # chunks). Copied verbatim from the slate; do not retype it.
     "context_any": ["kapasitesinin %25’ine düşmesine sebep olan kuraklıklar",
                     "her iki yem bitkisine ne ciddi zarar vererek"],
     # RISK checked, not assumed: "75% of field capacity" is a fairly generic
     # irrigation figure, so a model-carried read was plausible. It did NOT
     # materialise.
     # corpus-carried (live 2026-07-22, round 5): repeat 4 read normal 4/4,
     # ablated 0/4 - decisive, no repeat-8 escalation. The normal run also reads
     # ret=True ctx=True, so the grounding is not a list-echo off a methods chunk
     # (the local_ege_durum_wheat trap): the U+2019 verdict-chunk anchor is in the
     # retrieved context.
     "answer_any": ["%75 tarla kapasitesi", "% 75 tarla kapasitesi",
                    "tarla kapasitesinin %75"]},
    # DROPPED 2026-07-22 (round 5): technique_grape_graft_material, "Asma aşısında
    # anaç çeliği ve kalem hangi sürme durumunda olmalı?" asserting dp_19426's own
    # conclusion "sürmüş çelik X sürmemiş kalem durumunun aşıda kullanılması
    # önerilebilir" (slate row 10). retrieval-broken (normal ret=True ctx=False
    # ground=False). NOT dead anchors: both context_any anchors were re-verified in
    # the store (1 chunk each, dp_19426 page 7, source-unique). The RECORDED
    # sibling collision materialised - retrieve_context landed on dp_19448 (the
    # same Tekirdağ group, same graft combination with UV-C) as the #1 source; the
    # only dp_19426 chunk that surfaced was NOT the page-7 verdict chunk, so
    # neither anchor entered context and the model never stated the pairing. Same
    # class as the dropped quant_sunflower_humic_acid_dose (killed by dp_19431).
    # Retrieval is deterministic, so ctx=False is stable, not a flake - no repeat
    # escalation. The only way to green this is to change the query or the claim,
    # which is tuning-to-green; not done. Do NOT re-mine dp_19426 / dp_19448 /
    # dp_19471 against each other in a future round: they collide by construction.
    # HISTORICAL provenance block (row 9 is now a case ABOVE; row 10 dropped).
    # UNMEASURED 2026-07-21 (round-4 stopping rule, not a finding): slate rows 9
    # (dp_257759, Macar fiği/yem bezelyesi "%75 tarla kapasitesi" irrigation
    # level) and 10 (dp_19426, asma aşısı "sürmüş çelik X sürmemiş kalem"
    # graft-material state) were never run. Round 4's stopping rule fires at 4
    # corpus-carried ships, and this case was the fourth. Both rows' context_any
    # anchors WERE re-verified against the store first and all four are present,
    # contiguous and source-unique (r9: 2 chunks + 1 chunk, both page 4,
    # dp_257759-only; r10: 1 chunk each, both page 7, dp_19426-only), so round 5
    # can pick them up as-is. Neither is dropped and neither is a map finding -
    # they are simply unreached. Row 9 carries a recorded model-carried risk
    # ("75 % of field capacity" is a generic irrigation figure) and row 10 a
    # recorded sibling-collision risk (dp_19448/dp_19471, same group, same graft
    # combination), so both still need the ablated direction run first.
    #
    # WHERE THE ROWS ACTUALLY ARE (added 2026-07-21 by the final review - the
    # block above says "pick them up as-is" but recorded no path, no query and no
    # anchor text, so a cold session could not act on it):
    #   docs/superpowers/2026-07-21-round4-candidate-slate.md, section 1,
    #   rows 9 and 10. Query, answer_any, answer_none, context_any and the full
    #   anchor locators are frozen there. COPY them; do not re-derive them.
    #
    # WARNING - ROW 9's ANCHOR CONTAINS U+2019, NOT AN ASCII APOSTROPHE.
    # The anchor is "kapasitesinin %25’ine düşmesine sebep olan kuraklıklar".
    # COPY IT FROM THE SLATE; DO NOT RETYPE IT. Re-verified 2026-07-21 against
    # the store with the exact _matches semantics, corpus-wide:
    #   U+2019 form (’)  -> 2 chunks, dp_257759.pdf page 4   (correct)
    #   ASCII form  (')  -> ZERO chunks                      (dead)
    # This is the same defect class that killed 10 of 20 anchors earlier this
    # round (spec section 3, "verify every anchor against the STORED CHUNK
    # TEXT"), and it is the dangerous kind: a retyped anchor does not fail
    # loudly, it produces ctx=False, which reads as a retrieval-broken FINDING
    # about the corpus rather than as a typo. Row 9's own slate entry records
    # that its previous ASCII-apostrophe anchor was dead for exactly this reason.
    # Row 10's two anchors are plain ASCII and were also re-verified the same
    # day: 1 chunk each, dp_19426.pdf page 7.
    # DROPPED 2026-07-20: technique_pea_sowing_date, "Ot amaçlı bezelyede en
    # yüksek hasıl verimi için ekim ne zaman yapılmalı?" asserting dp_21712's
    # own conclusion "en yüksek hasıl ve kuru madde veriminin 22 Kasım'da
    # yapılan ekimlerden sağlandığı". retrieval-broken (normal 0/4, ablated
    # 0/4) - decisive at repeat 4, so no repeat-8 escalation (that is only for
    # an exact 2/4 read). NOT a retrieval-plumbing failure: all four retrieved
    # chunks are dp_21712 and "22 Kasım" IS in the context. The assertion is
    # simply not answer-natural, because the SAME document carries a COMPETING
    # date - its literature review cites Soya ve ark. (1989), Bornova, whose
    # best sowing date was 25 Ekim. The model reads both and states the cited
    # "25 Ekim" (and generic "erken dönem ekimi") rather than the paper's own
    # 22 Kasım verdict. The only way to green this is to accept a different
    # claim, which is the guarbean rule. Not retuned. A sowing-date candidate
    # whose OWN verdict is not displaced by a substitutable competing POINT date
    # can still work: slate rank 6 (dp_21713 maize, "20 Mayıs") was subsequently
    # validated and SHIPPED above as technique_maize_sowing_date (corpus-carried,
    # normal 4/4 ablated 0/4). Note dp_21713 is NOT free of a competing date - it
    # carries one - but that rival is a no-difference WINDOW (Konak ve Demir's
    # 15 Nisan-1 Haziran), not a single point value directly substitutable for the
    # verdict the way this case's cited 25 Ekim is. See that case's NOTE for why
    # "carries a competing date" is a risk flag to screen, not a rejection rule.
    # DROPPED 2026-07-19: technique_guarbean_row_spacing, "Sakız fasulyesi ot
    # üretimi için en uygun sıra arası mesafe kaç cm olmalıdır?" asserting
    # dp_257760's "4. SONUÇ VE ÖNERİLER" disjunction ("bitkilerin 20 veya 40 cm
    # aralıkla ekilmesi gerektiği"). Originally shipped with a broadened
    # answer_any ("20-40 cm"/"20 ila 40 cm"/"20-40cm") that converts the source's
    # either/or claim into a continuous-range claim - a looser, different
    # assertion, not an alternate notation of the same value. Code review
    # flagged this; tightened to disjunction-only forms ("20 veya 40 cm", "20
    # veya 40cm", "20 ya da 40 cm") and re-validated: repeat 4 read normal 2/4
    # ablated 0/4 (borderline), but repeat 8 read normal 0/8 ablated 0/8 -
    # retrieval-broken. The clean disjunction assertion is not answer-natural
    # (the model doesn't reliably state "20 veya 40 cm" even with the corpus
    # chunk in context) - the prior green was an artifact of the broadened
    # range matching the model's own smoothing of the odd disjunction into
    # "20-40 cm". Not retuned back to green (cherry rule).

    # --- Zone-4 corpus_fact cases (gap-crop / quantitative findings) ---
    {"id": "quant_wheat_nitrogen_dose", "category": "nutrition", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Ekmeklik buğdayda yüksek ve ekonomik tane verimi için dekara kaç kilogram saf azot uygulanmalıdır?",
     "retrieval": "nonempty", "products": "some",
     "context_any": ["azot dozu daha ekonomik", "16 kg/da azot dozu"],
     # dp_21735 (Öncan-Sümer ve ark., ANADOLU 2010; ekmeklik buğday N x sıklık):
     # the study's own SONUÇ states "yüksek verim için her iki yılda da 16 kg/da
     # azot dozu daha ekonomik" and again "16 kg/da azot dozunun ... bölge buğday
     # yetiştiriciligi için yeterli" - an unconditioned recommendation a natural
     # fertilization answer states, not a single results-table cell.
     "answer_any": ["16 kg/da", "16 kg saf azot", "16 kg n"]},
    # DROPPED 2026-07-18: quant_vetch_phosphorus, "Fiğ (yem bitkisi)
    # yetiştiriciliğinde dekara ne kadar fosforlu gübre (P2O5) önerilir?"
    # asserting dp_30458's "6 kg/da P2O5" figure. Code review found two defects
    # in the original assertion: (1) context_any's "6 kg/da P2O5" phrase is not
    # discriminating - it appears verbatim in 5 corpus sources, including an
    # unrelated soybean trial (dp_21743) and soil-test data (dp_1419647/57);
    # (2) answer_any included "6 kg/da fosfor"/"6 kg fosfor", which substitute
    # the specific compound P2O5 with the generic element word "fosfor" -
    # forbidden broadening, not a same-value notation. After narrowing
    # context_any to the source-unique "fosfor gübrelemesinin" and answer_any
    # to the four true P2O5-notation variants only, live re-validation showed
    # retrieval-broken (normal 1/4, ablated 0/4) - the model does not reliably
    # carry the number even with the corpus present, so the case does not
    # clear the GREEN-normal bar. Not retuned by re-adding the "fosfor"
    # variants or any looser value - that would be re-broadening to green.
    {"id": "quant_mera_nitrogen_dose", "category": "nutrition", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Meranın otlatma kapasitesini artırmak için dekara kaç kilogram azotlu gübre uygulanmalıdır?",
     "retrieval": "nonempty", "products": "some",
     # context_any drawn from the paper's aspect finding + comparative result,
     # NOT the query-echoing "otlatma kapasitesini artırmak" (a query substring,
     # a tautological anchor - code review 2026-07-19); both fragments are in the
     # retrieved dp_30475 context and absent from the query wording.
     "context_any": ["farklı yöneylerde meranın otlatma kapasitesi",
                     "gübrelenen parsellerde otlatma kapasitesi"],
     # dp_30475 (Daşcı ve ark.; yöney ve gübrelemenin meranın otlatma kapasitesi
     # üzerine etkileri): the study's own "4. SONUÇ ve ÖNERİLER" states "mera
     # alanlarına 10kg/da azot uygulaması meranın otlatma kapasitesini artırmak
     # amacıyla önerilebilir" - an unconditioned recommendation a natural
     # pasture-fertilization answer states, not a single results-table cell.
     # corpus-carried (live 2026-07-19): repeat 4 read normal 4/4, ablated 0/4 -
     # decisive, no repeat-8 recheck needed. answer_any includes "10 kg azot"
     # (no "/da") because the model consistently paraphrases as "dekara 10 kg
     # azot" - same value, alternate notation, matching the wheat case's "16 kg
     # saf azot" precedent.
     "answer_any": ["10 kg/da", "10 kg/da azot", "10 kg n", "10 kg azot"]},
    # DROPPED 2026-07-21: quant_sunflower_humic_acid_dose, "Ayçiçeğinde ekim
    # öncesi tohuma humik asit uygulaması hangi dozda yapılmalı?" asserting
    # dp_19600's own conclusion "100 kg tohuma 60 g humik asit dozunun ise
    # ekimden önce ayçiçeği tohumlarına uygulanabileceği". retrieval-broken
    # (normal 0/4, ablated 0/4) - decisive at repeat 4, so no repeat-8
    # escalation (that is only for an exact 2/4 read). The normal run also reads
    # ctx=False, and the reason is a RETRIEVAL COLLISION, not dead anchors: both
    # context_any anchors were re-verified in the store the same day (present as
    # contiguous runs, 1 chunk each, unique to dp_19600 corpus-wide, both in the
    # page-4 verdict chunk). All FOUR retrieved chunks are dp_19431 - a
    # different Ankara ayçiçeği + humik asit paper, which the round-4 slate had
    # already rejected at mining time as multi-valued (18 g/da at sowing, 12 at
    # the 4-5 leaf stage, 6 later). dp_19600 never enters context at all, so the
    # model answers off the collider's doses and never states 60 g/100 kg. The
    # only way to green this is to accept dp_19431's different claim, which is
    # the guarbean rule. Not retuned. Do not re-mine dp_19600 and dp_19431
    # against each other in round 5: they collide by construction (same crop,
    # same input, same question wording).
    {"id": "quant_rose_pot_fertilizer_dose", "category": "nutrition",
     "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Saksıda gül fidanı yetiştirirken hümik asitli kompoze gübreden saksı başına ne kadar vermeliyim?",
     "retrieval": "nonempty", "products": "some",
     # anchor honesty (the local_oltu_raspberry model): both anchors are unique
     # to dp_21749 corpus-wide, re-verified against the STORE 2026-07-21 as
     # contiguous runs, case-insensitively. They are NOT equally strong.
     # "18 kg harç için en olumlu sonucu" is a single chunk and sits in the
     # page-10 VERDICT chunk, next to "6 g/saksı"; "yaprak kuru madde oranı" is
     # 6 chunks spread over pages 0, 4, 7, 8, 10 - source-unique but NOT
     # verdict-confined, so on its own it would only prove dp_21749 was
     # retrieved, not that the conclusion was. context_any is ANY-semantics, so
     # the honest claim is: ctx=True proves dp_21749 and nothing else was the
     # source; only the first anchor pins the verdict chunk.
     "context_any": ["yaprak kuru madde oranı",
                     "18 kg harç için en olumlu sonucu"],
     # dp_21749 (2009; saksıda gül fidanı, hümik asitli kompoze gübre dozları):
     # the study's own conclusion states "6 g/bitki gübre dozunun sağlıklı gül
     # yetiştirmek ve en fazla sayıda çiçek elde etmek açısından en uygun doz
     # olacağı sonucuna varılmıştır" (and "özellikle 6 g/saksı'lık gübre
     # dozunda en olumlu sonuç elde edilmiştir") - a per-pot rate is exactly
     # what a "ne kadar vermeliyim" answer states, not a results-table cell.
     # The paper states the SAME value both as g/saksı and g/bitki, so those
     # answer_any forms are notations of one value, not a broadening; no bare
     # "6 g" form is listed. Recorded risk: the paper also reports that
     # 12 g/saksı DEPRESSED plant height - a supporting finding, not a competing
     # recommendation.
     # RECORDED RISK, SECOND PART (added 2026-07-21 by the final review; the
     # 12 g line above was only half the picture). "6 g/saksı" ALSO MATCHES A
     # RANGE that includes 6, because _matches' left guard is (?<!\w) and that
     # does not break on "-", on a space, or on "ve"/"ile". Verified:
     #   _matches("6 g/saksı", "3-6 g/saksı")     = True
     #   _matches("6 g/saksı", "4-6 g/saksı")     = True
     #   _matches("6 g/saksı", "3 ve 6 g/saksı")  = True
     #   _matches("6 g/saksı", "3 ile 6 g/saksı") = True
     # This is not hypothetical: dp_21749 ITSELF writes the range form for
     # individual traits in the same SONUÇ VE ÖNERİLER block as the verdict -
     # "Yaprak kuru madde oranı açısından en iyi sonuç 3 ile 6 g/saksı
     # dozlarından elde edilmektedir" (page 10, the verdict chunk) and "3 ve
     # 6 g/saksı'lık dozlar ... en başarılı sonucu vermektedir" (pages 6, 7, 8,
     # 10). So a corpus-grounded answer that reports the RANGE rather than the
     # paper's single-dose verdict grounds GREEN on a DIFFERENT claim.
     # Why this is recorded and NOT fixed: it does not make the case a false
     # guard. Corpus dependence is untouched - the range forms are as
     # corpus-dependent as the verdict, and the ablated read is 0/4 either way.
     # answer_any is FROZEN post-validation and was NOT narrowed; narrowing a
     # measured assertion after the fact would invalidate the measurement it was
     # measured under. Recorded so a green read on this case is understood as
     # "the model stated 6 g/saksı, possibly inside a 3-6 range", not as "the
     # model stated the paper's single-dose verdict".
     # (Note the guard is not useless: "6-12 g/saksı" does NOT match, since that
     # string does not contain "6 g/saksı" at all.)
     # corpus-carried (live 2026-07-21): normal 3/4, ablated 0/4 - not an exact
     # 2/4 read, so no repeat-8 escalation. The normal run also reads ret=True
     # ctx=True (and prod=True), so the grounding is not a list-echo artifact
     # off a methods chunk (the local_ege_durum_wheat trap). NOTE the 3/4: this
     # case grounds intermittently, so a single full-eval sample can read
     # ground=False (one was observed). That is the deveci-anchor situation the
     # _classify docstring records - the label is majority-based on purpose -
     # not a reason to widen answer_any.
     # This case took the input-application-rate bucket's last slot only because
     # slate rank 1 (dp_19600 sunflower) dropped retrieval-broken above; rows 1
     # (dp_19434 Ranunculus) and 5 (dp_21704 marul) stay BLOCKED BY SHAPE CAP
     # and are held for round 5.
     "answer_any": ["6 g/saksı", "6 g saksı", "6 g/bitki", "saksı başına 6 g"]},

    # ----------------------------------------------------------------- #
    # fert_plan - the ONE route whose behaviour diverges (2026-08-11)
    # ----------------------------------------------------------------- #
    # Added because the 55-case shield had ZERO coverage of the only route this
    # project has ever made behave differently: the whole set routed to
    # plant_info (40), nutrition (13) and offscope (2). The shield proved the
    # divergence did not LEAK into the other routes, which is what it was for,
    # but it never once exercised the changed route. The only evidence for it
    # was two hand-run answers pasted into a findings document.
    #
    # ANCHORS ARE THE PROVINCE NAME, and deliberately nothing else. The month
    # and season are date-derived (season.describe(date.today())), so an anchor
    # like "Ağustos" would be a time bomb in a frozen set - green in August, red
    # in December, for no product reason. The province is the one part of the
    # context block that does not move with the calendar, and it is also the
    # part that proves the block reached the model at all.
    {"id": "fertplan_province_reaches_the_answer",
     "category": "fert_plan",
     "query": "Manisa'dayım, domatese ne zaman gübre vermeliyim?",
     "retrieval": "nonempty",
     "products": "some",
     # Measured 2026-08-11: "Manisa'daki Ağustos ayı sıcaklıkları (38 °C'ye
     # kadar çıkabilen) ve yağışsız hava koşulları göz önüne alındığında..."
     # - both the province AND its live forecast reached the reply.
     "answer_any": ["Manisa"]},

    {"id": "fertplan_asks_which_province",
     "category": "fert_plan",
     "query": "Domatese ne zaman gübre vermeliyim?",
     "retrieval": "nonempty",
     "products": "some",
     # With no province stated the block says "ili BILINMIYOR - sor". The
     # contract is that the assistant ASKS rather than inventing a location.
     # Measured: "...hangi ilde yetiştirme yaptığınızı ... belirtebilir misiniz?"
     "answer_any": ["hangi il", "ilde", "bölgen"]},

    {"id": "fertplan_user_province_beats_produce_name",
     "category": "fert_plan",
     "query": "Antalya'dayım, Trabzon hurmasına ne zaman gübre vermeliyim?",
     "retrieval": "nonempty",
     "products": "some",
     # THE REGRESSION GUARD for the Critical found in whole-branch review.
     # Turkish produce is named after provinces - Trabzon hurması, Amasya
     # elması, Isparta gülü - and the matcher used to read the FRUIT'S province
     # as the user's address, then fetch that province's real forecast. Here the
     # user is in Antalya and the fruit carries "Trabzon": the answer must be
     # built on Antalya. Unit tests pin _context_block; this pins what the user
     # actually receives, one level up.
     # Measured: "Trabzon hurması için ... Antalya'nın Ağustos ayı sıcaklıkları
     # ... 40 °C'ye ulaşan sıcaklıklarda" - 40 °C is Antalya's forecast, not
     # Trabzon's. Note "Trabzon" is NOT bannable via answer_none: it is the
     # fruit's name and belongs in the reply.
     "answer_any": ["Antalya"]},

    # ----------------------------------------------------------------- #
    # crop_choice - the route this plan makes diverge
    # ----------------------------------------------------------------- #
    # Anchors avoid month and season names: those come from date.today(), so an
    # anchor like "Ağustos" would be green today and red in December with nothing
    # about the product having changed. The province is safe - it comes from the
    # question.
    {"id": "crop_choice_gives_factors_not_a_recommendation",
     "category": "crop_choice",
     "query": "Manisa'dayım, bu yıl tarlama ne eksem iyi olur?",
     "retrieval": "any",
     "products": "any",
     "answer_any": ["toprak", "sulama", "münavebe", "pazar"],
     # The prohibition is a PROMPT constraint, not something code can enforce, so
     # it is measured here. These ban the ACT of recommending, not the crop name:
     # a violation reads "pamuk ekmenizi öneririm", and banning crop names instead
     # would red on a legitimate answer that mentions one while explaining
     # rotation. A red here is a finding to report, not an anchor to soften.
     "answer_none": ["ekmenizi öneririm", "ekmenizi tavsiye ederim",
                     "ekebilirsiniz"]},
]
