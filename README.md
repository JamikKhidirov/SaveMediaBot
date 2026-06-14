# SaveMediaBot 🤖

**Telegram bot for downloading media from YouTube, Instagram, TikTok, VK, Twitter/X and other platforms.**

---

## Features ✨

| Feature | Description |
|---------|-------------|
| **Multi-platform** | YouTube, Instagram, TikTok, VK, Twitter/X, and 1000+ sites via yt-dlp |
| **YouTube Shorts** | Auto-detection of Shorts with optimized quality selection |
| **Format selection** | Inline buttons: video or audio (MP3 192kbps) |
| **Quality choice** | 360p / 480p / 720p / 1080p — pick before downloading |
| **Batch download** | Send multiple links in one message — download all at once |
| **Auto-compression** | Video >50MB is automatically compressed with ffmpeg |
| **Subscription gate** | Require users to subscribe to channels before using the bot |
| **Auto-cleanup** | Files are deleted from disk immediately after sending |
| **Admin panel** | Commands to manage required channels |

---

## Architecture 🏗️

```
SaveMediaBot/
├── bot/
│   ├── __init__.py
│   ├── main.py                    # Entry point, polling
│   ├── config.py                  # BOT_TOKEN, ADMIN_IDS from .env
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py               # /start command
│   │   ├── download.py            # Link handling, format/quality selection, batch download
│   │   └── admin.py               # Admin commands for channel management
│   └── services/
│       ├── __init__.py
│       ├── downloader.py          # yt-dlp wrapper with quality & compression
│       └── subscription.py        # Channel subscription checker
├── data/                          # Runtime data (channels.json)
├── .env                           # Environment variables (not committed)
├── .env.example                   # Environment template
├── requirements.txt
└── .gitignore
```

### Flow

```
User sends link
    │
    ▼
Check subscriptions ──❌──► Show channel list + "✅ I subscribed"
    │                               │
    ✔                               ▼
    │                           User subscribes & clicks button
    ▼                               │
Format selection (Video / Audio)    │
    │                               │
    ▼                               │
[if Video] Quality selection ──back─┘
    │
    ▼
Download via yt-dlp
    │
    ▼
[if video >50MB] Compress with ffmpeg
    │
    ▼
Send file to user
    │
    ▼
Delete file from disk
```

---

## Quick Start 🚀

### 1. Clone & setup

```bash
git clone https://github.com/JamikKhidirov/SaveMediaBot.git
cd SaveMediaBot
python -m venv .venv
```

### 2. Install dependencies

```bash
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux / macOS

pip install -r requirements.txt
```

### 3. Configure

Copy `.env.example` to `.env` and fill in:

```env
BOT_TOKEN=1234567890:ABCdefGHIjklmNOPqrstUVwxyz
ADMIN_IDS=12345678,87654321
```

> `ADMIN_IDS` — comma-separated Telegram user IDs that can manage channels.

### 4. Run

```bash
python -m bot.main
```

---

## Commands 📋

### User commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message with platform list and channel info |
| *(send any link)* | Triggers format selection → quality selection → download |

### Admin commands

| Command | Description |
|---------|-------------|
| `/add_channel @channel` | Add a channel to subscription requirement |
| `/remove_channel @channel` | Remove a channel from subscription requirement |
| `/list_channels` | Show all required channels |

---

## Download flow details 📥

### Single link

1. **Send a URL** — bot detects YouTube, Instagram, TikTok, VK, Twitter/X links
2. **Choose format** — inline buttons: `🎬 Video` or `🎵 Audio (MP3)`
3. **Choose quality** — pick from available resolutions (360p — 1080p) or `🏆 Best`
4. **Auto-download** — file is sent to chat and immediately deleted from server

### Batch download

Send multiple URLs in one message (one per line or separated by spaces). Bot will:
1. Detect all links
2. Ask: download all as video or all as audio
3. Process sequentially with progress indicators
4. Show summary: ✅ success / ❌ failed

### Compression

If a video exceeds **50 MB**, the bot attempts to compress it with **ffmpeg** using `-crf 28`.  
If ffmpeg is not installed, the file is sent as-is with a warning.

---

## Subscription gate 🔒

Admins can require users to subscribe to specific Telegram channels before using the bot:

1. Add channels with `/add_channel @channel_name`
2. When an unsubscribed user sends a link, they see the channel list with subscribe buttons
3. After subscribing, they click `✅ I subscribed` and the bot verifies
4. Once all channels are subscribed, the download proceeds normally

---

## Requirements 📦

- **Python** 3.10+
- **ffmpeg** (optional, for video compression)
- Dependencies (auto-installed via pip):
  - `aiogram>=3.0` — async Telegram Bot framework
  - `yt-dlp>=2024.0` — universal media downloader
  - `python-dotenv>=1.0` — environment file loader

---

## Supported platforms 🌐

| Platform | Video | Audio | Quality selection |
|----------|-------|-------|-------------------|
| YouTube | ✅ | ✅ | ✅ (360p–1080p) |
| YouTube Shorts | ✅ | ✅ | ✅ (up to 600p) |
| Instagram | ✅ | ❌ | ✅ |
| TikTok | ✅ | ❌ | ✅ |
| VK | ✅ | ❌ | ✅ |
| Twitter / X | ✅ | ❌ | ✅ |
| *1000+ others via yt-dlp* | varies | varies | varies |

---

## License 📄

MIT
