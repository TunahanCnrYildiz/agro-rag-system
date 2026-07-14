# Global/Çok-Bölgeli Kaynak Araştırması ve Karşılaştırma

**Tarih:** 2026-07-14
**Amaç:** Tropik/global bitki-tarım içeriğini (manyok, plantain, sorgum, pirinç,
tropik meyveler…) korpusa eklemek için güvenilir, açık-erişim, **programatik
PDF indirilebilir** kaynakları değerlendirmek. Bir sonraki fetcher'ı seçmek için.

## Değerlendirme kriterleri
1. Programatik **indirilebilir PDF** linki verir mi? (kritik — ingest için PDF lazım)
2. **API** var mı, yoksa scraping mi? (fetcher yazma kolaylığı)
3. **Konu/ürün filtreleme** ne kadar hassas?
4. **Global/tropik** kapsam
5. **Lisans / erişim** (açık-erişim, indirilebilir mi)
6. **API key / rate-limit**

## Karşılaştırma

| Kaynak | PDF erişimi | API & key | Konu/ürün filtresi | Kapsam | Rate-limit | Fetcher zorluğu |
|---|---|---|---|---|---|---|
| **OpenAlex** ⭐ | OA location `pdf_url` (bazen landing page → doğrulama gerek) | REST, **key YOK** (polite pool: e-posta UA) | **En iyi** — 4 katmanlı Topic taksonomisi (Domain→Field→Subfield→Topic) + `is_oa:true` | ~250M+ eser, global, tüm alanlar | Bol (polite pool); yüksek hacimde usage-pricing | **Düşük** (temiz JSON, esnek filtre) |
| **FAO Knowledge Repository** | DSpace **bitstream = doğrudan PDF** ✓ | DSpace REST + **OAI-PMH**, key yok | AGROVOC konu + koleksiyon | FAO'nun kendi yayınları — otoriter, tropik/organik güçlü | Nazik olun | Düşük-orta (OAI-PMH, dergipark'a benzer) |
| **CORE** | Full-text'i **CORE barındırıyor** (güçlü) | REST v3, **key GEREKLİ** (ücretsiz) | `subjects`, `fullTextOnly` | 300M+ metadata, 40M+ full-text | **Dar:** 10 sn'de 1 batch / 5 tekil; max 10k sonuç | Orta |
| **Semantic Scholar** | `openAccessPdf` (varsa doğrudan link) | REST, key ops. | `fieldsOfStudy` = "Agricultural and Food Sciences" (**kaba**) | Büyük, global | **1 istek/sn** (key'li/siz benzer) | Düşük-orta |
| **DOAJ** | **Dolaylı** — yayıncı fulltext linki (DOAJ PDF barındırmaz) | REST, key ops. | Dergi düzeyi (23k+ OA dergi; "Agriculture", "Open Agriculture") | Sadece OA dergiler | Nazik | Orta (link çözümleme gerek) |
| **FAO AGRIS ODS** | **Dolaylı** — full-text linkleri (barındırma değişken) | Bulk **ZIP** indirme (CC BY 4.0) + arayüz | AGROVOC | 16M+ kayıt, global tarım | — | Orta (bulk parse + link çözümleme) |

## Öne çıkanlar

- **OpenAlex** — en yüksek ROI: key yok, en hassas konu/ürün filtresi, doğrudan OA
  PDF linkleri (bizim `fetch_dergipark`'taki gibi %PDF doğrulama + landing→PDF
  çözümleme ile), devasa global kapsam. Bir sonraki fetcher için **ideal.**
- **FAO Knowledge Repository** — otoriter tropik/organik referans yayınları;
  DSpace bitstream = temiz doğrudan PDF, OAI-PMH ile hasat kolay. Dar ama
  yüksek-kalite (FAO'nun kendi yayınları).
- **CORE** — full-text'i kendi barındırdığı için PDF garantisi güçlü; ama key +
  dar rate-limit. İyi bir *fallback*.
- **Semantic Scholar** — basit ama field filtresi kaba, 1 istek/sn yavaş.
- **DOAJ / AGRIS** — keşif/metadata için iyi ama PDF erişimi dolaylı (yayıncı
  linki çözmek gerek) → fetcher daha kırılgan.

## Öneri: aşamalı

1. **İlk fetcher: OpenAlex** (`src/fetch_openalex.py`). Konu (agronomi, bitki
   bilimi, fitopatoloji) + `is_oa:true` filtreleyip tropik/global ürünlere odaklı
   hasat. PDF'i OA location'dan al, %PDF + boyut doğrula (mevcut desenimiz).
2. **İkinci: FAO Knowledge Repository** (OAI-PMH) — otoriter FAO tropik/organik
   yayınları; temiz doğrudan PDF.
3. **CORE** — sadece belirli boşluklar için fallback (key + rate-limit'e değerse).

## Ortak dikkat noktaları (tüm kaynaklar)
- **Landing-page vs doğrudan PDF:** OpenAlex/DOAJ linkleri bazen HTML sayfası →
  `fetch_dergipark`'taki gibi landing→PDF çözümleme + %PDF header doğrulama şart.
- **Deduplication:** Aynı makale birden çok kaynakta olabilir → **DOI bazlı**
  dedup (yoksa aynı içeriği tekrar ingest ederiz).
- **Off-topic filtresi:** OA tarım makaleleri de hayvancılık/ekonomi içerir →
  mevcut `_OFFTOPIC_REC` + `--clean-offtopic` mantığını her kaynağa uygula.
- **Nazik olmak:** User-Agent + gecikme + 429 backoff (dergipark'taki gibi).
- **Kalite > nicelik:** hedefli (boşluk olan ürünler), filtreli, deduplike.

## Kaynaklar (referans)
- OpenAlex Works API: https://developers.openalex.org/api-reference/works
- FAO Knowledge Repository: https://openknowledge.fao.org/ · AGRIS ODS: https://www.fao.org/agris/agris-ods
- CORE API v3: https://api.core.ac.uk/docs/v3
- Semantic Scholar Academic Graph API: https://www.semanticscholar.org/product/api
- DOAJ API: https://doaj.org/api/docs
