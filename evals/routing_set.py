"""Frozen routing expectations. Authored 2026-08-10, BEFORE src/router.py existed.

Pre-registration matters here for the same reason it did for the fragility probe:
a set written after the implementation measures the implementation, not the
requirement. Do not edit a case to make the router pass - fix the router, or
record why the expectation was wrong.
"""

ROUTES = ("plant_info", "nutrition", "fert_plan", "budget", "crop_choice",
          "product_dose", "offscope")

ROUTING_CASES = [
    # --- plant_info: growing practice, plant health, physiology --------------
    {"query": "Asmada budama ne zaman ve nasıl yapılır?", "route": "plant_info"},
    {"query": "Meyve ağaçlarında aşılama nasıl yapılır?", "route": "plant_info"},
    {"query": "Domates yapraklarında kahverengi lekeler var, ne yapmalıyım?", "route": "plant_info"},
    {"query": "Serada domates yetiştirirken havalandırma neden önemlidir?", "route": "plant_info"},
    {"query": "Kabak çiçeklerinde tozlaşma olmuyor, ne yapabilirim?", "route": "plant_info"},
    {"query": "Çilek nasıl çoğaltılır?", "route": "plant_info"},
    {"query": "Hasat sonrası elmaları uzun süre nasıl saklarım?", "route": "plant_info"},
    {"query": "Damla sulama bitkiler için neden faydalıdır?", "route": "plant_info"},

    # --- nutrition: fertilization without a timing request -------------------
    {"query": "Domates yapraklarım sararıyor, ne önerirsiniz?", "route": "nutrition"},
    {"query": "Buğday tarlamda verimi artırmak için nasıl gübreleme yapmalıyım?", "route": "nutrition"},
    {"query": "Toprağımın pH değeri çok yüksek, nasıl düzeltebilirim?", "route": "nutrition"},
    {"query": "Evde kompost nasıl yapılır?", "route": "nutrition"},
    {"query": "Bitkilerde demir eksikliği nasıl giderilir?", "route": "nutrition"},
    {"query": "Zeytin ağaçlarımda meyve kalitesini artırmak için gübreleme?", "route": "nutrition"},
    {"query": "Manyok yetiştiriciliğinde gübreleme nasıl olmalı?", "route": "nutrition"},

    # --- fert_plan: nutrition AND timing ------------------------------------
    {"query": "Domatese ne zaman gübre vermeliyim?", "route": "fert_plan"},
    {"query": "Buğdayda azotu hangi dönemde uygulamalıyım?", "route": "fert_plan"},
    {"query": "Fındık için gübreleme takvimi çıkarır mısın?", "route": "fert_plan"},
    {"query": "Zeytinde gübreleme programı nasıl olmalı?", "route": "fert_plan"},
    {"query": "Asmaya hangi ayda besleme yapılır?", "route": "fert_plan"},
    {"query": "Domates fidesi diktim, ne zaman besleyeyim?", "route": "fert_plan"},
    {"query": "Gübreyi hangi dönemde vermem lazım?", "route": "fert_plan"},
    {"query": "Bu ay azotlu gübre atmalı mıyım?", "route": "fert_plan"},

    # --- budget: money ------------------------------------------------------
    {"query": "5 dönüm domates ektim 1 milyon masraf ettim, ne kadar kâr ederim?", "route": "budget"},
    {"query": "Buğday ekmenin dekara maliyeti nedir?", "route": "budget"},
    {"query": "Zeytinlikten yıllık ne kadar gelir beklerim?", "route": "budget"},
    {"query": "Fındık bahçesi kurmak kaç para tutar?", "route": "budget"},
    {"query": "Serada domates yetiştirmek kârlı mı?", "route": "budget"},
    {"query": "Girdi masraflarım ne kadar olur?", "route": "budget"},
    {"query": "Bu yatırımın geri dönüşü ne kadar sürer?", "route": "budget"},

    # --- product_dose: how much of a fertilizer for this field ---------------
    # Authored 2026-08-25, BEFORE src/router.py knew this route existed.
    {"query": "HİGRO BARF dekara ne kadar kullanmalıyım?", "route": "product_dose"},
    {"query": "5 dönümlük tarlama FLY AZOT'tan ne kadar lazım?", "route": "product_dose"},
    {"query": "HİGRO FUBBY'nin dekara dozu nedir?", "route": "product_dose"},
    {"query": "Gübreyi dekara kaç litre vermeliyim?", "route": "product_dose"},
    {"query": "Domates için gübreden dekara ne kadar atmalıyım?", "route": "product_dose"},
    {"query": "Bir dönüme kaç kilo gübre gider?", "route": "product_dose"},

    # --- product_dose: naming a product is not asking its amount ------------
    # Authored 2026-08-25, in response to the whole-branch review. None of the
    # six cases above names a product in a question that is not about
    # quantity, so none of them could catch the rule hijacking every message
    # that merely names a product.
    {"query": "HİGRO BARF nedir?", "route": "plant_info"},
    {"query": "HİGRO BARF ne zaman uygulanır?", "route": "plant_info"},
    {"query": "Dekara kaç kilo azot gerekir?", "route": "nutrition"},

    # --- product_dose: a nutrient-qualified fertilizer is a CLASS -----------
    # Authored 2026-10-28, after the answer eval caught quant_mera_nitrogen_dose
    # answered by the dose card's fixed intro. No case above carried a
    # nutrient-qualified "gübre" with a rate, so the "zero wrong entries" this
    # set reported for product_dose had zero eligible inputs - the lesson the
    # block above records, met again one rule over. Both halves are here: a
    # BARE qualified "gübre" is a class (nutrition); a possessed or definite one
    # is the user's own (product_dose).
    {"query": "Buğdaya dekara kaç kg azotlu gübre verilir?", "route": "nutrition"},
    {"query": "Dekara kaç kg kükürtlü gübre uygulanır?", "route": "nutrition"},
    {"query": "Azotlu gübremi dekara ne kadar atmalıyım?", "route": "product_dose"},
    {"query": "Elimdeki fosforlu gübreyi dekara ne kadar vereyim?", "route": "product_dose"},

    # --- crop_choice: what to plant -----------------------------------------
    {"query": "Bu yıl tarlama ne eksem iyi olur?", "route": "crop_choice"},
    {"query": "Hangi ürünü yetiştirmeliyim?", "route": "crop_choice"},
    {"query": "Bu sezon ne ekmek mantıklı?", "route": "crop_choice"},
    {"query": "Arazime hangi meyve ağacı uygun?", "route": "crop_choice"},
    {"query": "Bu yıl domates mi biber mi ekmeliyim?", "route": "crop_choice"},
    {"query": "Ne yetiştirsem daha iyi olur?", "route": "crop_choice"},

    # --- offscope: not about plants -----------------------------------------
    {"query": "İneklerimin sütü azaldı, ne yapmalıyım?", "route": "offscope"},
    {"query": "Traktörümün motoru çalışmıyor, ne yapmalıyım?", "route": "offscope"},
    {"query": "Bu akşam hangi filmi izleyeyim?", "route": "offscope"},
    {"query": "Balık yetiştiriciliği nasıl yapılır?", "route": "offscope"},
    {"query": "Kredi çekmek istiyorum, hangi banka uygun?", "route": "offscope"},
    {"query": "Yarın hangi takım maç yapıyor?", "route": "offscope"},
]
