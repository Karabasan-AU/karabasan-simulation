# TEKNOFEST 2026 Elektronik Harp Projesi - Görev Dağılımı

Bu belge, projenin üç ana geliştirme aşamasında her ekip üyesinin birincil sorumluluklarını
ve dikkat etmesi gereken kritik noktaları tanımlamaktadır.

---

## Genel Sorumluluk Tablosu

| Üye    | Birincil Alan              | Erken Aşama                             | Orta Aşama                              | Final Aşaması                           |
|--------|----------------------------|-----------------------------------------|-----------------------------------------|-----------------------------------------|
| Murat  | Elektronik Taarruz (ET)    | JSR analizi ve karıştırma modeli        | Sürekli ve arabakışlı karıştırma        | Sahada iletişim engelleme               |
| Meryem | Konum Belirleme            | LOB/TDOA geometri hesapları             | Harita algoritmaları ve GPS entegrasyonu | Hedef koordinatlarının kesin tespiti   |
| Enise  | Sinyal Tespiti             | FFT ve filtre tasarımı                  | Sinyal tespiti ve parametre çıkarımı    | Gerçek zamanlı sinyal tanımlama         |
| Serhat | Demodülasyon               | Protokol ve paket analizi               | Analog/sayısal telsiz deşifre           | Canlı ses ve veri çözümleme             |
| Sıla   | Yapay Zeka ve Entegrasyon  | RF veri seti hazırlama ve model eğitimi | Sınıflandırma modeli ve UI bağlantısı   | Otomatik tehdit değerlendirmesi         |

---

## Üye Bazlı Görev Detayları

---

### Murat — Elektronik Taarruz (ET)

Murat, projenin taarruz biriminden sorumludur. ET sisteminin tüm karıştırma ve aldatma
modüllerini geliştirir, test eder ve saha aşamasında yönetir.

**Erken Aşama (Araştırma ve Tasarım)**
- JSR (Jammer-to-Signal Ratio) hesaplama modelini kurmak. Hangi güç seviyesinde, hangi
  mesafede karıştırmanın etkili olduğunu matematiksel olarak göstermek.
- Sürekli, çoklu ve baraj karıştırma tiplerinin farkını analiz etmek ve hangisinin hangi senaryoda
  kullanılacağını belgelemek.
- Analog telsiz aldatma ve GNSS spoofing için gereken sinyal formatlarını araştırmak.

**Orta Aşama (Geliştirme)**
- `et_system/` dizini altında karıştırma modüllerini yazmak.
- Arabakışlı (look-through) karıştırma için tespit ve karıştırma fazları arasındaki zamanlama
  mantığını kodlamak. Bu modülün Enise'nin sinyal tespiti çıktısıyla koordineli çalışması gerekir.
- GNSS aldatma için en az GPS L1 sinyali üretmek. Ek servisler (GLONASS, Galileo) ilave puan
  kazandırır.
- `sim_engine/` üzerinden Enise ve Serhat'ın modüllerine karıştırma sinyalinin nasıl etki
  ettiğini test etmek.

**Final Aşaması (Saha)**
- ET sistemini saha koşullarında çalıştırmak ve hedef telsiz iletişimini kesmek.
- Arabakışlı karıştırmada dinleme pencerelerini gerçek zamanlı yönetmek.

**Kritik Nokta — Duty Cycle Yönetimi:**
Karıştırma sinyali SDR donanımını ısıtır. Sürekli TX (gönderme) modunda uzun süre kalmak
donanımı bozabilir. Murat, yazılımsal olarak bir aç-kapat döngüsü (duty cycle) mekanizması
kurmalıdır. Bu mekanizma, sahada herhangi bir donanım arızasının önünde duran en önemli
güvencedir.

---

### Meryem — Konum Belirleme

Meryem, tespit edilen sinyallerin haritada nerede olduğunu hesaplayan algoritmalardan sorumludur.

**Erken Aşama (Araştırma ve Tasarım)**
- LOB (Line of Bearing) ve TDOA (Time Difference of Arrival) yöntemlerinin geometrik temellerini
  modellemek.
- Farklı anten yerleşim senaryolarında konum tahmin hatasının (RMS) nasıl değiştiğini simüle etmek
  ve en iyi yerleşimi önermek.
- `sim_engine/` içindeki koordinat sistemiyle uyumlu bir veri yapısı tanımlamak.

