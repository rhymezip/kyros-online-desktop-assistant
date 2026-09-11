# Kyros Linux / Hyprland Kabul Testleri

Bu liste gerçek bir Wayland + Hyprland oturumunda uygulanır. Testleri mümkünse
uygulama açıkken, aynı kullanıcı hesabında ve önce yedek/deneme verileriyle yapın.
Her işlemden sonra yalnızca Kyros'un sözünü değil, ekrandaki gerçek sonucu ve
`logs/kyros.log` kaydını kontrol edin.

## 1. Ortam ve kurulum

1. `echo "$XDG_SESSION_TYPE $XDG_CURRENT_DESKTOP $WAYLAND_DISPLAY"` çıktısında
   `wayland` ve Hyprland görülmeli.
2. `hyprctl -j monitors`, `hyprctl -j clients` ve `hyprctl cursorpos` çalışmalı.
3. `pw-record --help` ve `pw-play --help` çalışmalı. PipeWire ve WirePlumber
   servisleri aynı kullanıcı oturumunda hazır olmalı; `pactl` yoksa varsayılan
   route izleme için `wpctl` bulunmalıdır.
4. Hızlı ekran için `grim`, bölge seçimi için `slurp`, Wayland clipboard için
   `wl-copy`/`wl-paste`, bildirim için `notify-send` kurulu olmalı.
5. AT-SPI2 için dağıtımın `at-spi2-core`, `python-gobject`/PyGObject ve ilgili
   typelib paketleri kurulmalı. Uygulama da gerçekten erişilebilirlik ağacı
   sunmalıdır; her uygulama aynı ayrıntıyı vermez.
6. Saf Wayland klavye için `wtype` önerilir. Mouse tıklama/sürükleme için
   çalışan `ydotoold` + `ydotool` önerilir. Bunlar yoksa Kyros, izin verildiği
   durumda XDG Remote Desktop portalını dener; portal kullanıcı onayı ister.
7. `install.sh --dry-run` önce dağıtımı ve paket planını gösterir. Normal
   `install.sh` resmi paket yöneticisiyle eksik sistem paketlerini kurar; sudo
   parolası istenirse ekranda neden istendiği açıklanır. Kurulumdan sonra:

   ```bash
   bash install.sh
   venv/bin/python main.py --doctor
   ```

8. Mouse/klavye için `/dev/uinput` izni kurulmuşsa Kyros özel `kyros-input`
   grubunu ve kullanıcı `ydotoold` servisini kullanır. Grup değişikliğinden
   sonra çıkış yapıp tekrar girin; sonra `systemctl --user status kyros-ydotoold`
   ile servisi kontrol edin.

9. Kurulumu kaldırmayı denemeden önce `bash uninstall.sh --dry-run` çalıştırın.
   Uninstaller yalnızca Kyros manifestinde yeni kurulduğu yazan paketleri
   hedefler; kurulumdan önce var olan paketleri ve `config/local.json` dosyasını
   varsayılan olarak korur.

`doctor` API çağrısı yapmaz. Eksik Gemini anahtarı ve eksik Python bağımlılığı
uygulama başlamadan önce düzeltilmelidir; yalnızca PortAudio fallbackine ait
`numpy`/`sounddevice` eksikliği PipeWire yolunu engellemez.

## 2. Panel ve yaşam döngüsü

1. `venv/bin/python main.py` ile paneli başlatın.
2. Panelin Hyprland ekranının üstüne yerleştiğini, normal pencereleri
   gereksizce öne çekmediğini ve Ayarlar düğmesinin tıklanabildiğini kontrol edin.
3. Sağ tık menüsünden bekleme, durdurma, mikrofon kapatma ve çıkışı deneyin.
4. Çıkıştan sonra `ps -eo pid=,args=` ile Kyros, `pw-record`, `pw-play` veya
   araç child process'i kalmadığını kontrol edin.

## 3. Canlı ses ve aygıt değişimi

1. Dahili mikrofon ve hoparlörle konuşun; ses çıktısının mikrofona yankılanıp
   kendisini kesintiye uğratmaması gerekir. Hoparlör için uygun ses seviyesi
   kullanın.
2. Uzun bir cevap sırasında “dur, başka bir şey soracağım” deyin. Eski TTS
   sesi kesilmeli, yeni istek eski ses kuyruğundan etkilenmemeli.
