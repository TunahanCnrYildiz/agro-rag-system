# Yol Haritası: "Bitki ile Alakalı Her Şey" Kapsamına Geçiş

**Durum:** ✅ **UYGULANDI (2026-07-14).** "Önerilen kapsam" (bitki-geniş eksi
teşhis/kimyasal) benimsendi ve `src/config.py` SYSTEM_PROMPT'una yansıtıldı;
off-scope reddinde ürün önerisi de susturuldu (`[OFFSCOPE]` marker,
`src/engine.py`). Sıradaki yön: aşağıdaki **Global / çok-bölgeli kapsam**.
**Tarih:** 2026-07-14

## Üç kapsam seviyesi

| Seviye | Kapsar | Kapsamaz |
|---|---|---|
| **Dar (ŞU ANKİ)** | Bitki besleme, toprak sağlığı, organik/sürdürülebilir gübreleme, kompost, botanik eğitimi | Hastalık, zararlı, ıslah, sulama, hasat-sonrası, ekonomi, hayvancılık |
| **Bitki-geniş (bu belge)** | Bitkiyle ilgili HER konu (aşağıdaki tablo) | Hayvancılık, su ürünleri, tarım ekonomisi, mekanizasyon (bitki-dışı) |
| **Komple ziraat** | Tarımın tamamı | — |

"Bitki-geniş" bir **orta** kapsamdır: bugünkünden geniş, komple ziraatten dar.

## ÖNERİLEN kapsam: "Bitki-geniş EKSİ teşhis/kimyasal"

Bitki-geniş kapsamı al, ama **iki carve-out'u koru**: (a) kesin hastalık teşhisi
koyma, (b) kimyasal pestisit/fungisit/herbisit/ilaç önerme. Geri kalan her şeyi
(fizyoloji, toprak, bahçe pratiği, agronomi, çoğaltma, sulama, hasat-sonrası ve
**organik/kültürel/biyolojik** hastalık-zararlı yönetimi) dahil et.

Organik bir firma için bu **optimuma yakın** kapsamdır. Dezavantaj neredeyse yok:

**Avantajlar**
- **Marka uyumu:** Organik firma zaten kimyasal önermemeli — reddetmek eksiklik
  değil, tutarlılık ve güçlü konumlanma.
- **Sorumluluk koruması:** Teşhis ve ilaç dozu hukuki/güvenlik riski; dışarıda
  kalması firmayı korur.
- **Product-linker tutarlı:** Kimyasalda zaten ürün yok; ama organik hastalık/
  zararlı yönetimi (mikoriza, biyolojik ürünler, kompost çayı) için ürün varsa
  linker orada da devreye girer — genişleme değer bile katar.

**Yönetilecek küçük dezavantajlar**
- Hastalık/zararlı konusu "yarım" kapsanır: genel belirti + organik önlem +
  profesyonele yönlendirme verilir, kesin teşhis/kimyasal verilmez. Tam-hizmet
  danışman bekleyen kullanıcı eksik bulabilir.
- **Sınır-sürtünmesi (asıl dikkat):** Konuya girip iki noktada "yapamam" demek,
  temiz reddetmekten daha sinir bozucu olabilir. **Çözüm:** guardrail'i
  "yapamadığın" değil, **"yapabildiğin organik çözüm" ekseninde** kur — cevap
  çıkmaz sokak değil, faydalı organik tavsiye olsun.
- Konumlanma algısı: "komple ziraat"e göre sınırlı görünür; ama bu bilinçli ve
  organik marka için doğru bir tercih.

**Sonuç:** Bu, genişleme yapılacaksa **önerilen hedeftir** — geniş kapsama ulaşır,
ama markayı ve sorumluluğu koruyan iki sınırı korur.

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

---

# Global / Çok-Bölgeli Kapsam (sıradaki yön)