**Orta Aşama (Geliştirme)**
- `ed_system/` içindeki konum belirleme modülünü yazmak.
- Enise'nin yön bulma çıktısından gelen LOB verilerini alarak kesişim noktası hesabı yapmak.
- Birden fazla alıcı kullanılan TDOA senaryosu için zaman damgalarını işleyen algoritmayı geliştirmek.
- Sıla'nın arayüzüne konum verisini göndermek için JSON formatını Sıla ile birlikte tanımlamak.

**Final Aşaması (Saha)**
- Antenler fiziksel olarak yerleştirildikten sonra koordinat kalibrasyonunu yapmak.
- Gerçek zamanlı olarak hedef koordinatlarını hesaplamak ve arayüze aktarmak.

**Kritik Nokta — RMS ve Kalibrasyon:**
Şartname, yön bulma doğruluğunu Derece RMS üzerinden puanlar. Antenlerin fiziksel
yerleşimi ile kod içindeki geometri modeli arasında en küçük bir tutarsızlık bile konum
hatasını büyütür. Meryem, saha öncesinde bilinen bir noktadan kalibrasyon testi yapmalı
ve algoritmadaki sapmayı ölçerek düzeltmelidir.

---

### Enise — Sinyal Tespiti

Enise, sistemin ilk gözlem noktasıdır. Ham I/Q verisinden anlamlı sinyal bilgisi çıkaran
algoritmalar bu üyenin sorumluluğundadır.

**Erken Aşama (Araştırma ve Tasarım)**
- FFT tabanlı güç spektrum yoğunluğu hesabının matematiksel temellerini kurmak.
- Gürültü tabanı (noise floor) tespiti ve dinamik eşikleme (thresholding) yöntemlerini araştırmak.
- `generators/` modülünden üretilen test sinyalleri üzerinde temel tespit denemeleri yapmak.

**Orta Aşama (Geliştirme)**
- `ed_system/` içinde sinyal tespiti ve parametre çıkarımı modüllerini yazmak.
- Merkez frekansı, bant genişliği, güç seviyesi ve modülasyon tipini (AM, FM, FSK, PSK vb.)
  otomatik olarak çıkaran algoritmaları geliştirmek.
- FHSS (frekans atlamalı) sinyalleri takip edebilen dinamik tarama mantığını kodlamak.
- Yön bulma hesabı için Meryem'in ihtiyaç duyduğu veriyi doğru formatta ve düşük gecikmeyle
  sağlamak.
- Gelen I/Q akışını Serhat ve Meryem'in modüllerinin işleyebileceği hızda tamponlayan bir kuyruk
  mekanizması kurmak.

**Final Aşaması (Saha)**
- Gerçek zamanlı spektrum taraması yaparak yeni hedefleri tespit etmek.
- Parametreleri hakemlere sunulabilir biçimde arayüze iletmek.

**Kritik Nokta — Veri Akışı Yönetimi:**
Enise'nin modülü sistemin darboğaz noktasıdır. Eğer I/Q tamponu dolup taşarsa, Serhat'ın
demodülasyon modülü ve Meryem'in konum modülü boş kuyruktan okumaya çalışır ve sistem
donar. Enise bu kuyruk mekanizmasını ZMQ veya Python Queue yapısıyla doğru boyutlandırmalı
ve aşırı yük durumunda en eski veriyi düşüren (drop oldest) bir politika uygulamalıdır.

---

### Serhat — Demodülasyon

Serhat, tespit edilen sinyalin içindeki anlamlı veriyi çıkaran rolündedir.

**Erken Aşama (Araştırma ve Tasarım)**
- Analog telsiz demodülasyonu (AM, FM, NFM) ve sayısal telsiz demodülasyonu (FSK, GMSK,
  DMR gibi) arasındaki teknik farkları araştırmak.
- Şartnamenin işaret ettiği amatör telsiz formatlarını (hem analog hem sayısal) incelemek.
- Enise'nin çıkaracağı modülasyon tipi bilgisini alıp doğru demodülatöre yönlendiren bir yönlendirme
  mantığı tasarlamak.

**Orta Aşama (Geliştirme)**
- `ed_system/` içinde demodülasyon modülünü yazmak.
- Enise'nin tespitinden gelen parametreye göre otomatik demodülatör seçimi yapan mantığı kodlamak.
- Analog telsizden çözülen sesi `ui/` üzerinden operatöre iletmek.
- Sayısal telsiz için ham paket verisini çıkarmak ve Sıla'nın yapay zeka modeline beslemek.
- Sesin operatör tarafından gerçek zamanlı duyulabilmesi için işlem süresini kısa tutmak ve
  Sıla'nın arayüzüne veriyi gecikme yaratmadan aktarmak.

