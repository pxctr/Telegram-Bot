#!/usr/bin/env python3
"""
IceOut.org -> Telegram Bot
Yeni ICE aktivite raporlarını takip edip Telegram kanalına otomatik paylaşır.

Playwright kullanarak headless browser ile API'ye erişir.
(Site CSRF + session cookie gerektirdiği için requests yeterli değil)
"""

import asyncio
import json
import os
import sys
import time
import re
import requests
from datetime import datetime, timezone
from playwright.async_api import async_playwright

# ─── Ayarlar ────────────────────────────────────────────────────────────────────

ICEOUT_WEB_URL = "https://iceout.org/en/reportInfo/{id}"
ICEOUT_SITE_URL = "https://iceout.org/en/"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_seen.json")

# İlk çalıştırmada kaç rapor gönderilsin (spam olmasın diye sınırlı)
FIRST_RUN_LIMIT = 3

# API'den kaç rapor çekilsin
FETCH_LIMIT = 30

# Kategori eşlemeleri
CATEGORY_MAP = {
    0: ("🔴 Critical", "Critical"),
    1: ("🟠 Active", "Active"),
    2: ("🟢 Observed", "Observed"),
    3: ("🟣 Other", "Other"),
}

# ABD eyalet kısaltmaları -> tam isim
US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}


# ─── Yardımcı Fonksiyonlar ──────────────────────────────────────────────────────

def log(message: str):
    """Zaman damgalı log mesajı yazdırır."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{timestamp}] {message}")


def load_state() -> dict:
    """Son görülen rapor ID'sini dosyadan okur."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            log("⚠️ State dosyası okunamadı, sıfırdan başlanıyor.")
    return {"last_seen_id": 0, "total_sent": 0}


