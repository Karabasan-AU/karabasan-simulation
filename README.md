# TEKNOFEST 2026 Elektronik Harp Projesi

Bu depo, TEKNOFEST 2026 Elektronik Harp yarışması kapsamında geliştirilen Elektronik Destek (ED)
ve Elektronik Taarruz (ET) sistemlerinin tüm kaynak kodlarını tek bir yapı altında barındırmaktadır.

Proje, donanım bağımsız bir simülasyon mimarisine dayalıdır. Saha testlerine veya SDR (Yazılım
Tanımlı Radyo) donanımına ihtiyaç duymadan; sinyal üretimi, kanal modellemesi, sinyal işleme
algoritmaları ve taarruz teknikleri tamamen yazılım ortamında geliştirilip test edilmektedir. Fiziksel
donanım temin edildiğinde, kod tabanı değiştirilmez; yalnızca veri kaynağı ve hedefi yapılandırma
dosyasından güncellenir.

---

## Genel Mimari

Projedeki her klasör birbirinden bağımsız bir sorumluluk alanını kapsar. Modüller birbirleriyle doğrudan
fonksiyon çağrısı üzerinden değil, ağ soketleri (ZMQ veya UDP) ve belgelenmiş mesaj formatları
üzerinden haberleşir. Bu sayede bir ekip üyesi kendi modülünü diğerlerinden bağımsız olarak
geliştirebilir ve test edebilir.

```
eh_proje/
├── generators/
├── sim_engine/
├── ed_system/
├── et_system/
├── ui/
├── shared/
├── docker-compose.yml
└── README.md
```

---

## Klasör Açıklamaları

### generators/

**Ne yapar:** Yarışmada karşılaşılacak hedef sinyalleri matematiksel olarak üretir.

**İçeriği:** Her biri belirli bir sinyal tipini modelleyen Python betikleri. Örneğin:
- Analog amatör telsiz için FM modülasyonlu I/Q veri akışı
- ISM modülleri için FSK veya OOK sinyalleri
- Drone kumanda frekansları için DSSS tabanlı sinyaller
- GNSS aldatma senaryoları için GPS L1 ve diğer servislerin sinyalleri

**Çıktı:** ZMQ soket üzerinden yayınlanan ham I/Q (In-phase / Quadrature) veri akışı.
Üretilen sinyaller gürültüsüz ve idealize edilmiş olup, sim_engine bu sinyallere gerçek
ortam koşullarını uygular.

**Sorumluluk:** Sinyal üretimi ve modülasyon matematiği üzerinde çalışan ekip üyeleri.

---

### sim_engine/

**Ne yapar:** Hedef sinyallerine fiziksel ortam etkilerini uygular ve sistemin tüm bileşenlerini
birbirine bağlayan merkezi veri yönlendirmesini yönetir.

**İçeriği:**

- **Geometri Yöneticisi:** Hedeflerin ve alıcı antenlerin 1x1 km sanal haritadaki koordinatlarını
  tutar. Hareketli hedefler (İHA gibi) için zaman bağımlı konum güncellemelerini hesaplar.

- **Zayıflama Modeli:** generators'dan gelen saf sinyale Serbest Uzay Yol Kaybı (FSPL) modelini
  uygulayarak sinyal genliğini mesafeye göre düşürür.

- **Gürültü Modeli:** Düşürülmüş sinyalin üzerine AWGN (Additive White Gaussian Noise) ekleyerek
  gerçek ortam gürültüsünü simüle eder.

- **Faz ve Zaman Gecikmesi:** Çoklu anten mimarisi için kritik bir bileşendir. Hedefin konumuna ve
  anten diziliminin geometrisine göre her antene gelen sinyalin nanosaniyelik varış zamanı farkını
  (Time Difference of Arrival) ve faz kaymasını hesaplar. ED sistemindeki TDOA ve Faz
  Karşılaştırmalı Yön Bulma algoritmaları bu verilerle çalışır.

- **Sinyal Birleştirme:** et_system'den gelen karıştırma sinyali ile generators'dan gelen hedef
  sinyalini, aynı frekanstaki sinyallerin havada gerçekte yaptığı gibi toplar. Bu, karıştırma
  etkinliğini (JSR: Jammer-to-Signal Ratio) matematiksel olarak ölçmeyi mümkün kılar.

