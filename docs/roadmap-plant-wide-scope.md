# Yol Haritası: "Bitki ile Alakalı Her Şey" Kapsamına Geçiş

**Durum:** Hipotetik / planlama. Şu an sistem bilinçli olarak **dar kapsamda**
(bitki besleme + toprak sağlığı + organik gübreleme) ve öyle kalıyor. Bu belge,
ileride kapsam genişletmeye karar verilirse ele alınacak konuları ve yapılacak
işleri kaydeder.
**Tarih:** 2026-07-14

## Üç kapsam seviyesi

| Seviye | Kapsar | Kapsamaz |
|---|---|---|
| **Dar (ŞU ANKİ)** | Bitki besleme, toprak sağlığı, organik/sürdürülebilir gübreleme, kompost, botanik eğitimi | Hastalık, zararlı, ıslah, sulama, hasat-sonrası, ekonomi, hayvancılık |
| **Bitki-geniş (bu belge)** | Bitkiyle ilgili HER konu (aşağıdaki tablo) | Hayvancılık, su ürünleri, tarım ekonomisi, mekanizasyon (bitki-dışı) |
| **Komple ziraat** | Tarımın tamamı | — |

"Bitki-geniş" bir **orta** kapsamdır: bugünkünden geniş, komple ziraatten dar.

## Ele alınacak konular

Şu an olmayanlar **kalın**:

1. Bitki besleme & gübreleme — ✅ var
2. Toprak bilimi (yapı, pH, tuzluluk, mikrobiyoloji) — kısmen
3. Bitki fizyolojisi & botanik (büyüme, fotosentez, anatomi) — kısmen
4. **Bitki hastalıkları (fitopatoloji)** — mantar/bakteri/virüs, teşhis, yönetim
5. **Zararlılar & entomoloji / IPM**
6. **Yabancı ot (weed science)**
7. **Bahçe bitkileri pratiği** — budama, aşılama, sera, meyve/sebze yetiştiriciliği (kısmen)
8. **Tarla bitkileri agronomisi** — ekim, rotasyon, örtü bitkisi (besleme ekseninde kısmen)
9. **Islah & genetik / çeşitler**
10. **Çoğaltma** — tohum, çelik, doku kültürü
11. **Sulama & bitki-su ilişkileri**
12. **Hasat sonrası** — depolama, olgunlaşma, kalite

## Yapılacak işler

### A. Guardrail & kapsam yeniden yazımı — ASIL MESELE
- `src/config.py` içindeki `SYSTEM_PROMPT`'un SCOPE, STRICT PROHIBITIONS ve
  IDENTITY bölümlerini yeniden yazmak.
- **Felsefi çatışma:** Sistem şu an *ekolojik/organik firma* asistanı olduğu için
  hastalık teşhisini **reddediyor** ve kimyasal pestisit önerisini **yasaklıyor**.
  "Bitki ile alakalı her şey" en azından hastalık/zararlıyı **konuşmayı**
  gerektirir. Karar verilmesi gerekenler:
  - Hastalık teşhisi verilecek mi? (sorumluluk riski)
  - Kimyasal mücadeleden bahsedilecek mi? (organik kimlikle çelişir)
  - Yoksa "sadece organik/kültürel/biyolojik mücadele öner" gibi bir orta yol mu?
- Self-tanım tekrar güncellenir (şu an: "bitki besleme, toprak sağlığı, organik
  gübreleme asistanı").

### B. Korpus genişletme (`docs/books/` + `src/ingest.py`)
- **İyi haber:** Fitopatoloji/entomoloji içeriğinin çoğu muhtemelen zaten
  korpusta (DergiPark ziraat dergileri hastalık/zararlı makaleleri içeriyor).
  Asıl eksik korpus değil, asistanın bunları **cevaplamaya izinli olmaması**.
- Yine de şu alanlar için **hedefli kaynak** eklenmeli: bahçe pratiği, ıslah,
  çoğaltma, sulama, hasat-sonrası.
- `fetch_dergipark.py`'daki off-topic filtresi (`_OFFTOPIC_REC`) gözden geçirilir
  — şu an sadece hayvancılık/su ürünleri düşürüyor; bitki hastalık/zararlı zaten
  geçiyor, yani bu tarafta büyük değişiklik gerekmez.
- Yeni fetcher kaynakları (opsiyonel): DOAJ, OpenAlex, FAO açık-erişim depoları.

### C. Product-linker etkisi (`src/engine.py`)
- Ürün kataloğu **organik gübre**. Asistan hastalık/zararlı konuşursa bunlar için
  **ürün yok** (firma pestisit satmıyor).
- `match_products` benzerlik eşiğiyle (`MIN_PRODUCT_SIMILARITY`) geçtiği için
  besleme-dışı konularda doğal olarak ürün önermez — işlevsel sorun değil.
- Sonuç: "ürün eşleme" değeri yalnızca **besleme alt-kümesinde** gerçekleşir; bu
  kabul edilmeli.

### D. Güvenlik / sorumluluk
- Hastalık teşhisi ve pestisit tavsiyesi sorumluluk taşır. Genişletme bunları geri
  açar → net disclaimer'lar ve "profesyonele danış" yönlendirmeleri şart.

### E. Retrieval / kalite (`src/config.py`, `src/engine.py`)
- Daha geniş kapsam → daha çeşitli sorgu → `retrieval_k` ve relevans/ürün
  eşiklerinin yeniden ayarlanması gerekebilir.
- Dil (TR + EN, bge-m3) sorun değil.

## Önerilen aşamalı plan (karar verilirse)

1. **Karar:** Organik kimlikle uyumu netleştir — hastalık/pestisit politikası
   (tam yasak / sadece organik-biyolojik mücadele / serbest). Bu, gerisini belirler.
2. **Guardrail v2:** `SYSTEM_PROMPT`'u yeni politikayla yaz; self-tanımı güncelle.
3. **Korpus denetimi:** Mevcut korpusun hastalık/zararlı/bahçe kapsamını ölç;
   eksik alanlara hedefli kaynak ekle, ingest et.
4. **Test:** Yeni konularda (hastalık, zararlı, budama, sulama) grounded cevap +
   guardrail testleri; product-linker'ın besleme-dışında sessiz kaldığını doğrula.
5. **Dokümantasyon:** README ve self-tanımı yeni kapsama göre güncelle.

## Özet karar noktası

Geçiş = esas olarak **guardrail felsefesi değişimi** (hastalık/zararlı/pestisit
reddini kaldırmak) + hedefli korpus ekleme + ürün-linker'ın yalnızca besleme
alt-kümesinde çalışacağını kabul etmek. Korpusun büyük kısmı zaten hazır; asıl
karar bu genişlemenin **organik-firma kimliğiyle uyumlu olup olmadığı**.