3. Kulaklık ve Bluetooth çıkışını takıp çıkarın. Varsayılan source/sink
   değiştiğinde panel kısa süre `SES AYGITI DEĞİŞİYOR` göstermeli; bağlantı ve
   standby/aktif durumu korunarak yeni akışa dönmeli.
4. Mikrofonu veya çıkışı Ayarlar panelinden açıkça seçip tekrar deneyin.
   Seçili aygıt ile varsayılan aygıt değişiminin birbirine karışmadığını kontrol
   edin.
5. `venv/bin/python main.py --audio-check` ile Gemini'ye bağlanmadan gerçek bir
   mikrofon PCM çerçevesi alınabildiğini doğrulayın. PortAudio fallbackini
   doğrulamak için `venv/bin/python main.py --audio-backend portaudio --audio-check`
   çalıştırın.

## 4. Model araçları ve gerçek sonuç doğrulaması

Araçların hiçbirinde uygulama adı veya cümle listesi varsayımı yoktur. Modelden
önce durumu gözlemesini ve işlemden sonra yeniden doğrulamasını isteyin.

1. Genel dosya işlemi: geçici bir klasörde dosya oluşturma, okuma, düzenleme ve
   gerçek içeriği kontrol etme.
2. `computer` veya `linux_desktop` ile `inspect`: Hyprland pencereleri,
   monitörler, aktif pencere ve mümkünse AT-SPI2 ağacı dönmeli.
3. `screenshot`: gerçek ekran JPEG'i Gemini bağlamına gitmeli; yalnızca
   “screenshot aldım” cümlesi başarı kabul edilmemeli.
4. Erişilebilir bir butonda `ax_press`, metin alanında `ax_set` deneyin. Önceki
   `pid`, `path`, `role` ve `label` değerleriyle yapın; arayüz değişirse Kyros'un
   işlemi reddedip yeniden inspect istemesi gerekir.
5. `wtype`/portal üzerinden Unicode, satır sonu ve modifier içeren klavye
   eylemlerini deneyin. Gerçek odaklanmış alanda metni kontrol edin.
6. `ydotool` veya portal ile tek/çift tık, sürükleme ve dikey/yatay kaydırmayı
   deneyin. Backend yoksa işlem başarısız olmalı; imlecin taşınması tek başına
   tıklama başarısı sayılmamalı.
7. Clipboard okuma/yazma, pencere odaklama/kapatma/taşıma/boyutlandırma,
   workspace değiştirme, URI/uygulama açma ve bildirim araçlarını tek tek deneyin.
8. Her işlemden sonra pencere, içerik, dosya, clipboard veya bildirimi dışarıdan
   kontrol edin. Modelin sözlü onayı tek başına kanıt değildir.

## 5. Standby, wake, iptal ve hata

1. Açılışta ortam konuşması yapın; sistem aracı çalışmamalı.
2. “Hey Kyros” ile uyanın ve aynı cümlede bir Linux isteği verin.
3. Bekleme talebinden sonra araç çağrılmamalı; tekrar uyanana kadar sistem
   değişmemeli.
4. Uzun süren bir shell veya ekran işlemi sırasında durdurun. Yeni child process
   başlatılmamalı; bitmiş yan etkiler varsa Kyros bunları geri alınmış gibi
   göstermemeli.
5. Olmayan bir hedef, değişmiş AT-SPI yolu, kapalı portal veya eksik backend
   deneyin. Sonuç `ok=false` ve gerçek sebep olmalı; sahte başarı olmamalı.
6. Ağ bağlantısını kısa süre kesip geri getirin. Session resumption/reconnect
   sonrasında eski TTS veya kesilmiş araç otomatik olarak yeniden yürümemeli.

## 6. Kabul ölçütü

Linux sürümü şu koşulların hepsi sağlanınca kabul edilir:

- Mac dalı ve Mac kabul testleri değişmeden kalır.
- PipeWire akışı gerçek PCM üretir; başlangıç hatası sessizce yutulmaz.
- Hyprland pencereleri ve ekran görüntüsü okunur; işlem yoksa hata açıkça döner.
- AT-SPI2 yolu ve koordinat tabanlı işlem güncel gözleme dayanır.
- Wayland input izinsiz bypass edilmez; backend/portal yokluğu başarıya çevrilmez.
- İptal, reconnect, hot-plug ve child process kapanışı loglarda izlenebilir.
- `python3 -m unittest discover -s tests -v` temiz tamamlanır.
