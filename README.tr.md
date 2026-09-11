<div align="center">

# KYROS

### macOS ve Linux için doğal dilli masaüstü asistanı

Doğal konuş. Kyros, Gemini Live üzerinden dinlesin, doğru genel aracı seçsin,
işi gerçekten yapsın ve gerçek sonucu bildirsin.

**macOS 13+** · **Linux / Wayland** · **Hyprland öncelikli** · **Python 3.10–3.14** · **MIT**

</div>

---

## Kyros nedir?

Kyros, Google Gemini Live API için yerel bir masaüstü istemcisidir. Tam çift
yönlü sesi, hafif PyQt6 panelini, platformun doğal ses altyapısını ve genel
masaüstü araçlarını tek bir konuşmada birleştirir.

macOS yolu kritik noktalarda native kalır: Swift `AVAudioEngine`, Apple voice
processing, Accessibility, Quartz, AppleScript ve `zsh`. Linux ise PipeWire,
Hyprland/Wayland, AT-SPI2, XDG portal ve mevcut en uygun girdi/çıktı
backend'leri üzerine kurulu ayrı bir adaptör kullanır.

Temel tasarım kararı nettir: Kyros'ta cümleye özel intent yönlendiricisi,
uygulama allowlist'i veya regex komut eşleştiricisi yoktur. Model genel
yetenekleri çalışma anında birleştirir. Araç sonuçları okunup doğrulanır;
eksik yetenekler tahmin edilmez, gerçek hata olarak döndürülür.

## İçindekiler

