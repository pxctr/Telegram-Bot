# IceOut.org → Telegram Bot 🤖

iceout.org sitesindeki yeni ICE aktivite raporlarını otomatik olarak Telegram kanalınıza gönderen bot.

## Özellikler

- 🔄 Her 30 dakikada bir yeni raporları kontrol eder
- 📍 Konum, tarih, eyalet bilgilerini formatlar
- 📸 Raporlardaki fotoğrafları indirir ve gönderir
- 🏷️ Rapor kategorisini gösterir (Critical, Active, Observed, Other)
- 🔗 Rapor detay linkini ekler
- 💾 Son görülen rapor ID'sini cache'de saklar (tekrar gönderim olmaz)
- 🌐 Playwright headless browser ile güvenli API erişimi

## Kurulum — Adım Adım

### Adım 1: Telegram Bot Oluşturma

1. Telefonunuzda veya bilgisayarınızda Telegram'ı açın
2. Arama çubuğuna **@BotFather** yazıp tıklayın
3. `/start` yazın
4. `/newbot` yazın
5. Bot için bir **isim** girin (örn: `IceOut Alert Bot`)
6. Bot için bir **kullanıcı adı** girin — sonunda `bot` olmalı (örn: `iceout_alert_bot`)
7. BotFather size bir **token** verecek. Bu tokeni kopyalayın ve bir yere not edin!
   - Örnek: `7123456789:AAHnXXXXXXXXXXXXXXXXXXXXXXXXXX`

### Adım 2: Telegram Kanalı Oluşturma

1. Telegram'da hamburger menüsüne (☰) tıklayın
2. **"Yeni Kanal"** (New Channel) seçin
3. Kanala bir isim verin (örn: `ICE Activity Alerts`)
4. Kanal türünü **Public** yapın
5. Kanala bir **kullanıcı adı** verin (örn: `iceout_alerts`) — bu önemli!
6. Kanalı oluşturun
7. Kanal ayarlarına gidin → **Yöneticiler** → **Yönetici Ekle**
8. 1. adımda oluşturduğunuz botu arayıp ekleyin
9. Bota **mesaj gönderme** yetkisi verin

### Adım 3: GitHub'a Yükleme

1. [github.com](https://github.com) hesabınıza girin (yoksa ücretsiz açın)
2. Sağ üst köşede **+** → **New repository** tıklayın
3. İsim: `iceout-telegram-bot`
4. **Public** olarak oluşturun (ücretsiz Actions için gerekli)
5. Bu proje klasörünü GitHub'a yükleyin:

```bash
cd iceout-telegram-bot
git init
git add .
git commit -m "İlk commit"
git branch -M main
git remote add origin https://github.com/KULLANICI_ADINIZ/iceout-telegram-bot.git
git push -u origin main
```

### Adım 4: GitHub Secrets Tanımlama

1. GitHub'da repo sayfanıza gidin
2. **Settings** (Ayarlar) sekmesine tıklayın
3. Sol menüde **Secrets and variables** → **Actions** tıklayın
4. **New repository secret** butonuna tıklayın
5. İki secret ekleyin:

| Secret Adı | Değer |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather'dan aldığınız token (örn: `7123456789:AAH...`) |
| `TELEGRAM_CHAT_ID` | Kanal kullanıcı adınız, başında @ ile (örn: `@iceout_alerts`) |

### Adım 5: İlk Testi Yapın

1. GitHub'da **Actions** sekmesine tıklayın
2. Sol menüde **IceOut Telegram Bot** workflow'unu seçin
3. **Run workflow** butonuna tıklayın
4. Telegram kanalınızı kontrol edin — mesajlar gelecektir!

## Dosya Yapısı

```
iceout-telegram-bot/
├── .github/
│   └── workflows/
│       └── check_iceout.yml   # GitHub Actions (30 dk otomatik)
├── main.py                     # Ana bot scripti (Playwright)
├── requirements.txt            # Python bağımlılıkları
├── last_seen.json             # State dosyası (otomatik)
├── .gitignore                 # Git'e dahil edilmeyenler
└── README.md                  # Bu dosya
```

## Yerel Test (Opsiyonel)

```bash
# Virtual environment oluştur
python3 -m venv .venv
source .venv/bin/activate

# Bağımlılıkları yükle
pip install -r requirements.txt
python -m playwright install chromium

# Ortam değişkenlerini ayarla
export TELEGRAM_BOT_TOKEN="your_token_here"
export TELEGRAM_CHAT_ID="@your_channel"

# Çalıştır
python main.py
```

## Mesaj Formatı

Bot Telegram'a şu formatta mesajlar gönderir:

```
🔴 Critical
━━━━━━━━━━━━━━━━━━━━

📍 5127 W Imperial Hwy, Lennox, CA 90304, USA
🏛️ California (CA)
📅 14 Feb 2026, 21:58 UTC
🔖 ✅ Verified

📝 CHP escorting 7 unmarked suburban from the 405 south...

🔗 Details: https://iceout.org/en/reportInfo/108250
━━━━━━━━━━━━━━━━━━━━
📡 iceout.org • #108250
```

## Sorun Giderme

- **Bot mesaj göndermiyor**: Actions sekmesinden log'ları kontrol edin
- **"TELEGRAM_BOT_TOKEN gerekli" hatası**: Secrets'ları doğru girdiğinizden emin olun
- **Kanal ID hatası**: Chat ID'nin başında `@` olduğundan emin olun
- **API hatası**: iceout.org geçici olarak erişilemez olabilir, bir sonraki çalıştırmada düzelir
