<div align="center">

# KYROS

### macOS İçin Yapay Zeka Destekli Masaüstü Sesli Asistan

*Doğal konuş. Kyros dinler, anlar ve harekete geçer.*

[![macOS](https://img.shields.io/badge/macOS-13+-000000?style=for-the-badge&logo=apple&logoColor=white)](https://www.apple.com/macos/)
[![Python](https://img.shields.io/badge/Python-3.10--3.14-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Gemini](https://img.shields.io/badge/Gemini-Live-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=for-the-badge)](https://github.com/rhymezip/kyros-onlin-desktop-assistant/pulls)
[![Issues](https://img.shields.io/github/issues/rhymezip/kyros-onlin-desktop-assistant?style=for-the-badge)](https://github.com/rhymezip/kyros-onlin-desktop-assistant/issues)
[![Stars](https://img.shields.io/github/stars/rhymezip/kyros-onlin-desktop-assistant?style=for-the-badge)](https://github.com/rhymezip/kyros-onlin-desktop-assistant/stargazers)
[![Forks](https://img.shields.io/github/forks/rhymezip/kyros-onlin-desktop-assistant?style=for-the-badge)](https://github.com/rhymezip/kyros-onlin-desktop-assistant/network/members)

<br>

**Kyros**, Mac'inizde çalışan ve Google'ın Gemini Live API'sine bağlanan gerçek zamanlı bir sesli asistandır.
Swift ile yazılmış tam çift yönlü ses motoru, Dynamic Island tarzı yüzen panel ve tüm Mac'inizi sesle kontrol etmenizi sağlayan güçlü bir araç sistemine sahiptir.

Kodlanmış komutlar yok. Ayrı STT/TTS hattı yok. Regex eşleme yok.
**Tek model. Tek ses yolu. Saf sohbet.**

<br>

![Ekran Görüntüleri](assets/1.png)

</div>

---

## İçindekiler

- [Özellikler](#-özellikler)
- [Demo](#demo)
- [Mimari](#mimari)
- [Hızlı Başlangıç](#hızlı-başlangıç)
- [Gereksinimler](#gereksinimler)
- [Kurulum](#kurulum)
- [Kullanım](#kullanım)
- [Ses Komutları](#ses-komutları)
- [Oturum Durumları](#oturum-durumları)
- [Panel ve Ayarlar](#panel-ve-ayarlar)
- [Araçlar ve Yetenekler](#araçlar-ve-yetenekler)
- [Canlı Ses Motoru](#canlı-ses-motoru)
- [Yapılandırma](#yapılandırma)
- [Testler](#testler)
- [Sorun Giderme](#sorun-giderme)
- [Güvenlik ve Gizlilik](#güvenlik-ve-gizlilik)
- [Proje Yapısı](#proje-yapısı)
- [SSS](#sss)
- [Katkı Sağlama](#katkı-sağlama)
- [Lisans](#lisans)
- [English](README.md)

---

## Özellikler

<table>
<tr>
<td width="50%">

**🎤 Canlı Ses**
Yankı iptali ile tam çift yönlü ses. 16 kHz mikrofon, 24 kHz TTS, 20 ms parçacıklar, 350 ms VAD.

**🧠 Gemini Native Audio**
`gemini-2.5-flash-native-audio` — tek model sohbet, araç çağrısı ve ses sentezini doğal olarak çalıştırır.

**🖥️ Tam Mac Kontrolü**
Shell komutları, AppleScript/JXA, Erişilebilirlik API'si (tıklama, sürükleme, kaydırma, yazma, ekran görüntüsü), uygulama otomasyonu.

**🔍 Google Arama**
Canlı oturuma doğrudan bağlı yerleşik web arama aracı — tarayıcı gerekmez.

</td>
<td width="50%">

**🎙️ Akıllı Oturum Yönetimi**
*Hey Kyros* ile uyan, *bekleyebilirsin* ile beklemede kal, *dur* ile durdur. Model karar verir.

**🛡️ Dayanıklı Bağlantı**
Oturum yenileme, arabellek kurtarma, otomatik yeniden bağlanma. Ağ sorunlarından etkilenmez.

**🌊 Dynamic Island UI**
Transkript, mikrofon seviyesi, ayarlar ve sağ tık menüsüne sahip yüzen 300×100 panel.

**🔐 Tasarımda Güvenli**
API anahtarları `0600` izinleriyle saklanır, asla kaydedilmez. Yetkili komutlar yerel macOS kimlik doğrulama pencerelerini kullanır.

</td>
</tr>
</table>

> **Tasarım Prensibi:** Kyros, çalışma zamanında bir araya getirilen genel amaçlı araçlar kullanır. *"Notları aç"* veya *"Fenerbahçe'yi ara"* gibi örnek komutlar için kodlanmış dal yok — model her şeyi yönetir.

---

## Demo

<p align="center">
  <img src="assets/2.png" alt="Kyros kullanımda" width="800">
</p>
<p align="center">
  <img src="assets/3.png" alt="Kyros ayarları" width="600">
</p>

---

## Mimari

```
                    ┌─────────────────────────────────────────────┐
                    │              Gemini Live (WSS)               │
                    │     gemini-2.5-flash-native-audio            │
                    └──────────┬──────────────────┬───────────────┘
                               │  PCM 24k (TTS)   │  Araç Çağrıları
                               ▼                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                         macOS Masaüstü                           │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────────────┐  │
│  │  AVAudioEngine│    │  PyQt6 Panel │    │  Araç Yöneticisi  │  │
│  │  (Swift)      │    │  (Dynamic    │    │  ┌─────────────┐ │  │
│  │  • Mikrofon   │    │   Island)    │    │  │ run_shell    │ │  │
│  │  • Hoparlör   │    │  • Transkript│    │  │ run_apple-   │ │  │
│  │  • Yankı İpt. │    │  • Mikro Düz.│    │  │   script     │ │  │
│  │  • VAD        │    │  • Ayarlar   │    │  │ computer     │ │  │
│  └──────┬───────┘    │  • Kontroller│    │  │  (AX/API/    │ │  │
│         │ PCM 16k     └──────────────┘    │  │   ekran grsy)│ │  │
│         └────────────────────────────────▶│  │ read_web     │ │  │
│                                           │  │ google_search│ │  │
│                                           │  └─────────────┘ │  │
│                                           └───────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

**Temel tasarım kararları:**
- **Tek model mimarisi** — Ayrı STT/TTS yok. Gemini sesi doğal olarak işler.
- **Tam çift yönlü** — Mikrofon ve hoparlör Apple'ın ses işleme özelliğiyle aynı `AVAudioEngine`'i paylaşır.
- **İptal edilebilir araçlar** — Her araç bir `asyncio` görevi olarak çalışır. Kesinti anında kuyruğu temizler.
- **Birleştirilebilir araçlar** — Niyet eşleme veya regex yok. Model hangi araçları çağıracağına karar verir.

---

## Hızlı Başlangıç

```bash
# 1. Klonla
git clone https://github.com/rhymezip/kyros-onlin-desktop-assistant.git
cd kyros-onlin-desktop-assistant

# 2. Kur (venv oluştur, bağımlılıkları kur, ses motorunu derle)
bash install.sh

# 3. Çalıştır
venv/bin/python main.py
```

Hepsi bu kadar. Panel açılır, Ayarlar'dan Gemini API anahtarınızı yapıştırırsınız ve hazırsınız.

---

## Gereksinimler

| Bileşen | Sürüm | Notlar |
|---------|-------|--------|
| **macOS** | 13+ | Önerilen: 15.x (Sequoia) |
| **Python** | 3.10 – 3.14 | Önerilen: **3.12** |
| **Apple CLI Araçları** | En son | `xcode-select --install` |
| **Gemini API Anahtarı** | — | [aistudio.google.com](https://aistudio.google.com) adresinden alın |

> Python kodu çapraz platformda test edilebilir; Swift ses motoru ve Live API macOS gerektirir.

---

## Kurulum

### Seçenek A: Otomatik (önerilen)

```bash
git clone https://github.com/rhymezip/kyros-onlin-desktop-assistant.git
cd kyros-onlin-desktop-assistant
bash install.sh
```

**`install.sh` ne yapar:**
1. Uyumlu bir Python bulur (3.10–3.14), `venv/` oluşturur
2. `requirements.txt` dosyasındaki tüm bağımlılıkları kurar
3. Gemini API anahtarı ister (ayarlanmamışsa) → `config/local.json` `0600` izinleriyle yazar
4. Swift ses motorunu derler (`native/kyros-audio`)
5. Test paketini otomatik çalıştırır

### Seçenek B: Manuel

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
bash build_audio.sh
```

Sonra API anahtarınızı ayarlayın:

```bash
export GEMINI_API_KEY="anahtarınız-burada"
```

Veya örneği kopyalayın:

```bash
cp config/local.json.example config/local.json
# config/local.json dosyasını düzenleyin ve anahtarınızı ekleyin
```

### API Anahtarı Olmadan İlk Çalıştırma

API anahtarı olmadan ilk açılışta Kyros, 900ms sonra **Ayarlar** panelini otomatik açar. Anahtarınızı yapıştırın, **Test**'e, sonra **Kaydet ve Uygula'**ya tıklayın — bağlantı ~0.6s içinde başlar.

---

## Kullanım

### Çalıştırma Komutları

```bash
venv/bin/python main.py                  # Panel + Canlı (önerilen)
venv/bin/python main.py --text           # Metin modu, mikrofon yok
venv/bin/python main.py --no-panel       # Arayüzsüz, başsız mod
venv/bin/python main.py --audio-check    # Sadece ses motorunu test et
venv/bin/python main.py --doctor         # Tanılama kontrolleri
venv/bin/python main.py --debug          # Ayrıntılı kayıt
```

### Ses Komutları

Doğal konuşun. Kyros bağlamı anlar ve araçları anında bir araya getirir:

```text
Hey Kyros, Notları aç ve "Toplantı Notları" başlıklı yeni bir not oluştur

Hey Kyros, Fenerbahçe'nin son haberlerini araştır ve özetle

Hey Kyros, Telegram'da Ali'yi bul ve "Yarın görüşürüz" gönder

Hey Kyros, Masaüstüme bak ve bu dosyaları türe göre düzenle

Hey Kyros, İstanbul'da hava şu an nasıl?
```

### Oturum Kontrolü

| Ne Derseniz | Ne Olur |
|-------------|---------|
| **Hey Kyros** | Beklemeden uyanır, dinlemeye başlar |
| **bekleyebilirsin** | Beklemeye geçer, bir sonraki uyanışı bekler |
| **dur / iptal** | Mevcut görevleri iptal eder, aktif kalır |
| **Mikrofon kapat** | Sağ tık menüsünden mikrofonu kapatır |

> **Not:** Sadece *"Hey Kyros"* uyanır — beklemedeyken *"Kyros"* demek işe yaramaz. Model `session_control` aracılığıyla uyanma/bekleme/durma kararlarını verir.

---

## Oturum Durumları

| Panel Durumu | Anlamı |
|-------------|--------|
| `BEKLİYOR` | Beklemede — mikrofon aktif ama araçlar/TTS kapalı. *Hey Kyros* bekliyor. |
| `DİNLİYOR` | Aktif — mikrofon açık, VAD dinliyor, komutlara hazır. |
| `KONUŞUYOR` | TTS çalıyor — *dur/sessizlik/bir dakika* ile kesilebilir. |
| `UYGULUYOR · DİNLİYOR` | Araç çalışıyor ama mikrofon ve bağlantı canlı. |
| `SES AYGITI DEĞİŞİYOR` | Varsayılan giriş/çıkış değişti, otomatik yeniden bağlanıyor. |

---

## Panel ve Ayarlar

### Panel

- **Sol tık** — Sohbet görünümünü açar (transkript, kaynak bağlantıları, metin girişi, kontroller)
- **Sağ tık** — Bağlam menüsü (Uyan / Dur / Bekle / Mikrofon aç-kapat / Ayarlar / Çıkış)
- **Ayarlar (⚙)** — API anahtarı, ses modeli seçimi, bağlantı testi

### Ayarlar Paneli

| Ayar | Açıklama |
|------|----------|
| **API Anahtarı** | Gemini API anahtarınız (`AIza...` veya `AQ...`). Göster/gizle geçişi. |
| **Ses Modeli** | Mevcut native audio modelleri açılır listesi (API'den canlı olarak getirilir). |
| **Test** | API anahtarını ve model uygunluğunu doğrular. Yeşil = hazır. |
| **Kaydet ve Uygula** | `config/local.json`'a kaydeder, bağlantıyı ~0.6s içinde yeniden başlatır. |

> **Önemli:** Kyros sadece doğrudan Google Gemini API anahtarlarıyla çalışır. Uyumlu OpenAI proxyleri (`sk-...`) Live protokolünü desteklemez.

---

## Araçlar ve Yetenekler

Kyros, modelin çalışma zamanında bir araya getirdiği genel amaçlı araçlar sağlar:

| Araç | Açıklama |
|------|----------|
| `run_shell` | Herhangi bir `zsh` komutu çalıştırır. `elevated=true` ile yönetici desteği (macOS parola penceresi gösterir). |
| `run_applescript` | Uygulama otomasyonu için AppleScript veya JXA kodu çalıştırır. |
| `computer` | Tam GUI etkileşimi: `inspect` (AX ağacı), `screenshot`, `click`, `drag`, `scroll`, `key`, `type_text`. |
| `read_web` | Web sayfası içeriğini alır ve okur. |
| `google_search` | Canlı oturumdan doğrudan web'de arama yapar. |
| `session_control` | Uyanma, bekleme ve durdurma eylemleri. |

### Neler Yapabilirsiniz

- **Uygulama Kontrolü:** Herhangi bir uygulamayı açın, menülerde gezin, formları doldurun
- **Dosya Yönetimi:** Dosya ve klasörleri oluşturun, düzenleyin, organize edin
- **Araştırma:** Arayın, makaleleri okuyun, içeriği özetleyin
- **Mesajlaşma:** Telegram, Notes veya herhangi bir otomasyon destekli uygulama aracılığıyla mesaj gönderin
- **Sistem Yönetimi:** Seçenekli yetkili ayrıcalıklarla shell komutları çalıştırın
- **Ekran Farkındalığı:** Ekran görüntüleri alın, UI elemanlarını okuyun, herhangi bir görünür içerikle etkileşime geçin

---

## Canlı Ses Motoru

Kyros, `AVAudioEngine` üzerine kurulu özel bir Swift ses motoruyla (`native/AudioBridge.swift`) birlikte gelir:

| Özellik | Detay |
|---------|-------|
| **Mikrofon Girişi** | 16 kHz PCM, 20 ms parçacıklar |
| **TTS Çıkışı** | 24 kHz PCM via `AVAudioSourceNode` |
| **Yankı İptali** | Apple Voice Processing (`setVoiceProcessingEnabled`) |
| **VAD** | 350 ms sessizlik algılama, 40 ms ön ek dolgusu |
| **Söz Kesme** | Kesinti için art arda 2 RMS > 1150 |
| **Aygıt Tak-Çıkar** | Varsayılan giriş/çıkış değişimlerini otomatik algılar, ~75ms içinde yeniden bağlanır |
| **Yedek** | Kulaklık modu için PortAudio (`--audio-backend portaudio`) |

### Değişikliklerden Sonra Yeniden Derleyin

```bash
bash build_audio.sh
venv/bin/python main.py --audio-check   # Doğrula: "Standard started" + kare istatistikleri
```

---

## Yapılandırma

### Öncelik Sırası

| Kaynak | Öncelik | Açıklama |
|--------|---------|----------|
| `GEMINI_API_KEY` env | 1 | `export GEMINI_API_KEY=...` |
| `GEMINI_MODEL` env | 1 | Model seçimini geçersiz kıl |
| `config/local.json` | 2 | `{"GEMINI_API_KEY":"...","GEMINI_MODEL":"..."}` |

### `config/settings.py` Ayarları

| Ayar | Varsayılan | Açıklama |
|------|-----------|----------|
| `AUDIO_BACKEND` | `native` | `native` (Swift) veya `portaudio` |
| `SILENCE_DURATION_MS` | `350` | VAD sessizlik eşiği |
| `TOOL_TIMEOUT` | `60` | Araç çalışma zaman aşımı (saniye) |
| `MAX_TOOL_OUTPUT` | `24000` | Maksimum araç çıktı baytı |
| `MIC_GATE_RMS` | `1100` | TTS sırasında mikrofon kapısı RMS eşiği |
| `MIC_GATE_HANGOVER_MS` | `400` | TTS sonrası mikrofon kapısı tutma |
| `MIC_GATE_BLOCK_MS` | `600` | TTS sonrası mikrofon engelleme süresi |

### Desteklenen Modeller

| Model | Durum |
|-------|-------|
| `gemini-2.5-flash-native-audio-latest` | Kararlı, önerilen |
| `gemini-2.5-flash-native-audio-preview-09-2025` | Önizleme |

---

## Testler

```bash
# Tüm birim testlerini çalıştır (38 test, API gerekmez)
venv/bin/python -m unittest discover -s tests -v

# Tanılama (izinler, ses, API anahtarı)
venv/bin/python main.py --doctor

# Metin modu (gerçek API, mikrofon yok)
venv/bin/python main.py --text

# Ses motoru kontrolü (API yok)
venv/bin/python main.py --audio-check
```

### Kabul Testi

Kurulum, uyanma/bekleme, söz kesme, sistem yetenekleri, iptal/bağlantı ve yönetici ayrıcalıklarını kapsayan tam manuel kabul testi kontrol listesi için [`MAC_TEST.md`](MAC_TEST.md) dosyasına bakın.

---

## Sorun Giderme

| Belirti | Çözüm |
|---------|-------|
| `Microphone failed to start` | Sistem Ayarları → Gizlilik → Mikrofon → Kyros/Terminal/Python'a erişim verin |
| `Connecting`'de takıldı | API anahtarını kontrol edin (Ayarlar ⚙ → Test), ağı doğrulayın, `logs/kyros.log` dosyasına bakın |
| `Received 1008 policy violation` | Model/API uyumsuzluğu — Ayarlar'dan doğru modeli seçin |
| `User location is not supported` | Google bölgesel kısıtlaması — VPN veya farklı ağ deneyin |
| Ses aygıtı değişiyor döngüsü | Bridge v5 debounce bunu halleder; en son `build_audio.sh`'den emin olun |
| Ctrl+C sonrası `0 bytes read` | Normal WebSocket kapanışı — hata değil |
| Söz kesme çalışmıyor | Açıkça > 1150 RMS darbesi gerektiğinden emin olun; mikrofon kazanç ayarlarını kontrol edin |
| Uyanma kelimesi algılanmıyor | Sadece *"Hey Kyros"* çalışır — beklemedeyken *"Kyros"* tek başına uyanmaz |

### Kayıtlar

```bash
tail -f logs/kyros.log    # Dönen: 1MB × 3 dosya
```

---

## Güvenlik ve Gizlilik

- **API anahtarları** `config/local.json` dosyasında `0600` izinleriyle veya ortam değişkenleriyle saklanır — asla kaydedilmez veya commit edilmez.
- **Araçlar giriş yapmış kullanıcı olarak çalışır** — sandbox yok, izin listesi yok. Terminal ile aynı dikkatle kullanın.
- **Yetkili komutlar** (`elevated=true`) yerel macOS parola pencerelerini tetikler. Parolalar asla sesle istenmez veya saklanmaz.
- **Ekran görüntüleri** `computer` aracı bağlamı için JPEG olarak Gemini'ye gönderilir. Yerel olarak saklanmaz.
- **Bekleme modu** sesi Gemini'ye aktarmaya devam eder (çevrimdışı uyanma kelimesi yok). Akışı kesmek için *Mikrofon kapat* seçeneğini kullanın.
- **Root çalıştırmaz** — Kyros asla root olarak çalışmaz.

---

## Proje Yapısı

```
kyros/
├── main.py                    # Giriş noktası, CLI argümanları, kayıt
├── config/
│   ├── settings.py            # Gemini yapılandırması, model listesi, API doğrulama
│   ├── local.json             # (gitignore) API anahtarınız ve model
│   └── local.json.example     # Şablon
├── core/
│   ├── gemini_live.py         # Gemini Live oturumu, mikrofon kapısı, söz kesme
│   ├── audio_io.py            # Ses motoru köprüsü (Swift / PortAudio)
│   ├── protocol.py            # Sistem mesajı, araç tanımları
│   ├── executor.py            # Araç çalıştırma (shell, AS, AX, web)
│   ├── doctor.py              # Tanılama (--doctor, --audio-check)
│   ├── bootstrap.py           # Otomatik venv etkinleştirme
│   ├── macos_ui.py            # macOS UI yardımcıları
│   └── web_page.py            # Web içerik alma
├── gui/
│   └── panel.py               # Dynamic Island panel + Ayarlar диалогы
├── native/
│   ├── AudioBridge.swift      # Swift ses motoru (AVAudioEngine)
│   ├── Launcher.c             # Kyros.app başlatıcı
│   └── AudioInfo.plist        # Mikrofon kullanımı açıklaması
├── assets/
│   ├── 1.png                  # Ekran görüntüsü
│   ├── 2.png                  # Ekran görüntüsü
│   └── 3.png                  # Ekran görüntüsü
├── tests/                     # 38 birim testi
├── logs/                      # (gitignore) Dönen kayıtlar
├── install.sh                 # Tek komutluk kurulum
├── build_audio.sh             # Swift ses motoru derleyicisi
├── requirements.txt           # Python bağımlılıkları
├── LICENSE                    # MIT Lisansı
└── README.tr.md               # Türkçe dokümantasyon
```

---

## SSS

<details>
<summary><strong>Kyros OpenAI API anahtarlarıyla çalışır mı?</strong></summary>
Hayır. Kyros, Live (BidiGenerateContent) protokolü için doğrudan Google Gemini API anahtarı gerektirir (`AIza...` veya `AQ...`). Uyumlu OpenAI proxyleri gerçek zamanlı sesi desteklemez.
</details>

<details>
<summary><strong>Kyros'u kulaklıkla kullanabilir miyim?</strong></summary>
Evet. Kulaklık modu için `--audio-backend portaudio` seçeneğini kullanın. Native Swift motoru, yankı iptaliyle hoparlör için optimize edilmiştir.
</details>

<details>
<summary><strong>Intel Mac'lerde çalışır mı?</strong></summary>
Evet, yedek modla. 3 kanallı ses işleme Intel'de kare üretmez, bu yüzden Kyros otomatik olarak Standart 1 kanallı moda geçer.
</details>

<details>
<summary><strong>Verilerim Google'a gönderiliyor mu?</strong></summary>
Ses ve araç sonuçları işleme için Gemini Live'a gönderilir. Ekran görüntüleri `computer` aracı kullanıldığında JPEG olarak gönderilir. Kyros tarafından oturum transkriptleri dışında yerel olarak veri saklanmaz.
</details>

<details>
<summary><strong>Kyros'u Linux veya Windows'ta kullanabilir miyim?</strong></summary>
Python mantığı çapraz platformda test edilebilir, ancak Swift ses motoru ve macOS'e özgü araçlar (Erişilebilirlik, AppleScript) macOS 13+ gerektirir.
</details>

<details>
<summary><strong>Maliyeti ne kadar?</strong></summary>
Kyros ücretsiz ve açık kaynaklıdır (MIT). Yalnızca Google'ın [fiyatlandırmasına](https://ai.google.dev/pricing) göre Gemini API kullanımını ödersiniz.
</details>

---

## Katkı Sağlama

Katkılarınız hoşa geldi! Nasıl:

1. Depoyu **fork** edin
2. **Özellik dalı** oluşturun (`git checkout -b feature/olaganusti-ozellik`)
3. Değişikliklerinizi **commit** edin (`git commit -m 'Olağanüstü özellik ekle'`)
4. Dalı **push** edin (`git push origin feature/olaganusti-ozellik`)
5. **Pull Request** açın

### Geliştirme Ortamı

```bash
git clone https://github.com/rhymezip/kyros-onlin-desktop-assistant.git
cd kyros-onlin-desktop-assistant
bash install.sh
venv/bin/python -m unittest discover -s tests -v
```

### Kod Stili

- Python: Mevcut kurallara uyun, harici linter gerekmez
- Swift: `native/AudioBridge.swift` dosyasındaki mevcut kalıpları takip edin
- Testler: Yeni araçlar veya önemli değişiklikler için test ekleyin

---

## Lisans

Bu proje **MIT Lisansı** altında lisanslanmıştır — ayrıntılar için [LICENSE](LICENSE) dosyasına bakın.

---

<div align="center">

**macOS için özenle yapıldı**

*Kyros — çünkü masaüstünüz dinlemeli.*

<br>

[![GitHub](https://img.shields.io/badge/GitHub-rhymezip-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/rhymezip)

</div>
