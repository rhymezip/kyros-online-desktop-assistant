# Mac kabul testleri

Bu listeyi sırayla uygulayın. Hata varsa yaklaşık saati ve `logs/kyros.log` içindeki ilgili
satırları paylaşın; `config/local.json` ve API anahtarını paylaşmayın.

## 1. Kurulum ve izinler

1. Projeyi Mac'e taşıyın, `bash install.sh` çalıştırın. Derleme ve otomatik testler hatasız bitmeli.
2. `venv/bin/python main.py --doctor` çalıştırın. İlk kullanım öncesi izinlerin eksik görünmesi mümkündür.
3. `open Kyros.app` ile açın. Mikrofon iznini verin. Bağlanıyor, sonra Bekliyor görünmeli.
4. Panelin ekranın üst kenarına bitişik açıldığını kontrol edin. Çentikli Mac'te fiziksel çentikle
   birleşmeli; çentiksiz ekranda üstten sarkan siyah ada gibi görünmeli, menü çubuğunun altına kaymamalı.
5. Panel menüsüne ulaşabildiğinizi ve Çıkış'ın uygulamayı/ses motorunu kapattığını kontrol edin.
6. Erişilebilirlik/Ekran Kaydı/Otomasyon izinlerini ilk ilgili istekte verin. Gerektiğinde yeniden açın.

## 2. Wake ve standby

1. Açılışta Kyros'a seslenmeden normal konuşun. Sesli cevap vermemeli ve sistem işlemi yapmamalı.
2. “Hey Kyros” deyin. Uyanıp kısa cevap vermeli; ardından Dinliyor görünmeli.
3. Normal bir soru sorun. Cevapta “tamam efendim” geçmesi standby'a geçirmemeli.
4. “Bekleyebilirsin” deyin. Bekliyor durumuna geçmeli; eski konuşma tekrar başlamamalı.
5. Bu durumda uyandırmadan bir uygulama açmasını söyleyin. Yerel işlem yapılmamalı.
6. “Hey Kyros, Notlar'ı aç” deyin. Aynı cümlede uyanıp isteği yerine getirmeli.
7. 2–6 adımlarını en az beş kez tekrarlayın; durum kayması olmamalı.
8. Mikrofonu menüden kapatın. Seslenmek etkinleştirmemeli. Menüden açınca tekrar uyandırın.

Wake kararı mevcut Gemini ses modelindedir. Yanlış uyanma/uyanmama olursa tam söylenen cümleyi,
ortam sesini ve paneldeki transkripti not edin; kelime listesi ekleyerek üzeri örtülmemeli.

## 3. Ses akışı ve söz kesme

1. Önce Mac'in kendi mikrofonu/hoparlörü ile konuşun. Kyros kendi sesine cevap vermemeli.
2. Uzun bir açıklama isteyin. Konuşurken “dur, başka bir şey soracağım” deyin.
3. Ses kısa sürede kesilmeli; birkaç saniyelik eski ses kuyruktan geri gelmemeli.
4. Yeni sorunuza cevap vermeli. Konuşuyor etiketi gerçek ses bittikten sonra Dinliyor olmalı.
5. Panele sağ tıklayıp Şimdi durdur'u deneyin. Aynı şekilde eski ses ve bekleyen işlem durmalı.
6. Aynı denemeyi kulaklıkla yapın. Hoparlörde sorun olup kulaklıkta yoksa ses/yankı yolunu belirtin.
7. Bluetooth kullanıyorsanız ayrıca test edin; gecikmeyi dahili ses aygıtıyla karşılaştırın.
8. Uygulama açıkken kulaklığı takıp çıkarın. macOS varsayılan çıkışı değiştiğinde kısa süre
   “Ses aygıtı değişiyor” görünebilir; ardından yeni varsayılan aygıt kullanılmalı. Kod değişikliği
   veya uygulamayı yeniden başlatma gerekmemeli. Aktifken ve standby'dayken ayrı ayrı deneyin;
   önceki durum korunmalı. Mikrofon varsayılanı değiştiğinde de aynı davranışı kontrol edin.

Algılanan gecikmeyi telefon videosuyla veya kronometreyle yaklaşık ölçün. Kayıtların API/ağ,
yerel ses ve araç sürelerini ayırmaya yardımcı olması amaçlanır; şimdiden belirli bir süre garanti edilmez.

## 4. Genel sistem yeteneği

1. “Notlar'ı aç, Kyros Deneme başlıklı yeni bir not oluştur, içine menemen tarifi yaz.”
2. Gerçek notu açıp başlığını/içeriğini kontrol edin. Sadece sözlü başarı cevabı yeterli değildir.
3. “O notun sonuna iki kişilik olduğunu ekle.” Bağlamı takip edip mevcut notu düzenlemeli.
4. Kaynak kodda örneği olmayan, geçici bir klasörde dosya oluşturma/düzenleme isteği verin.
5. Bir pencereyi gösterip içeriği hakkında soru sorun. Arayüz okumayı ve ekran görüntüsünü ayrı ayrı deneyin.
6. “Fenerbahçe'nin güncel gündemini araştır, son haberleri tarihlerine göre anlat.” Görünür tarayıcı
   gerektirmeden güncel kaynak kullanmalı; paneldeki kaynakları açıp tarih ve iddiaları kontrol edin.
7. Telegram'da önce kendi Kayıtlı Mesajlar sohbetinizi kullanın: “Kayıtlı Mesajlar'a Kyros deneme yazısını gönder.”
   Doğru sohbet ve gerçek gönderim kontrol edilmeli. İlk testte başka kişiye deneme mesajı göndermeyin.

## 5. İptal, hata ve yeniden bağlantı

1. Geçici klasörde, aralarında bekleme bulunan birkaç dosya oluşturmasını isteyin; ilk işlem sırasında
   “iptal et” deyin. Henüz başlamayan adımlar yürümemeli. Tamamlanan dosyaların kalması normaldir.
2. Olmayan bir dosyayı açmasını isteyin. Hata bildirip varmış gibi davranmamalı.
3. Bir uygulamanın otomasyon iznini reddederek deneyin. Başarı dememeli; eksik izni açıklamalı.
4. Konuşurken ağı kısa süre kapatıp açın. Bağlanıyor görünmeli, bağlantı dönünce eski ses çalmamalı.
5. Bağlantı koparken yürüyen iş kendiliğinden yeniden çalışmamalı. Sonuç belirsizse kontrol etmeli.
6. En az 20 dakika kullanın; oturum yenilenmesi sonrasında wake, standby ve söz kesmeyi tekrar deneyin.
7. Uygulamadan çıkın. Activity Monitor'de Kyros'a ait `kyros-audio` veya devam eden araç süreci kalmamalı.

## 6. Yönetici yetkisi (yalnızca gerçekten gerekiyorsa)

Normal işlerde parola sorulmamalı. Yönetici erişimi isteyen bir işte standart macOS kimlik doğrulama
penceresi görünmeli. Parola sohbetten istenmemeli. Pencereyi iptal etmek sahte başarıya dönüşmemeli.
Sırf test etmek için sistem ayarlarını değiştirmeyin; gerçek ihtiyaç olduğunda bu adımı doğrulayın.