def save_state(state: dict):
    """Son görülen rapor ID'sini dosyaya yazar."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
    log(f"💾 State kaydedildi: last_seen_id={state['last_seen_id']}, total_sent={state['total_sent']}")


def extract_state_from_location(location: str) -> str:
    """
    Adres stringinden eyalet bilgisini çıkarır.
    Örnek: "5127 W Imperial Hwy, Lennox, CA 90304, USA" -> "California (CA)"
    """
    if not location:
        return "Bilinmiyor"

    # "City, STATE ZIP, USA" veya "City, STATE, USA" kalıbını ara
    match = re.search(r',\s*([A-Z]{2})\s+\d{5}', location)
    if not match:
        match = re.search(r',\s*([A-Z]{2})\s*,', location)
    if not match:
        # Son çare: adresteki herhangi bir 2 harfli eyalet kısaltmasını bul
        parts = location.split(",")
        for part in parts:
            stripped = part.strip().split()[0] if part.strip() else ""
            if stripped in US_STATES:
                full_name = US_STATES.get(stripped, stripped)
                return f"{full_name} ({stripped})"
        return "Bilinmiyor"

    state_abbr = match.group(1)
    full_name = US_STATES.get(state_abbr, state_abbr)
    return f"{full_name} ({state_abbr})"


def format_datetime(iso_string: str) -> str:
    """ISO tarih stringini okunabilir formata çevirir."""
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y, %H:%M UTC")
    except (ValueError, AttributeError):
        return iso_string or "Bilinmiyor"


def format_telegram_message(report: dict) -> str:
    """Bir raporu Telegram mesaj formatına dönüştürür."""
    report_id = report.get("id", "?")
    location = report.get("location_description", "Konum belirtilmemiş")
    incident_time = format_datetime(report.get("incident_time", ""))
    created_at = format_datetime(report.get("created_at", ""))
    description = report.get("activity_description", "")
    category_num = report.get("category_enum", 3)
    category_emoji, category_name = CATEGORY_MAP.get(category_num, ("🟣 Other", "Other"))
    state = extract_state_from_location(location)
    web_url = ICEOUT_WEB_URL.format(id=report_id)

    # Doğrulama durumu
    approved = report.get("approved", False)
    verification = "✅ Verified" if approved else "⏳ Not Confirmed"

    # Görevli sayısı
    officials = report.get("number_of_officials")
    officials_text = f"\n👮 Officials: {officials}" if officials else ""

    # Açıklama (yoksa boş bırak)
    desc_text = f"\n\n📝 {description}" if description else ""

    message = (
        f"{category_emoji}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"📍 {location}\n"
        f"🏛️ {state}\n"
        f"📅 {incident_time}\n"
        f"🔖 {verification}"
        f"{officials_text}"
        f"{desc_text}\n"
        f"\n"
        f"🔗 Details: {web_url}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📡 iceout.org • #{report_id}"
    )
    return message


# ─── API Fonksiyonları (Playwright ile) ──────────────────────────────────────────

async def fetch_reports_via_browser(limit: int = FETCH_LIMIT) -> list:
    """
    Playwright headless browser kullanarak iceout.org API'sine erişir.
    Site CSRF + session cookie gerektirdiği için bu yöntem gerekli.
    """
    log(f"🌐 Headless browser başlatılıyor...")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                )
            )
            page = await context.new_page()

            # Siteye git ve cookie'leri al
            log("📡 iceout.org'a bağlanılıyor...")
            await page.goto(ICEOUT_SITE_URL, wait_until="networkidle", timeout=45000)
            await page.wait_for_timeout(3000)

            cookies = await context.cookies()
            cookie_names = [c["name"] for c in cookies]
            log(f"🍪 Cookie'ler alındı: {cookie_names}")

            # API'den raporları çek (browser context içinde)
            log(f"📡 API'den son {limit} rapor çekiliyor...")
            reports = await page.evaluate(
                """
                async (limit) => {
                    try {
                        const response = await fetch(
                            `/api/reports/?count=${limit}`,
                            { credentials: 'include' }
                        );
                        if (!response.ok) {
                            return { error: `HTTP ${response.status}`, data: [] };
                        }
                        const data = await response.json();
                        return { error: null, data: data };
                    } catch (e) {
                        return { error: e.message, data: [] };
                    }
                }
                """,
                limit,
            )

            await browser.close()

            if reports.get("error"):
                log(f"⚠️ API hatası: {reports['error']}")
                return []

            data = reports.get("data", [])
            log(f"✅ {len(data)} rapor alındı")
            return data

    except Exception as e:
        log(f"❌ Browser hatası: {e}")
        return []


def download_image(url: str) -> bytes | None:
    """Fotoğrafı indirir ve bytes olarak döndürür."""
    try:
        log(f"📥 Fotoğraf indiriliyor...")
        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36"
                ),
            },
        )
        response.raise_for_status()
        content = response.content
        size_kb = len(content) / 1024
        log(f"✅ Fotoğraf indirildi ({size_kb:.0f} KB)")
        return content
    except requests.exceptions.RequestException as e:
        log(f"⚠️ Fotoğraf indirilemedi: {e}")
        return None


# ─── Telegram Fonksiyonları ──────────────────────────────────────────────────────

def send_telegram_message(text: str, photo_bytes: bytes | None = None) -> bool:
    """Telegram kanalına mesaj (ve opsiyonel fotoğraf) gönderir."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("❌ TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID tanımlanmamış!")
        return False

    try:
        if photo_bytes:
            # Fotoğraflı mesaj gönder
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            files = {"photo": ("report.jpg", photo_bytes, "image/jpeg")}
            data = {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": text[:1024],  # Telegram caption limiti
                "parse_mode": "HTML",
            }
            # Markdown yerine HTML kullan (daha az parse hatası)
            html_text = text_to_html(text)
            data["caption"] = html_text[:1024]
            response = requests.post(url, data=data, files=files, timeout=30)
        else:
            # Sadece metin mesaj gönder
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            html_text = text_to_html(text)
            data = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": html_text[:4096],  # Telegram mesaj limiti
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            }
            response = requests.post(url, json=data, timeout=30)

        result = response.json()
        if result.get("ok"):
            log("✅ Telegram mesajı gönderildi!")
            return True
        else:
            error_desc = result.get("description", "Bilinmeyen hata")
            log(f"❌ Telegram hatası: {error_desc}")
            # Parse hatası varsa düz metin olarak dene
            if "parse" in error_desc.lower() or "can't" in error_desc.lower():
                log("🔄 Düz metin olarak tekrar deneniyor...")
                return send_telegram_plain(text, photo_bytes)
            return False

    except requests.exceptions.RequestException as e:
        log(f"❌ Telegram bağlantı hatası: {e}")
        return False


def text_to_html(text: str) -> str:
    """Düz metni Telegram HTML formatına dönüştürür."""
    # HTML özel karakterlerini escape et (& ilk sırada olmalı)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def send_telegram_plain(text: str, photo_bytes: bytes | None = None) -> bool:
    """Düz metin olarak gönderir (fallback)."""
    try:
        if photo_bytes:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            files = {"photo": ("report.jpg", photo_bytes, "image/jpeg")}
            data = {"chat_id": TELEGRAM_CHAT_ID, "caption": text[:1024]}
            response = requests.post(url, data=data, files=files, timeout=30)
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            data = {"chat_id": TELEGRAM_CHAT_ID, "text": text[:4096]}
            response = requests.post(url, json=data, timeout=30)

        result = response.json()
        return result.get("ok", False)
    except Exception as e:
        log(f"❌ Fallback gönderim hatası: {e}")
        return False