**Motivasyon:** AI'a sadece TR/EN değil, farklı ülkelerden farklı dillerde soru
gelecek. Afrikalı bir çiftçi manyok (cassava), plantain, teff; Latin Amerikalı
biri yuca, quinoa sorabilir. Sistem bunlara "cahil" kalmamalı.

## Kritik ayrım: DİL değil, İÇERİK (bilgi kapsamı)

- **Soru dili — zaten çözülü.** `build_language_instruction` + dil algılama →
  asistan kullanıcının dilinde cevaplıyor; bge-m3 her dildeki sorguyu embed edip
  çapraz-dil retrieval yapıyor. Fransızca/Arapça/İspanyolca soru **teknik olarak
  zaten çalışıyor.**
- **Asıl boşluk — içerik kapsamı.** Korpus şu an **Türkiye tarımı (DergiPark,
  ılıman/Akdeniz) + ABD/ılıman İngilizce** ağırlıklı. Tropik/Afrika/Asya bölgesel
  ürünleri (manyok, plantain, sorgum, börülce, tropik meyveler, pirinç
  çeşitleri) **zayıf kapsanıyor.** Afrikalı çiftçi manyok sorunca AI cahil kalır
  çünkü **o ürün hakkında içerik yok** — dili bilmediğinden değil.

## Strateji

1. **Öncelik: bölgesel/global ürün İÇERİĞİ ekle.** Uluslararası tarım biliminin
   çoğu **İngilizce** yayımlanır → dil değiştirmeden çok sayıda global ürünü
   kapsayabiliriz. Güvenilir açık-erişim kaynaklar:
   - **FAO** belge deposu (tropik/global bitki üretim & koruma, otoriter)
   - **CGIAR merkezleri:** IITA (tropik Afrika), CIP (patates), ICRISAT (kurak
     bölge tahılları: sorgum, darı), IRRI (pirinç), CIAT (fasulye/manyok)
   - Uluslararası açık-erişim dergiler (DOAJ / OpenAlex üzerinden bölge+ürün
     filtreli)
2. **Yabancı-dil içeriği — sadece hedefli.** Bilgi özgün olarak o dilde varsa:
   Frankofon Afrika için Fransızca, Latin Amerika için İspanyolca/Portekizce.
   bge-m3 bunları kullanılabilir kılar. "Her dilde her şeyi tara" DEĞİL.

## Dürüst uyarılar / kararlar

- **Chat modeli (gemma-4-12b)** düşük-kaynaklı dillerde (Amharca, Svahili) kalite
  düşürebilir; büyük dillerde (ES/FR/PT/AR/HI) sorun yok. bge-m3 de yüksek-kaynaklı
  dillerde daha isabetli.
- **Product-linker coğrafya sorunu:** Katalog Türk firmasının organik gübreleri.
  Tavsiye globalleşebilir ama **ürünler globalleşemez** (yurt dışı çiftçi satın
  alamaz). Karar: yurt dışı kullanıcıda ürün önerisi susturulacak mı (bölge/dil
  bazlı), yoksa "sadece tavsiye" modu mu? — netleştirilmeli.
- Her yeni kaynak = yeni fetcher (kod) + alaka/kalite filtresi + `--clean-offtopic`
  benzeri temizlik. **Kalite > nicelik** kuralı burada da geçerli.

## Aşamalı plan

1. **Kaynak araştırması:** FAO / CGIAR / DOAJ / OpenAlex açık-erişim + PDF erişim
   yollarını belirle.
2. **İlk fetcher:** En yüksek getirili biriyle başla (ör. OpenAlex API — konu/ürün
   filtreli, açık-erişim PDF linkleri; ya da FAO).
3. **Hedefli hasat:** Boşluk olan global ürünlere odaklan (tropik/Afrika/Asya);
   indir → ingest → cleanup.
4. **Test:** Global ürün sorgularıyla (manyok, plantain, sorgum) ve farklı
   dillerde (FR/ES) grounded cevap doğrula.
5. **Product-linker/coğrafya kararını** uygula (yurt dışı için ürün politikası).
