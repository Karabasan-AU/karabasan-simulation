# shared/ — Merkezi Altyapı Dokümantasyonu

Bu dizin, tüm modüllerin ortak kullandığı yapılandırma, DSP yardımcıları ve loglama altyapısını barındırır.

---

## İçerik

```
shared/
├── config.json       # Merkezi yapılandırma (soket adresleri, I/Q parametreleri, mesaj şemaları)
├── dsp_utils.py      # Ortak DSP fonksiyonları (filtreler, FFT sarmalayıcıları, pencere fonksiyonları)
├── logger.py         # Merkezi loglama modülü
└── README.md         # Bu dosya
```

---

## config.json Kullanım Kılavuzu

### Hangi blok ne için?

| Blok | Kim kullanır | Amaç |
|---|---|---|
| `sockets` | Tüm modüller | ZMQ/WebSocket/REST bağlantı adresleri |
| `simulation` | `sim_engine`, `generators`, `ed_system` | Fiziksel kanal modellemesi parametreleri |
| `ml_pipeline` | `ed_system` (sınıflandırıcı), eğitim scriptleri | HisarMod uyumlu normalize parametreler |
| `synthetic_signal_params` | `generators` | Modülasyon üretim parametreleri |
| `antenna_array` | `sim_engine`, `ed_system` | TDOA / faz karşılaştırma geometrisi |
| `websocket_schemas` | `ed_system`, `ui` | Mesaj formatı referansı |
| `logging` | Tüm modüller | Log seviyesi ve çıktı hedefi |

---

### ⚠️ Kritik: İki Farklı Sample Rate

`config.json` içinde iki farklı `sample_rate` değeri bulunmaktadır. Bu kasıtlıdır ve karıştırılmamalıdır:

#### `simulation.sample_rate` = 200,000 Hz
- **Fiziksel değerdir.** FSPL, AWGN ve TDOA hesaplarında kullanılır.
- Nanosaniyelik varış zamanı farkı (TDOA) bu değere göre hesaplanır.
- `sim_engine`, `generators` ve `ed_system`'in kanal modelleme kısmı bu bloğu okur.

#### `ml_pipeline.sample_rate` = 1.0 Hz (normalize)
- **Fiziksel değil, boyutsuz bir sayıdır.**
- HisarMod veri setindeki I/Q örnekleriyle uyum için kullanılır.
- Yalnızca `ed_system` içindeki sınıflandırıcı modeli ve eğitim scriptleri bu bloğu okur.
- `sim_engine` veya herhangi bir kanal modeli bu değeri **kesinlikle kullanmamalıdır.**

> **Kural:** `sim_engine` veya TDOA/FSPL hesabı yapan herhangi bir kod `ml_pipeline` bloğunu okuyorsa bu bir **hata**dır.

---

### Center Frequency: Neden 0.0 Hz?

Proje baseband (temel bant) I/Q mimarisi üzerine kuruludur:

- `generators/` her sinyali 0 Hz merkezli (baseband) üretir. GPS L1 gibi gerçek frekanslı sinyaller `synthetic_signal_params` içinde referans için belgelenmiştir ancak `sim_engine` içinde baseband'e indirgenerek işlenir.
- HisarMod veri seti de baseband formatındadır; bu sayede ML modeli frekans bağımsız çalışır ve tüm modülasyon sınıfları aynı frekans düzleminde eşleşir.

---

## Soket Bağlantı Rehberi

Her modülün bağlanması gereken soketler:

| Modül | Okuduğu soket | Yazdığı soket |
|---|---|---|
| `generators` | — | `sockets.generators_to_sim` (PUBLISH) |
| `sim_engine` | `sockets.generators_to_sim` (SUBSCRIBE) | `sockets.sim_to_ed` (PUBLISH) |
| `sim_engine` | `sockets.et_to_sim` (SUBSCRIBE) | *(hedef sinyalle birleştirir)* |
| `ed_system` | `sockets.sim_to_ed` (SUBSCRIBE) | `sockets.ed_to_ui` (WebSocket SEND) |
| `et_system` | `sockets.ui_to_et` (REST dinler) | `sockets.et_to_sim` (PUBLISH) |
| `ui` | `sockets.ed_to_ui` (WebSocket RECEIVE) | `sockets.ui_to_et` (REST POST) |

---

## WebSocket Mesaj Şemaları (ed_system → ui)

Tüm mesajlar JSON formatındadır ve `event` alanı içerir. Tam şema `config.json` → `websocket_schemas` altındadır.

### Özet

| Event | Tetikleyici | Kritik Alanlar |
|---|---|---|
| `detection` | Yeni sinyal tespit edildiğinde | `signal_id`, `center_freq_hz`, `modulation` |
| `location` | DF/TDOA sonucu hazır olduğunda | `signal_id`, `azimuth_deg`, `estimated_x_m/y_m` |
| `demodulation` | Ses/veri çıktısı hazır olduğunda | `signal_id`, `audio_chunk_b64` |
| `jamming_status` | Karıştırma durumu değiştiğinde | `active`, `mode`, `jsr_db` |

> `signal_id` (UUID), aynı sinyale ait birden fazla event'i `ui`'da ilişkilendirmek için kullanılır. `ed_system` sinyal ömrü boyunca aynı ID'yi korumalıdır.

---

## Format Değişikliği Protokolü

`config.json` içindeki herhangi bir alan değiştirildiğinde:

1. **Değişikliği yapan kişi** önce takım kaptanıyla birebir görüşür.
2. Onay alındıktan sonra PR açılır; PR açıklamasında hangi modüllerin etkilendiği listelenir.
3. **Etkilenen modüllerin sorumluları** PR'ı inceleyip onaylar — takım kaptanının onayı tek başına yeterli değildir.
4. Merge sonrası takım kaptanı Slack'te `#eh-proje-genel` kanalında bildirim gönderir.

> Özellikle `websocket_schemas` değişikliklerinde `ed_system` ve `ui` sorumlularının **ikisi birden** onay vermelidir.

---

## Simülasyondan Donanıma Geçiş

Donanım temin edildiğinde yalnızca `sockets` bloğundaki adresler değiştirilir:

```jsonc
// Simülasyon
"sim_to_ed": { "address": "zmq://localhost:5556" }

// Donanım (ADALM-Pluto SDR)
"sim_to_ed": { "address": "ip:192.168.2.1" }
```

`simulation`, `ml_pipeline` ve `websocket_schemas` blokları **değişmez.**

---

## Sorular

Önce bu dosyayı ve `config.json` içindeki `_comment` alanlarını okuyun. Yanıt bulamazsanız takım kaptanıyla iletişime geçin.