# ─── Ana Çalışma Fonksiyonu ──────────────────────────────────────────────────────

async def process_new_reports():
    """Yeni raporları kontrol eder ve Telegram'a gönderir."""
    log("🚀 IceOut Telegram Bot başlatıldı")
    log(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # State'i yükle
    state = load_state()
    last_seen_id = state.get("last_seen_id", 0)
    total_sent = state.get("total_sent", 0)
    is_first_run = last_seen_id == 0

    if is_first_run:
        log("🆕 İlk çalıştırma tespit edildi")
    else:
        log(f"📌 Son görülen ID: {last_seen_id}")

    # Raporları çek (Playwright ile)
    reports = await fetch_reports_via_browser(FETCH_LIMIT)
    if not reports:
        log("📭 Rapor bulunamadı veya bağlantı hatası. Çıkılıyor.")
        return

    # Raporları ID'ye göre sırala (küçükten büyüğe — eskiden yeniye)
    reports.sort(key=lambda r: r.get("id", 0))

    # Yeni raporları filtrele
    new_reports = [r for r in reports if r.get("id", 0) > last_seen_id]

    if not new_reports:
        log("✨ Yeni rapor yok. Bir sonraki kontrole kadar bekleniyor.")
        # State'i yine de kaydet (cache yenilenmesi için)
        max_id = max(r.get("id", 0) for r in reports)
        if max_id > last_seen_id:
            state["last_seen_id"] = max_id
        state["last_check"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        return

    log(f"🆕 {len(new_reports)} yeni rapor bulundu!")

    # İlk çalıştırmada çok fazla göndermemek için sınırla
    if is_first_run and len(new_reports) > FIRST_RUN_LIMIT:
        log(f"📋 İlk çalıştırma: sadece son {FIRST_RUN_LIMIT} rapor gönderilecek")
        # ID'yi yine de en son rapora ayarla (eskiler atlanır)
        skipped = new_reports[:-FIRST_RUN_LIMIT]
        if skipped:
            skip_max = max(r.get("id", 0) for r in skipped)
            log(f"⏭️ {len(skipped)} eski rapor atlandı (ID <= {skip_max})")
        new_reports = new_reports[-FIRST_RUN_LIMIT:]

    sent_count = 0
    for report in new_reports:
        report_id = report.get("id", 0)
        log(f"\n{'─' * 40}")
        log(f"📋 Rapor #{report_id} işleniyor...")

        # Mesajı oluştur
        message = format_telegram_message(report)

        # Fotoğraf var mı kontrol et
        photo_bytes = None
        media = report.get("media", [])
        if media:
            first_media = media[0]
            # Thumbnail daha hızlı indirilir, yoksa orijinal resmi dene
            photo_url = (
                first_media.get("medium_thumbnail")
                or first_media.get("small_thumbnail")
                or first_media.get("image")
            )
            if photo_url:
                photo_bytes = download_image(photo_url)

        # Telegram'a gönder
        success = send_telegram_message(message, photo_bytes)
        if success:
            sent_count += 1
            total_sent += 1
        else:
            log(f"⚠️ Rapor #{report_id} gönderilemedi, devam ediliyor...")

        # Rate limiting — Telegram API flood kontrolü
        time.sleep(1.5)

    # En son görülen ID'yi güncelle
    max_id = max(r.get("id", 0) for r in reports)
    state["last_seen_id"] = max_id
    state["total_sent"] = total_sent
    state["last_check"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    log(f"\n{'═' * 40}")
    log(f"📊 Özet: {sent_count}/{len(new_reports)} rapor gönderildi")
    log(f"📊 Toplam gönderilen: {total_sent}")
    log(f"📊 Son görülen ID: {max_id}")
    log("✅ İşlem tamamlandı!")


# ─── Giriş Noktası ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Ortam değişkenlerini kontrol et
    if not TELEGRAM_BOT_TOKEN:
        print("❌ HATA: TELEGRAM_BOT_TOKEN ortam değişkeni gerekli!")
        print("   Telegram'da @BotFather'dan bot oluşturup token'ı alın.")
        sys.exit(1)

    if not TELEGRAM_CHAT_ID:
        print("❌ HATA: TELEGRAM_CHAT_ID ortam değişkeni gerekli!")
        print("   Telegram kanal ID'nizi girin (örn: @kanal_adi veya -100xxxxxxxxxx)")
        sys.exit(1)

    asyncio.run(process_new_reports())