**Sorumluluk:** Ortam modellemesi, RF yayılım matematiği ve modüller arası veri yönlendirmesi.

---

### ed_system/

**Ne yapar:** Gelen I/Q veri akışını analiz ederek Elektronik Destek görevlerini yerine getirir.

**İçeriği:** Yarışma şartnamesinde tanımlanan her ED alt görevine karşılık gelen bir modül:

- **Sinyal Tespiti:** FFT (Hızlı Fourier Dönüşümü) tabanlı güç spektrum yoğunluğu hesabı ve
  gürültü tabanının üzerindeki sinyallerin otomatik olarak işaretlenmesi.

- **Parametre Çıkarımı:** Tespit edilen sinyalin merkez frekansı, bant genişliği, güç seviyesi,
  modülasyon türü ve (varsa) FHSS/DSSS gibi karşı tedbir özelliklerinin hesaplanması.

- **Sinyal İzleme ve Dinleme:** Sinyalin demodülasyonu ve ham veri veya ses çıktısının elde
  edilmesi.

- **Yön Bulma (DF):** Faz Karşılaştırmalı veya TDOA yöntemleri kullanılarak sinyalin geliş
  açısının (Azimut) hesaplanması.

- **Konum Belirleme:** Birden fazla alıcıdan elde edilen LOB (Line of Bearing) veya TDOA
  ölçümlerinin kesiştirilmesiyle hedefin iki boyutlu haritadaki konumunun tahmin edilmesi.

**Geliştirme kuralı:** Bu dizindeki hiçbir modül, verinin simülasyondan mı yoksa fiziksel SDR
donanımından mı geldiğini bilmemelidir. Bağlantı noktaları shared/config.json içinde tanımlanır
ve sadece o dosya değiştirilerek hedef değiştirilir.

**Sorumluluk:** DSP (Dijital Sinyal İşleme) algoritmaları, yapay zeka tabanlı sınıflandırma ve
parametre çıkarımı.

---

### et_system/

**Ne yapar:** Elektronik Taarruz sinyalleri üretir.

**İçeriği:**

- **Sürekli Karıştırma:** Belirlenen frekans veya frekans aralığında kesintisiz gürültü yayını.
  Tekli, çoklu ve baraj karıştırma modlarını destekler.

- **Arabakışlı Karıştırma:** Karıştırma ve dinleme fazlarını belirlenmiş sürelerle dönüşümlü olarak
  yönetir. Hedef sinyalin varlığı ve durumu izlenerek karıştırma etkinliği sürekli doğrulanır.

- **Analog Telsiz Aldatma:** Hedef telsizin kullandığı modülasyon formatında sahte ses içeriği
  üretir ve yayınlar.

- **GNSS Aldatma:** GPS L1 ve diğer servisler için sahte uydu sinyalleri oluşturur. Sahte konum
  mesajları hedef alıcının gerçek konumu yerine üretilen konumu bildirmesine neden olur.

**Çıktı:** Simülasyon aşamasında sim_engine'e yönlendirilen I/Q veri akışı. Saha aşamasında
aynı veri, SDR donanımının TX portuna yönlendirilir.

**Sorumluluk:** Karıştırma ve aldatma algoritmalarını geliştiren ekip üyeleri.

---

### ui/

**Ne yapar:** Operatörün sistemi yönettiği kullanıcı arayüzünü sağlar.

**İçeriği:**

- Spektrogram ve şelale (waterfall) görselleştirme
- Tespit edilen hedeflerin harita üzerinde konumlandırılması
- Yön bulma (DF) sonuçlarının görsel olarak sunulması
- Karıştırma ve aldatma görevlerinin başlatılması ve izlenmesi için kontrol paneli

**Geliştirme kuralı:** Arayüz modülü doğrudan DSP veya sinyal işleme işlemi yapmaz. ed_system
ve et_system'den WebSocket veya REST üzerinden gelen verileri görselleştirir ve kullanıcı
komutlarını ilgili modüle iletir.

**Sorumluluk:** Arayüz geliştirmesi ve veri görselleştirme.

---

### shared/

**Ne yapar:** Tüm modüllerin ortak kullandığı yardımcı fonksiyonları ve yapılandırmayı içerir.

