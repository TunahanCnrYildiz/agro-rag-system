# Buraya ne konacak

TÜİK'ten elle indirilen iki export. Bunlar `scripts/build_crop_norms.py`'ın girdisi;
betik `data/crop_norms.json`'u bunlardan üretir. Yılda bir kez yenilenir.

Kaynak: https://biruni.tuik.gov.tr/medas/?kn=92&locale=tr

1. Konu: **Bitkisel Üretim İstatistikleri**
   - Göstergeler: üretim ve verim
   - Zaman: son 10 yıl
   - Düzey: **İl** (seçenek varsa)

2. Konu: **Tarımsal Ürün Fiyatları ve Üretim Değerleri**
   - Aynı şekilde.
   - `Tarım Ürünleri Üretici Fiyat Endeksi` DEĞİL. O bir endekstir, verimle
     çarpılamaz; gelir hesabına giremez.

Dosyalar indirildikleri hâliyle commit'lenir. Girdisi repoda olmayan bir
dönüştürücü ne yeniden çalıştırılabilir ne de incelenebilir.
