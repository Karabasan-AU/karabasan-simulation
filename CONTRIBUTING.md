# Katkı Kılavuzu

Bu belge, karabasan-simulation reposunda çalışırken uyulması gereken branch, commit ve PR kurallarını tanımlar. Yarışma sürecinde hızlı ve çakışmasız çalışabilmek için bu kurallara uymak zorunludur.

---

## 1. Başlamadan Önce

Her yeni iş bir GitHub issue'ya dayanmalıdır. Kod yazmadan önce üzerinde çalışacağın issue'nun sana atanmış olduğundan emin ol. Issue yoksa önce issue aç, sonra koda geç.

---

## 2. Branch Kuralı

Her issue için `main`'den ayrı bir branch aç. Branch adı şu formatı takip eder:

```
<kişi>/<konu>
```

**Örnekler:**
```
enise/fm-generator
murat/channel-model
serhat/analog-demod
meryem/geometry-manager
sila/logging-altyapisi
```

- Branch adında Türkçe karakter kullanma.
- Tek bir branch'te birden fazla issue'nun işini yapma.
- `main` branch'ine doğrudan push yapma.

---

## 3. Commit Mesajı Formatı

```
<modül>: <ne yapıldı>
```

**Örnekler:**
```
ed_system: FM demodülatör eklendi
sim_engine: FSPL hesabında mesafe sıfır kontrolü eklendi
shared: logger modülü oluşturuldu
generators: FM generator ZMQ soketi üzerinden yayın yapıyor
```

- Türkçe yazılabilir.
- Tek bir commit'e birden fazla modülün değişikliğini sıkıştırma.
- "düzeltme", "güncelleme", "değişiklik" gibi belirsiz mesajlar yazma — ne yaptığını yaz.

---

## 4. Pull Request Açma

Branch'inde iş bittiğinde bir PR aç. PR açmadan önce:

```bash
git fetch origin
git rebase origin/main
```

PR başlığı commit formatıyla aynı olmalıdır:

```
ed_system: FM demodülatör eklendi
```

PR açıklamasına mutlaka şu satırı ekle:

```
Closes #<issue_no>
```

Bu satır PR merge edildiğinde issue'yu otomatik olarak kapatır. Issue numarasını yazmayı unutursan issue açık kalır.

**PR açıklaması örneği:**
```
FM ve NFM demodülasyonu eklendi. Demodülatör seçimi modülasyon tipine göre
otomatik yapılıyor. Her adımda gecikme ölçümü loglanıyor.

Closes #6
```

---

## 5. Review Kuralı

- Kendi yazdığın kodu sen merge edemezsin.
- PR merge edilmeden önce en az 1 kişinin review'u gerekir.
- Sıla, entegrasyon sahibi olarak tüm PR'ları takip eder; modüller arası
  arayüzü etkileyen değişikliklerde mutlaka Sıla'yı reviewer olarak ekle.
- Review yorumları çözülmeden PR merge edilmez.

---

## 6. `shared/config.json` Değişiklikleri

`shared/config.json` veya modüller arası mesaj formatını etkileyen herhangi bir değişiklik yapmadan önce:

1. İlgili modülün sahibine haber ver.
2. Değişikliği `shared/README.md`'de belgele.
3. PR açıklamasında hangi modüllerin etkilendiğini yaz.

Format değişikliği yapan kişi, bağlı modülün sahibini bilgilendirmeden commit atamaz.

---

## 7. Büyük Dosyalar

`.raw`, `.cfile`, `.npy` ve diğer büyük I/Q veri dosyaları Git LFS olmadan repoya eklenmez.

```bash
git lfs track "*.raw"
git lfs track "*.cfile"
git lfs track "*.npy"
```

LFS dışında commit edilmiş büyük dosyalar repoyu kullanılamaz hale getirir.

---

## 8. Özet — Standart İş Akışı

```
1. Issue'yu al, sana atandığından emin ol
2. main'den yeni branch aç  →  git checkout -b enise/fm-generator
3. Kodunu yaz, commit'le     →  git commit -m "generators: FM generator eklendi"
4. main'i rebase et          →  git rebase origin/main
5. Push et                   →  git push origin enise/fm-generator
6. PR aç, açıklamaya         →  Closes #<issue_no>  yaz
7. Review bekle, merge et
```