- [Öne çıkanlar](#öne-çıkanlar)
- [Platform desteği](#platform-desteği)
- [Hızlı başlangıç](#hızlı-başlangıç)
- [Kurulum](#kurulum)
- [Kaldırma](#kaldırma)
- [Kyros'u çalıştırma](#kyrosu-çalıştırma)
- [Konuşma ve oturum kontrolü](#konuşma-ve-oturum-kontrolü)
- [Araç yüzeyi](#araç-yüzeyi)
- [Linux ve Hyprland](#linux-ve-hyprland)
- [macOS](#macos)
- [Ses](#ses)
- [Yapılandırma](#yapılandırma)
- [Tanılama ve test](#tanılama-ve-test)
- [Sorun giderme](#sorun-giderme)
- [Güvenlik ve gizlilik](#güvenlik-ve-gizlilik)
- [Depo temizliği](#depo-temizliği)
- [Proje yapısı](#proje-yapısı)
- [Katkı sağlama](#katkı-sağlama)
- [Lisans](#lisans)
- [English](README.md) · [Русский](README.ru.md)

## Öne çıkanlar

- **Canlı ses:** Gemini native audio, mikrofon girdisi, sesli çıktı,
  söz kesme ve oturum devam ettirme.
- **Tek konuşma:** ayrı STT/TTS orkestrasyonu ve uygulamaya özel sabit iş akışı
  yoktur.
- **Genel masaüstü kontrolü:** shell, arayüz inceleme, klavye/fare, uygulama
  başlatma, medya, clipboard, bildirim, web okuma ve arama.
- **Platforma uygun ses:** macOS'ta Swift voice processing; Linux'ta varsayılan
  PipeWire ve açıkça seçilen PortAudio fallback'i.
- **Hyprland farkındalığı:** compositor IPC, pencere/çalışma alanı işlemleri,
  ekran görüntüsü, portal, AT-SPI2 ve yetenek denetimi.
- **İptal edilebilir çalışma:** araçlar zaman sınırlıdır, kesilebilir ve gerçek
  çıkış/UI sonucunu bildirir.
- **Temiz terminal:** canlı akışta kısa durum olayları; ayrıntılı kayıtlar
  dönen log dosyalarında.
- **Sahiplik farkındalığı:** kurulum ne oluşturduğunu kaydeder, kaldırma
  işlemi tahmin ederek paket silmez.

## Platform desteği

| Platform | Ana yol | Not |
| --- | --- | --- |
| macOS 13+ | Swift ses köprüsü + Accessibility/Quartz | Apple Command Line Tools ve istenen gizlilik izinleri gerekir. |
| Linux / Wayland | PipeWire + `linux_desktop` | Birincil hedef Hyprland'dır; portal ve X11/XWayland fallback'leri mevcutsa kullanılır. |
| Linux dağıtımları | `pacman`, `apt`, `dnf`, `zypper` | `install.sh` resmi depoları kullanır; desteklenmeyen yöneticide durur. |
| Windows | Desteklenmiyor | Windows uygulaması bulunmaz. |

## Hızlı başlangıç

~~~bash
git clone https://github.com/rhymezip/kyros-online-desktop-assistant.git
cd kyros-online-desktop-assistant

chmod +x install.sh uninstall.sh
bash install.sh

venv/bin/python main.py
~~~

Kurulum macOS veya Linux'u algılar ve yalnızca o platformun Python
bağımlılıklarını seçer. İlk çalıştırmada Ayarlar panelinden doğrudan Google
Gemini API anahtarını ekleyip test edebilir veya kuruluma başlamadan önce
anahtarı ortam değişkeni olarak verebilirsin.

## Kurulum

### Önerilen kurulum

~~~bash
bash install.sh
~~~

`install.sh` platforma göre şu adımları uygular:

1. `Darwin` veya `Linux` tespit edilir; diğer platformlar reddedilir.
2. `requirements-macos.txt` veya `requirements-linux.txt` seçilir.
3. Linux'ta `pacman`, `apt`, `dnf` ya da `zypper` algılanır ve dağıtıma uygun
   paket adlarıyla masaüstü araç seti hazırlanır.
4. Python 3.10–3.14 ile proje içi `venv/` oluşturulur.
5. Python bağımlılıkları bu ortama kurulur ve `pip check` çalıştırılır.
6. macOS'ta Swift ses binary'si derlenip imzalanır.
7. Linux'ta yeni kurulan paketler kaydedilir; uygunsa dar kapsamlı
   `uinput`/`ydotoold` entegrasyonu hazırlanır.
8. Başarı bildirilmeden önce test paketi çalıştırılır.

Linux paketleri yalnızca tespit edilen dağıtımın resmi depolarından gelir.
Kurulum AUR, dışarıdan installer script'i, `sudo pip`,
`--break-system-packages` veya kısmi yükseltme oluşturabilecek `pacman -Sy`
kullanmaz.

Hiçbir şeyi değiştirmeden kurulum planını görmek için:

~~~bash
bash install.sh --dry-run
~~~

### Linux PortAudio fallback'i

Linux'ta varsayılan PipeWire yolu NumPy veya `sounddevice` gerektirmez.
PortAudio'yu yalnızca fallback'e ihtiyacın varsa kur:

~~~bash
bash install.sh --with-portaudio
venv/bin/python main.py --audio-backend portaudio
~~~

### Linux neden parola sorabilir?

Eksik Linux paketleri veya dar kapsamlı `/dev/uinput` izin kurulumu varsa,
installer önce yapılacak işlemi açıklar ve ardından yönetici yetkisi ister.
Bu parola:

- sistemin yetkilendirme mekanizması tarafından işlenir;
- Gemini'ye gönderilmez ve Kyros dosyasına yazılmaz;
- yalnızca ekranda açıklanan paket/izin işlemi için kullanılır;
- normal Kyros işlerini root olarak çalıştırmaz.

`uinput` kuralı yalnızca sanal girdi aygıtına erişebilen `kyros-input` grubunu
oluşturur; fiziksel klavye ve fare aygıtlarına genel erişim vermez. Grup
değişikliğinin etkili olması için bir kez çıkış/giriş yapmak gerekebilir.

## Kaldırma

Önce kaldırma planını değişiklik yapmadan incele:

~~~bash
bash uninstall.sh --dry-run
~~~

Ardından Kyros'un sahip olduğu kaynakları kaldır:

~~~bash
bash uninstall.sh
~~~

Uninstaller sahiplik kaydına göre çalışır:

- Yalnızca Kyros kurulmadan önce sistemde bulunmayan ve kurulum manifestine
  kaydedilen Linux paketleri aday olur. Önceden var olan paketlere dokunulmaz.
- Geniş kapsamlı `autoremove` çalıştırmaz ve `pacman -Rs` gibi bağımlılık
  zincirini izleyerek silen kipleri kullanmaz.
- `venv` yalnızca Kyros tarafından oluşturulduysa kaldırılır.
- macOS ses binary'si yalnızca Kyros tarafından oluşturulduysa kaldırılır.
- Sadece Kyros'a ait ve değiştirilmemiş `ydotoold` servisi ile izin dosyaları
  kaldırılır.
- API anahtarını içerebileceği için `config/local.json` varsayılan olarak
  korunur.

Onay sorularını atlamak için `--yes` kullanabilirsin. Yerel yapılandırmayı
özellikle kaldırmak için:

~~~bash
bash uninstall.sh --purge-config
~~~

Kurulum manifesti yoksa güvenli davranış mevcut ortam ve sistem paketlerini
tahmin ederek silmemektir.

## Kyros'u çalıştırma

~~~bash
venv/bin/python main.py                  # Panel + canlı ses
venv/bin/python main.py --text           # Metin tabanlı Live oturumu; mikrofon yok
venv/bin/python main.py --no-panel       # Panelsiz Live oturumu
venv/bin/python main.py --doctor         # Salt-okunur yerel tanılama
venv/bin/python main.py --audio-check    # Yerel ses testi; Gemini çağrısı yok
venv/bin/python main.py --debug          # Terminalde daha ayrıntılı kayıt
~~~

macOS ses kaynağında değişiklik yaptıysan native köprüyü yeniden derle:

~~~bash
bash build_audio.sh
venv/bin/python main.py --audio-check
~~~

`build_audio.sh` yalnızca macOS içindir. Linux Swift köprüsünü derlemez ve
kullanmaz.

## Konuşma ve oturum kontrolü

Kyros konuşarak kullanılmak üzere tasarlanmıştır. Model, başarı bildirmeden
önce araç sonucunu okumalı ve bir tur tamamlandıktan sonra kendi kendine yeni
bir cevap başlatmamalıdır.

- **Uyanma:** bekleme modunda `Hey Kyros` de. İki kelimelik ifade bilerek
  zorunludur; yalnızca `Kyros` uyanma isteği değildir.
- **Bekleme:** Kyros'tan açıkça beklemesini veya bekleme moduna geçmesini iste.
- **Durdurma:** mevcut işi durdurmasını/iptal etmesini iste. Açıkça bekleme
  istenmedikçe oturum aktif kalır.
- **Söz kesme:** yeni kullanıcı turu sesli çıktıyı kesebilir ve bekleyen işi
  iptal edebilir. İptal edilen yan etkiler otomatik olarak geri alınmaz.

Araç sonucundan sonra Kyros bir kez başarı veya hata bildirir ve yeni kullanıcı
turunu bekler. Kullanıcı istemeden “bekleyeyim mi?” sorusu ya da nezaket
kapanışı üretmez.

## Araç yüzeyi

Model aşağıdaki genel yeteneklere sahiptir. Örnekler cümleye veya uygulamaya
özel bir dispatch kuralı değildir.

| Araç | macOS | Linux | Görevi |
| --- | :---: | :---: | --- |
| `run_shell` | ✓ | ✓ | Kullanıcı yetkisiyle genel shell çalıştırır (`zsh` / `/bin/sh`). |
| `run_applescript` | ✓ | — | AppleScript veya JXA ile native macOS otomasyonu. |
| `computer` | ✓ | ✓ | Mevcut native backend'lerle arayüzü inceler ve kontrol eder. |
| `linux_desktop` | — | ✓ | Linux/Wayland/Hyprland pencere, workspace, AT-SPI2, girdi, ekran, clipboard, launch, bildirim ve yetenek işlemleri. |
| `launch_app` | ✓ | ✓ | Shell kullanmadan gerçek uygulama, desktop entry, URI, yol veya argv başlatır. |
| `media_control` | ✓ | ✓ | Seçilen medya oynatıcıyı kontrol eder; Linux'ta MPRIS/`playerctl`. |
| `clipboard` | ✓ | ✓ | Native clipboard; Linux'ta desteklendiği yerde primary selection. |
| `read_web` | ✓ | ✓ | Tarayıcı açmadan okunabilir HTTP(S) içeriği getirir. |
| Google Search | ✓ | ✓ | Güncel araştırma için Gemini'nin native arama aracı. |
| `session_control` | ✓ | ✓ | Açıkça istenen wake, standby ve stop geçişleri. |

Komut yolunda sabit Spotify/Notes/Telegram dalları yoktur. Örneğin uygulama
başlatma genel `launch_app` işlemiyle, medya genel `media_control` ile,
görsel arayüz işlemleri ise `computer` veya `linux_desktop` ile incelenip
doğrulanır.

Yönetici yetkili shell ayrı bir yoldur. macOS native yönetici penceresini,
Linux ise mevcutsa görünür polkit `pkexec` penceresini kullanır. Kyros sesle
parola istemez ve normal komutları root olarak çalıştırmaz.

## Linux ve Hyprland

Linux, Wayland'ın macOS gibi sınırsız girdi API'si varmış gibi davranmak yerine
yetenek odaklı bir adaptör kullanır.

`linux_desktop` şunları sunabilir:

- Gerçek pencere, monitör, odak, taşıma, boyutlandırma, kapatma ve workspace
  işlemleri için Hyprland IPC;
- Hedef uygulama sunuyorsa AT-SPI2 erişilebilirlik ağacı ve action'ları;
- `grim`/`slurp` veya XDG Screenshot portalı ile ekran görüntüsü;
- Unicode yazımında `wtype`; uygun yerde `ydotool`, portal ve clipboard-paste
  fallback'leri;
- Yetki verildiğinde `ydotoold`, XDG Remote Desktop veya X11 üzerinden fare ve
  düşük seviyeli klavye girdisi;
- Wayland/X11 clipboard, uygulama başlatma, bildirim ve `capabilities`
  incelemesi.

Model önce inspect yapacak şekilde yönlendirilir; gerçek PID, accessibility
path, role, label, pencere adresi, monitör veya workspace sonucunu kullanır.
Durum değiştiren işlemlerden sonra tekrar doğrulama yapar. Compositor veya
masaüstü güvenliği bir yeteneği reddederse araç gerçek hatayı döndürür; sahte
tıklama, tuş, ekran veya uygulama durumu bildirmez.

Yetenek matrisini görmek için:

~~~bash
venv/bin/python main.py --doctor
~~~

Tam Hyprland kabul listesi [LINUX_TEST.md](LINUX_TEST.md) dosyasındadır.

## macOS

macOS yolu native Swift ses köprüsünü ve mevcut Accessibility/Quartz/AppleScript
entegrasyonlarını kullanır. Linux adaptörü ve Linux bağımlılık dosyaları
macOS'ta seçilmez.

İlk gerçek çalıştırmada şu izinler istenebilir:

- Mikrofon;
- Accessibility;
- Screen Recording;
- AppleScript veya System Events ile kontrol edilen uygulamalar için
  Automation.

Kyros'un yapacağı işlere göre yalnızca gereken izinleri ver. Tam macOS kontrol
listesi [MAC_TEST.md](MAC_TEST.md) dosyasındadır.

## Ses

| Platform | Varsayılan backend | İsteğe bağlı yol |
| --- | --- | --- |
| macOS | Apple voice processing kullanan Swift `AVAudioEngine` | PortAudio |
| Linux | `pw-record` ve `pw-play` üzerinden PipeWire | `--with-portaudio` ile PortAudio |

Live protokolü 16 kHz mikrofon PCM ve 24 kHz konuşma çıktısı kullanır. macOS,
hoparlör yankısını azaltmak için Apple voice-processing yolunu kullanabilir.
Linux'ta Apple katmanı yoktur; hoparlör yankısı duyuluyorsa kulaklık veya
doğru yapılandırılmış PipeWire/WirePlumber echo-cancellation grafiği tercih
edilmelidir.

Ses aygıtları Ayarlar'dan veya `KYROS_INPUT_DEVICE` ve
`KYROS_OUTPUT_DEVICE` ortam değişkenlerinden seçilebilir. Aygıt değişiklikleri
izlenir ve etkilenen akış yeniden başlatılır.

## Yapılandırma

### API anahtarı ve model

Öncelik sırası:

1. `GEMINI_API_KEY` ve `GEMINI_MODEL` ortam değişkenleri;
2. aynı değerlerin `config/local.json` içindeki karşılığı;
3. `GEMINI_MODEL` için yerleşik varsayılan model.

Installer `config/local.json` dosyasını yalnızca ihtiyaç varsa oluşturur ve
izinini mevcut kullanıcıya sınırlar (`0600`). Elle kurulumda şablondan başla:

~~~bash
cp config/local.json.example config/local.json
chmod 600 config/local.json
~~~

Anahtarı dosyaya yerel olarak ekleyebilir veya Kyros'u çalıştırmadan önce
ortam değişkeni verebilirsin:

~~~bash
export GEMINI_API_KEY="your-direct-google-gemini-key"
~~~

Kyros, Live `bidiGenerateContent` protokolü için doğrudan Google Gemini API
anahtarı ister. OpenAI uyumlu bir anahtar veya proxy eşdeğer backend değildir.

### Çalışma ayarları

| Değişken | Varsayılan | Anlamı |
| --- | --- | --- |
| `KYROS_AUDIO_BACKEND` | macOS'ta `native`; Linux'ta `pipewire` | Desteklenen yerde `native`, `pipewire` veya `portaudio` seçer. |
| `KYROS_INPUT_DEVICE` | Sistem varsayılanı | Girdi aygıtı adı/kimliği override'ı. |
| `KYROS_OUTPUT_DEVICE` | Sistem varsayılanı | Çıktı aygıtı adı/kimliği override'ı. |
| `GEMINI_MODEL` | `gemini-2.5-flash-native-audio-latest` | Live ses modeli; Ayarlar kullanılabilir modelleri yenileyebilir. |

Ayarlar paneli, kaydedip Live bağlantıyı yeniden başlatmadan önce anahtar ve
modeli test edebilir.

## Tanılama ve test

Testleri proje ortamından çalıştır:

~~~bash
venv/bin/python -m unittest discover -s tests -v
~~~

Installer aynı test paketini sessiz modda çalıştırır. Test kapsamı şunları
içerir:

- bağlantı yaşam döngüsü, yeniden bağlanma, iptal, söz kesme ve oturum
  disiplini;
- macOS ve Linux ses adaptörleri;
- PipeWire keşfi, aygıt yönlendirme ve yetenek raporu;
- shell, uygulama başlatma, medya, clipboard, UI dispatch ve platform
  bildirileri;
- installer/uninstaller sahiplik sınırları ve izin dosyası güvenliği;
- loglama ve panel kapanış davranışı.

`--doctor` salt-okunur yerel kontrol yapar, Gemini'ye bağlanmaz.
`--audio-check` yalnızca seçilen yerel ses backend'ini başlatır, Gemini
çağırmaz. `--text` gerçek Live API'yi kullanır ancak mikrofonu açmaz.

## Sorun giderme

| Belirti | İlk kontrol |
| --- | --- |
| “Connecting” ekranında kalıyor | Ayarlar'da anahtar/modeli test et, ardından `logs/kyros.log` dosyasını incele. |
| macOS mikrofon hatası | Kyros'u çalıştıran uygulamaya Terminal → Privacy → Microphone izni ver; `--audio-check` çalıştır. |
| macOS arayüz işlemi reddediliyor | Gerekiyorsa Accessibility, Screen Recording veya Automation izni ver. |
| Linux mikrofon başlamıyor | `--audio-check` çalıştır; PipeWire, WirePlumber, `pw-record` ve `pw-play` durumunu kontrol et. |
| Linux yazma/tıklama çalışmıyor | `--doctor` çalıştır; `wtype`, `ydotoold`, portal onayı ve oturum tipini kontrol et. |
| AT-SPI2 ağacı boş | `at-spi2-core`, PyGObject/typelib, çalışan AT-SPI2 bus ve erişilebilirlik sunan uygulamayı kontrol et. |
| Medya kontrolü çalışmıyor | Linux'ta çalışan MPRIS oynatıcı ve `playerctl`; macOS'ta inspect sonucundaki uygulama adını kontrol et. |
| Kaldırmada eski paket görünüyor | Manifest planını oku; yalnızca Kyros'un sonradan kurduğu paketler adaydır. |
| Terminal çok gürültülü | Normal mod kısa olayları gösterir; yalnızca tanılama sırasında `--debug` kullan. Ayrıntı `logs/kyros.log` içindedir. |

Loglar yerel ve döner yapıdadır:

~~~bash
tail -f logs/kyros.log
~~~

`logs/` aktif dosyada yaklaşık 1 MiB ve üç dönen dosya ile sınırlıdır.
Kurulum/paket ayrıntıları yok sayılan `.kyros/` altında tutulur.

## Güvenlik ve gizlilik

- API anahtarı yok sayılan `config/local.json` içinde `0600` izinle veya ortam
  değişkeninde tutulur; Kyros anahtarı loglamaz.
- Live oturumunun gerektirdiği ses, transkripsiyon, araç çağrısı ve araç
  sonuçları Gemini'ye gönderilir.
- Ekran görüntüsü yalnızca ekran aracı kullanıldığında Gemini'ye gönderilir;
  depo veya kalıcı yerel klasörde tutulmaz.
- Normal araçlar giriş yapmış kullanıcı olarak çalışır. Gizli root daemon'ı
  veya ayrı bir privileged komut yolu yoktur.
- Installer yönetici yetkisini yalnızca paket ve açıkça anlatılan Linux izin
  işlemleri için ister.
- `run_shell` bilinçli olarak geneldir; kullanıcı tarafından açılmış bir
  terminal kadar güvenilir kabul edilmelidir.

## Depo temizliği

Depodaki `.gitignore` hem macOS hem Linux çıktılarının tamamını hedefler:
yerel credential'lar, ortam dosyaları, sanal ortamlar, Python cache'leri,
loglar, installer state'i, native build çıktıları, app bundle'ları, editör
metadata'sı, büyük ses/model dosyaları ve geçici dosyalar.

Hiçbir şeyi stage etmeden denetle:

~~~bash
git status --short --ignored
git check-ignore -v config/local.json .env .kyros logs venv native/kyros-audio
git add -A --dry-run
~~~

Ignore kuralı yalnızca henüz takip edilmeyen dosyaları etkiler. Bir secret daha
önce commit edildiyse geçmişten temizlenmeli ve anahtar yenilenmelidir;
`.gitignore` daha önce takip edilmiş yolu untrack etmez.

## Proje yapısı

~~~text
.
├── main.py                         # Giriş noktası ve CLI
├── config/
│   ├── settings.py                 # Anahtar, model, ses ve çalışma ayarları
│   └── local.json.example          # Güvenli yapılandırma şablonu
├── core/
│   ├── gemini_live.py              # Live oturumu, ses akışı, iptal
│   ├── audio_io.py                 # macOS native/PortAudio yolu
│   ├── linux_audio.py              # Linux PipeWire/PortAudio yolu
│   ├── linux_ui.py                 # Wayland, Hyprland, AT-SPI2, X11, portal
│   ├── macos_ui.py                 # macOS Accessibility ve ekran kontrolleri
│   ├── executor.py                 # Genel araç çalıştırma
│   ├── protocol.py                 # Sistem talimatı ve araç bildirimleri
│   ├── doctor.py                   # Salt-okunur tanılama
│   ├── bootstrap.py                # Proje ortamı bootstrap'i
│   └── web_page.py                 # Okunabilir web sayfası getirici
├── gui/panel.py                    # PyQt6 paneli ve Ayarlar görünümü
├── native/
│   ├── AudioBridge.swift           # macOS AVAudioEngine köprüsü
│   ├── AudioInfo.plist             # Native kullanım metadata'sı
│   └── Launcher.c                  # İsteğe bağlı macOS launcher kaynağı
├── scripts/kyros-system.sh         # Linux paket/izin yaşam döngüsü
├── system/                         # Scoped uinput ve ydotoold şablonları
├── tests/                          # Birim, contract ve Linux testleri
├── install.sh                      # Platform farkındalıklı installer
├── uninstall.sh                    # Sahiplik farkındalıklı uninstaller
├── build_audio.sh                  # macOS ses köprüsü derleyicisi
├── requirements*.txt               # Ortak ve platforma özel Python deps
├── MAC_TEST.md                     # macOS kabul listesi
├── LINUX_TEST.md                   # Linux/Hyprland kabul listesi
├── LICENSE                         # MIT lisansı
└── README.md / README.tr.md / README.ru.md  # Dokümantasyon
~~~

`venv/`, `logs/`, `.kyros/`, `__pycache__/` ve üretilen
`native/kyros-audio` gibi runtime çıktıları kaynak ağacında tutulmaz ve Git
tarafından yok sayılır.

## Katkı sağlama

1. `main` üzerinden odaklı bir branch oluştur.
2. Platforma özel kodu ilgili adaptörün arkasında tut.
3. Cümleye veya uygulamaya özel intent dalları ekleme.
4. Araç, installer ve platform değişikliklerine contract testi ekle/güncelle.
5. Test paketini ve `git diff --check` komutunu çalıştır.
6. API anahtarı, local config, log, build çıktısı veya generated binary commit
   etme.

~~~bash
git switch -c feature/kisa-aciklama
venv/bin/python -m unittest discover -s tests -v
git diff --check
~~~

## Lisans

Kyros [MIT Lisansı](LICENSE) ile yayımlanır.
