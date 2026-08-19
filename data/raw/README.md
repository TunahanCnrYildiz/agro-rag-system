# Buraya ne konacak

TÜİK'ten elle indirilen export'lar. Bunlar `scripts/build_crop_norms.py`'ın girdisi;
betik `data/crop_norms.json`'u bunlardan üretir. Yılda bir kez yenilenir.

Kaynak: https://biruni.tuik.gov.tr/medas/?kn=92&locale=tr

## MEDAS'ın yapısı (2026-08-17'de ekranda doğrulandı)

"Üretim" ve "verim" ÜST SEVİYEDE GÖSTERGE DEĞİL. Sıra şöyle:

1. `Konu` = **Bitkisel Üretim İstatistikleri**
2. `Ölçüm` = ÜRÜN GRUBU, ölçü birimi değil. Seçenekler:
   Tarım alanı · Tahıllar ve diğer bitkisel ürünler · Sebzeler ·
   Meyveler içecek ve baharat bitkileri · Süs bitkileri · Örtüaltı sebzeler ·
   Örtüaltı meyveler · Örtüaltı süs bitkileri · Örtüaltı tarım alanı ·
   (Kuru / Sulu) - (1. Ekiliş / 2. Ekiliş) ürünleri
3. Bir ürün grubu seçilince sağda `Kırılım Seçiniz` paneli açılır:
   `Ürün niteliği` · `Ürünler` · **`Ölçü birimi`**
   Üretim miktarı / verim / ekilen alan **`Ölçü birimi` altındadır.**
   Kırmızı renkli kırılımların seçilmesi zorunludur.
4. Sonra `Zaman`, `Düzey`, `Rapor` sekmeleri.

## İL KIRILIMI VAR - adı "İl" değil

`Düzey` sekmesindeki seçenekler (2026-08-17'de ekranda görüldü):
Türkiye · İBBS1 · İBBS2 (26 Bölge) · **İBBS3 (İl Düzeyi)** · İlçe Düzeyi

Bize gereken **İBBS3 (İl Düzeyi)**. Yani spec'in `scope: "il"` dalı gerçek;
`scope: "tr"` sadece fiyat tarafında gerekebilir.

## SERT SINIR

Ekranın altında yazıyor: **gösterge × düzey × zaman ≤ 50000**.
81 il sabit olduğuna göre bütçe:
  16 yıl ->  38 gösterge
  10 yıl ->  61 gösterge
   5 yıl -> 123 gösterge

Bir ürün grubunu tüm ürünleri ve tüm ölçü birimleriyle seçmek 395 gösterge
üretiyor; 395 x 81 x 16 = 512.000, yani sınırın on katı. Kesilecek yer İL
DEĞİL, gösterge sayısı: ölçü birimini tek seçeneğe (verim) indir ve ürünleri
sınırla. Bu yüzden TEK dosya çıkmaz - ürün grubu basina, ve ölçü birimi
başına, ayrı export gerekir. Hepsini buraya koy, dönüştürücü birleştirir.

## İkinci konu

`Tarımsal Ürün Fiyatları ve Üretim Değerleri` - aynı mantıkla.
`Tarım Ürünleri Üretici Fiyat Endeksi` DEĞİL: o bir endekstir, verimle
çarpılamaz, gelir hesabına giremez.

## En kritik gözlem

`Düzey` sekmesinde **İl** seçeneği var mı? Her iki konu için de.
Yoksa da tasarım bunu karşılıyor (`scope: "tr"`), ama bilinmesi gerekiyor.

Dosyalar indirildikleri hâliyle commit'lenir. Girdisi repoda olmayan bir
dönüştürücü ne yeniden çalıştırılabilir ne de incelenebilir.