**İçeriği:**

- Ortak DSP fonksiyonları (filtreler, pencere fonksiyonları, FFT sarmalayıcıları)
- Loglama ve hata yönetimi altyapısı
- config.json: Merkezi yapılandırma dosyası. Modüllerin birbirine bağlandığı soket adresleri,
  örnekleme hızı (sample rate), merkez frekansı gibi parametreler burada tutulur. Simülasyondan
  donanıma geçerken değiştirilmesi gereken tek dosyadır.

---

## Veri Akışı

```
generators          ->  ZMQ/UDP  ->  sim_engine
sim_engine          ->  ZMQ/UDP  ->  ed_system
ed_system           ->  WebSocket/JSON  ->  ui
ui                  ->  REST/RPC  ->  et_system
et_system           ->  ZMQ/UDP  ->  sim_engine
```

---

## Geliştirme Kuralları

**Donanım soyutlaması:** Modüller donanım API'lerine doğrudan bağımlı olmamalıdır. Tüm girdi
ve çıktılar ağ soketleri veya I/Q dosya akışları üzerinden sağlanmalıdır. Donanım adresi
yalnızca shared/config.json içinde tanımlanır.

**Konteyner kullanımı:** İşletim sistemi ve kütüphane bağımlılığından kaynaklanan geliştirme
ortamı farklılıklarını önlemek için kök dizindeki docker-compose.yml dosyası kullanılmalıdır.
Her ekip üyesi kodunu bu konteyner içinde çalıştırmalıdır.

**Büyük dosyalar:** .raw, .cfile ve diğer büyük I/Q veri dosyaları depoya eklenirken Git LFS
(Large File Storage) kullanılmalıdır. Bu dosyalar Git LFS dışında commitlenirse depo boyutu
hızla büyür ve kullanılamaz hale gelir.

**Otomatik testler:** Her modülün kendi testleri /tests alt dizininde bulunmalıdır. Testler sabit
I/Q dosyaları (test vektörleri) kullanılarak yazılmalı ve GitHub Actions üzerinde her commit
sonrası otomatik olarak çalıştırılmalıdır.

**Commit mesajları:** Kısa ve tanımlayıcı olmalıdır. Hangi modülü etkilediği belirtilmelidir.
Örnek: `ed_system: TDOA hesaplamasında faz belirsizliği düzeltildi`

---

## Simülasyondan Donanıma Geçiş

Donanım temin edildiğinde yapılması gereken tek işlem shared/config.json dosyasındaki
veri kaynağı adreslerini güncellemektir:

```json
// Simülasyon
"ed_source": "zmq://localhost:5555"

// Donanım (Örnek: ADALM-Pluto SDR)
"ed_source": "ip:192.168.2.1"
```

Algoritmaların, arayüzün ve taarruz modüllerinin hiçbir satırı değiştirilmez.

---

### 📡 Jeneratörlerin Kullanımı ve Test Senaryoları

Projemizde, `sim_engine` motorunu ve tespit algoritmalarımızı izole test edebilmek için iki farklı sentetik sinyal jeneratörü bulunmaktadır:

* **`fm_generator.py`:** Sabit frekanslı standart bir FM telsiz sinyali (NBFM) üretir.
* **`fm_drone_generator.py`:** Sürekli frekans atlaması yapan (sweep) hareketli bir drone sinyali üretir.

> **⚠️ Önemli Not (Port Çakışması):** > Mevcut mimaride (PR #13) her iki jeneratör de `config.json` üzerinden aynı adresi (`tcp://*:5555`) kullanmaktadır. Bu modüller, farklı hedefleri test etmek için tasarlanmış bağımsız senaryolardır. Port çakışması (ZMQ Address in use) hatası almamak adına, lokal testler sırasında **bu iki jeneratör aynı anda çalıştırılmamalıdır**. Çoklu hedeflerin aynı anda simüle edileceği mimari güncellemesi ilerleyen fazlarda `sim_engine` üzerine eklenecektir.

## Iletişim ve Sorular

Mimariyle ilgili sorular için önce bu dosyayı ve shared/config.json yorumlarını okuyun.
Yanıt bulamazsanız takım kaptanıyla iletişime geçin.