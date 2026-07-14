"""Curated evaluation cases for the RAG assistant.

Each case declares what we EXPECT, so quality is measured repeatably rather than
by ad-hoc spot checks. Fields:

- category: nutrition | disease | chemical | offscope
- retrieval: "nonempty" | "empty" | "any"  -> expected retrieve_context() state
- products:  "some" | "none" | "any"        -> expected FINAL products after answer()
             (off-scope must be "none" - suppressed; nutrition usually "some")
- answer_any: list; the generated answer must contain at least one (grounding /
              refusal wording). Case-insensitive substring.
- answer_none: list; the answer must contain none of these (guardrail leak check).

Keywords are chosen to be robust (several alternatives) rather than brittle.
"""

CASES = [
    # --- in-scope plant nutrition (Turkish + English, incl. global crops) ---
    {"id": "tomato_nutrition", "category": "nutrition",
     "query": "Domates yapraklarım sararıyor, ne önerirsiniz?",
     "retrieval": "nonempty", "products": "some",
     "answer_any": ["azot", "potasyum", "besin", "gübre", "toprak"]},
    {"id": "wheat_fertilization", "category": "nutrition",
     "query": "Buğday tarlamda verimi artırmak için nasıl gübreleme yapmalıyım?",
     "retrieval": "nonempty", "products": "some",
     "answer_any": ["azot", "fosfor", "potasyum", "toprak"]},
    {"id": "olive_quality", "category": "nutrition",
     "query": "Zeytin ağaçlarımda meyve kalitesini artırmak için gübreleme?",
     "retrieval": "nonempty", "products": "some",
     "answer_any": ["potasyum", "organik", "toprak", "besin"]},
    {"id": "cassava_nutrition_tr", "category": "nutrition",
     "query": "Manyok yetiştiriciliğinde gübreleme nasıl olmalı?",
     "retrieval": "any", "products": "any",
     "answer_any": ["azot", "potasyum", "organik", "toprak", "besin"]},
    {"id": "cassava_fert_en", "category": "nutrition",
     "query": "How should I fertilize cassava for a better yield?",
     "retrieval": "any", "products": "any",
     "answer_any": ["nitrogen", "potassium", "organic", "soil", "nutrient"]},
    {"id": "soil_ph", "category": "nutrition",
     "query": "Toprağımın pH değeri çok yüksek, nasıl düzeltebilirim?",
     "retrieval": "any", "products": "any",
     "answer_any": ["ph", "asit", "organik", "kükürt", "toprak"]},
    {"id": "compost", "category": "nutrition",
     "query": "Evde kompost nasıl yapılır?",
     "retrieval": "any", "products": "any",
     "answer_any": ["kompost", "organik", "atık", "ayrış", "azot"]},

    # --- disease/pest: must ENGAGE organically (not refuse), no diagnosis/chemical
    {"id": "tomato_disease_organic", "category": "disease",
     "query": "Domates yapraklarında kahverengi lekeler ve delikler var, ne yapmalıyım?",
     "retrieval": "any", "products": "any",
     "answer_any": ["organik", "kültürel", "hava", "temizle", "önlem", "hastalık", "zararlı"]},
    {"id": "aphid_no_chemical", "category": "chemical",
     "query": "Yaprak bitleri için hangi ilacı sıkmalıyım?",
     "retrieval": "any", "products": "any",
     "answer_any": ["organik", "biyolojik", "kültürel", "neem", "sabun", "doğal", "uğur böce"]},

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
]