**Final Aşaması (Saha)**
- Canlı olarak gelen telsiz sesini çözmek ve arayüzde görünür kılmak.
- Hakemlerin sinyalin içeriğini doğrulayabileceği çıktıları loglamak.

**Kritik Nokta — Gecikme (Latency):**
Demodülasyon çıktısı hem operatör hem de hakem tarafından görülecektir. Ses çok geç gelirse
veya kesilirse, sinyal dinleme görevi başarısız sayılabilir. Serhat, işlem hattının her adımında
gecikme ölçümü yapmalı ve darboğaz yaratan adımı tespit edip optimize etmelidir.

---

### Sıla — Yapay Zeka ve Sistem Entegrasyonu

Sıla, iki ayrı kritik sorumluluğu birlikte taşır: RF sinyallerini otomatik sınıflandıran yapay
zeka modelini geliştirmek ve tüm modüllerin kullanıcı arayüzüyle konuşmasını sağlamak.

**Erken Aşama (Araştırma ve Tasarım)**
- Sinyal sınıflandırması için eğitim veri seti oluşturmak. `generators/` modülünden üretilen farklı
  modülasyon tiplerine ait I/Q verilerini toplayarak etiketlemek.
- CNN veya RNN tabanlı bir model mimarisi seçmek ve `sim_engine/` ortamında üretilen verilerle
  ön eğitimi başlatmak.
- `ui/` için hangi verinin, hangi modülden, hangi protokolle geleceğini diğer tüm üyelerle birlikte
  tanımlamak. Bu adım Sıla'nın görevi olmakla birlikte tüm ekibin onayına tabidir.

**Orta Aşama (Geliştirme)**
- `ed_system/` içinde yapay zeka sınıflandırma modülünü yazmak ve Enise'nin ham tespitlerini
  bu modele besleyen boru hattını kurmak.
- `ui/` dizini altında kullanıcı arayüzünü geliştirmek.
- Arayüzdeki her göstergenin (spektrogram, harita, ses seviyesi, tespit listesi) gerçek veriyle
  beslendiğinden emin olmak. Bunun için her modülden gelen WebSocket veya REST bağlantısını
  kurmak ve test etmek Sıla'nın sorumluluğundadır.
- Tüm modüllerin birbiriyle sorunsuz çalıştığı uçtan uca entegrasyon testini koordine etmek.

**Final Aşaması (Saha)**
- Yapay zeka modelinin gerçek sinyaller üzerindeki sınıflandırma doğruluğunu izlemek.
- Arayüzün saha koşullarında kararlı çalıştığından emin olmak.

**Kritik Nokta — Backend Bağlantısı:**
Arayüzün görsel olarak hazır olması yeterli değildir. Enise'nin frekans tespiti, Meryem'in
koordinatı, Serhat'ın çözülen sesi ve Murat'ın karıştırma durumu — bunların tamamı arayüze
doğru formatta ve doğru zamanda ulaşmalıdır. Sıla, bu bağlantıları kurmadan önce her üyeyle
mesaj formatını (veri tipi, birim, güncelleme sıklığı) yazılı olarak netleştirmelidir.

---

## Ekip Genelinde Dikkat Edilecek Noktalar

**Senkronizasyon:**
TDOA yöntemiyle konum belirleme, farklı alıcılardaki saat farklarına son derece duyarlıdır.
Birden fazla SDR kullanılması durumunda saatlerin senkron olup olmadığı yazılımsal olarak
sürekli kontrol edilmelidir. Bu kontrol Meryem ve Enise'nin ortak sorumluluğundadır.

**Loglama:**
Yarışma sırasında hakemler herhangi bir anda "bu sonuca nasıl ulaştınız?" diye sorabilir.
Her modülün işlem anındaki ham girdi ve çıktısını zaman damgasıyla kaydetmesi gerekir.
Loglama altyapısı `shared/` dizini altında Sıla tarafından kurulur; diğer üyeler kendi
modüllerinde bu altyapıyı kullanır.

**Mesaj Formatı Anlaşması:**
Modüller arası veri formatı (JSON şeması, birimler, örnekleme hızı) her değişiklikte
`shared/config.json` ve `shared/README.md` içinde güncellenmeli ve ilgili üyeye bildirilmelidir.
Format değişikliği yapan kişi, bağlı modülün sahibini bilgilendirmeden commit atmamalıdır.