# Yol Haritası: Deployment (Lokal → Hosted)

**Durum:** Planlama. Şu an her şey **lokal** çalışıyor (LM Studio + LAN) ve
kısa vadede öyle devam edecek. Bu belge, lokali bozmadan hosting'e geçişi fazlı
kaydeder.
**Tarih:** 2026-07-14

## Anahtar içgörü: geçiş bir config swap'ı, yeniden yazım değil

`engine.py` LLM'e **OpenAI-uyumlu client** ile bağlanıyor
(`base_url`+`api_key`+`model`, hepsi `.env`'den; `settings` üzerinden). LM Studio
da OpenAI-uyumlu. Embedding de aynı (`OpenAIEmbeddings(base_url=…, model=…)`).
Yani **"lokal → hosted"** temelde `LM_STUDIO_BASE_URL` / model isimlerini
değiştirmek. Kod provider-agnostik. Bu yüzden lokalde kalmak **sorun yaratmaz** —
tek şart, aşağıdaki 3 kuralı korumak.

## Lokal-şimdiyi geleceğe-uyumlu tutan 3 kural
1. **Embedding modeli kilidi (en kritik):** Store **bge-m3** ile kuruldu.
   Hosted'da embedding **bge-m3 olmalı**, yoksa **tüm store'u yeniden indeksle**.
2. **Hardcoded URL yok:** `mobile-app/src/api.ts`'deki `API_BASE` sabit LAN IP;
   env/config'e alınmalı (aşağıda "şimdi yapılacaklar").
3. **HTTP→HTTPS & CORS** sadece hosting fazında; lokali etkilemez.

## Fazlar

### Faz 0 — Config hijyeni (ŞİMDİ, lokali bozmaz)
- `mobile-app` `API_BASE`'ini **env/build-config'e al** (ör. Expo `extra` /
  `EXPO_PUBLIC_*` env). Backend URL'i değiştirmek kod düzenleyip yeniden
  build gerektirmesin.
- Hosting env değişkenlerini `.env.example`'da netleştir (zaten çoğu var:
  `LM_STUDIO_BASE_URL`, `EMBEDDING_MODEL`, `CHAT_MODEL`, `CORS_ALLOW_ORIGINS`).
- **Çıktı:** lokal aynen çalışır, ama URL/CORS artık dışarıdan ayarlanabilir.

### Faz 1 — Backend'i containerize et (ŞİMDİ/yakın, lokalde)
- `Dockerfile` (FastAPI + uvicorn) + `.dockerignore` (data/, docs/books, node
  hariç). `data/vector_store`'u **volume** olarak mount et (git'te değil).
- Container'ı **lokalde** çalıştır ama **hâlâ lokal LM Studio'ya** bağlan
  (`LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1`).
- **Çıktı:** taşınabilir container; lokal dev bozulmadan production-benzeri koşum.
- **İnterim dış erişim (opsiyonel):** off-LAN mobil test / demo için lokal
  FastAPI'yi **cloudflared/ngrok tunnel** ile HTTPS public URL'e aç (tam hosting
  değil, ama hemen çalışır).

### Faz 2 — Backend'i host'a taşı (SONRA)
- Host seç (VPS / Fly.io / Render / Railway). **HTTPS** (platform TLS ya da
  reverse proxy) + **kalıcı disk** (`data/vector_store` ~1.4 GB, git'te yok).
- Env/secrets ayarla; `CORS_ALLOW_ORIGINS`'i daralt.
- `mobile-app` `API_BASE` → hosted HTTPS URL (Faz 0 sayesinde sadece config).
- **Çıktı:** internetten erişilebilir backend; ama LLM hâlâ nerede?

### Faz 3 — LLM + embedding'i host'la (SONRA — asıl karar)
Sadece `LM_STUDIO_BASE_URL` (+ model isimleri, + varsa embedding endpoint) swap'ı.
**Embedding bge-m3 kalmalı, yoksa re-index.** Seçenekler aşağıda.

## LLM/embedding hosting seçenekleri (karar ertelendi — sunum)

| Seçenek | Artı | Eksi |
|---|---|---|
| **A) Self-hosted GPU** (bulut GPU'da vLLM/Ollama/LM Studio ile **gemma + bge-m3**) | Aynı modeller → **re-index YOK**; veri kontrolü sende; sabit maliyet | GPU kirası ($/ay) + ops (kurulum, ölçekleme, uptime) |
| **B) Managed OpenAI-uyumlu API** (Together / Groq / OpenRouter / DeepInfra) | GPU ops yok; en hızlı kurulum; ölçeklenir | Token başına ücret; **veri dışarı çıkar**; **bge-m3 sunan sağlayıcı** gerek (yoksa embedding'i ayrı çöz / re-index) |
| **C) Hibrit / tunnel** (lokal LLM + cloudflared) | Ücretsiz; hemen çalışır | Prod-değil: PC açık olmalı, ölçeklenmez, kırılgan — sadece demo/test |

**Not — embedding ayrı düşünülebilir:** Chat modelini managed API'den (B) alıp,
**embedding'i (bge-m3) self-host** etmek mümkün — böylece re-index'ten kaçınırsın
ve chat için ops yükü olmaz. Karma yaklaşım genelde en pratik.

## Riskler / kararlar
- **Embedding lock-in (bge-m3)** — hosting seçimini bu belirler.
- **Store boyutu (~1.4 GB)** — host'ta kalıcı disk; git'e girmez, deploy'da kopyala/rebuild.
- **Maliyet** — Faz 3'te GPU kirası (A) vs token ücreti (B).
- **Veri gizliliği** — managed API (B) sorguları dışarı gönderir; firma için önemliyse A/C.
- **LLM hızı** — lokalde yavaş (8 tok/s); hosted GPU/API bunu da **çözer** (bonus).

## Önerilen sıra
Faz 0 (config hijyeni) + Faz 1 (Docker) **şimdi** yapılabilir; lokali bozmaz ve
Faz 2-3'ü açar. Faz 2-3 (hosting) hazır olunca, LLM-hosting kararıyla birlikte.
Her fazdan sonra `python -m evals.run_eval` ile kalitenin bozulmadığını doğrula.
