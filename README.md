# 🎬 Video Compressor Bot

A Telegram bot that compresses videos using FFmpeg with per-user settings.

## Features
- Resolutions: 240p → 1080p (or keep original)
- Codecs: x264, x265, VP9, AV1
- Bit depth: 8-bit / 10-bit
- CRF control (18 = best quality, 51 = smallest)
- Watermark with custom text, color, position, size
- Aspect ratio control
- Metadata stripping
- Auto rename output files
- Upload as Document or Video
- Per-user settings stored in SQLite

---

## 🚀 Deploy on Railway (Easiest - Free)

1. Fork or push this code to GitHub

2. Go to https://railway.app → **New Project → Deploy from GitHub**

3. Add these **Environment Variables**:
   ```
   API_ID      = your_api_id        # from my.telegram.org
   API_HASH    = your_api_hash      # from my.telegram.org
   BOT_TOKEN   = your_bot_token     # from @BotFather
   ```

4. Railway will auto-detect nixpacks.toml and install FFmpeg

5. Deploy! Bot goes live in ~2 minutes ✅

---

## 💻 Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Install FFmpeg
# Ubuntu/Debian:
sudo apt install ffmpeg
# macOS:
brew install ffmpeg
# Windows: download from https://ffmpeg.org/download.html

# Edit .env with your credentials
cp .env .env.local  # fill in values

# Run
python bot.py
```

---

## 📁 File Structure

```
video_compress_bot/
├── bot.py          ← main bot logic
├── config.py       ← environment config
├── database.py     ← SQLite user settings
├── requirements.txt
├── Procfile        ← for Railway/Render
├── nixpacks.toml   ← installs FFmpeg on Railway
└── .env            ← credentials (never commit this!)
```

---

## 🔑 Getting Credentials

| Credential | Where to get |
|------------|-------------|
| `API_ID` & `API_HASH` | https://my.telegram.org → App API |
| `BOT_TOKEN` | @BotFather on Telegram → /newbot |

---

## ⚙️ Bot Commands

| Command | Description |
|---------|-------------|
| /start | Welcome message |
| /settings | Open settings panel |
| /help | Usage guide |

Send any video → bot compresses with your settings automatically!
