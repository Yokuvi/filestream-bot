# Fast Telegram FileStream Bot

A simple Telegram bot that turns files and videos into **instant streaming and direct download links**.

## Features

- Send any **file / video / photo** and get:
  - Streaming link
  - Direct download link
- `/fdl` command: reply to an existing file to generate links again.
- Streams directly from Telegram (no local file storage needed).
- Works locally and on Railway (free hosting).

## Requirements

- Python 3.10+
- Telegram Bot Token (from @BotFather)
- Telegram API ID & API Hash (from https://my.telegram.org)

Python dependencies:

```bash
pip install -r requirements.txt
```

`requirements.txt`:

```txt
pyrogram==2.0.106
tgcrypto
aiohttp
aiofiles
```

## Environment Variables

Set these before running:

```bash
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
OWNER_ID=your_telegram_user_id   # used for /clean command
PUBLIC_BASE=https://your-domain-or-railway-url
```

Examples:

- Local: `PUBLIC_BASE=http://localhost:8080`
- Railway: `PUBLIC_BASE=https://your-app-name.up.railway.app`

## Run Locally

```bash
python bot.py
```

Then in Telegram:

- Start the bot with `/start`.
- Send any file/video.
- The bot replies with:
  - Stream link
  - Direct download link
- Or reply to a file with `/fdl` to regenerate the links.

## Deploy on Railway

1. Push this project to GitHub.
2. On Railway:
   - Create a **New Project → Deploy from GitHub**.
   - Set environment variables: `API_ID`, `API_HASH`, `BOT_TOKEN`, `OWNER_ID`, `PUBLIC_BASE`.
   - Set **Start Command** to: `python bot.py`.
3. Use the Railway URL as `PUBLIC_BASE`.

Your bot will then be online with a proper HTTPS URL for all links.