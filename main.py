import os
import time
import asyncio
import aiofiles
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pyrogram import Client, filters

# ===== CONFIG =====
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
BASE_URL = os.getenv("BASE_URL")

UPLOADASH_API = os.getenv("UPLOADASH_API")  # 🔐 put your NEW key here

CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

app = FastAPI()

bot = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

files_db = {}

# ===== START =====
@app.on_event("startup")
async def startup():
    await bot.start()

@app.on_event("shutdown")
async def shutdown():
    await bot.stop()

# ===== UPLOADASH FUNCTION =====
def upload_to_uploadash(file_path):
    url = "https://uploadash.com/api/upload"

    with open(file_path, "rb") as f:
        files = {"file": f}
        headers = {"Authorization": UPLOADASH_API}

        res = requests.post(url, files=files, headers=headers)
        data = res.json()

        return data.get("link")

# ===== CACHE DOWNLOAD =====
async def cache_file(msg, path):
    if os.path.exists(path):
        return
    await bot.download_media(msg, file_name=path)

# ===== BOT =====
@bot.on_message(filters.private & filters.media)
async def handle_file(client, message):

    msg = await message.copy(CHANNEL_ID)

    size = 0
    if msg.document:
        size = msg.document.file_size
    elif msg.video:
        size = msg.video.file_size

    path = f"{CACHE_DIR}/{msg.id}"

    files_db[msg.id] = {
        "path": path,
        "expiry": time.time() + 3600 * 6
    }

    # ===== SMALL FILE → UPLOADASH =====
    if size < 100 * 1024 * 1024:  # <100MB
        await bot.download_media(msg, file_name=path)

        try:
            link = upload_to_uploadash(path)
            if link:
                await message.reply(f"⚡ Fast Link:\n{link}")
                return
        except:
            pass

    # ===== BIG FILE → TELEGRAM CACHE =====
    asyncio.create_task(cache_file(msg, path))

    link = f"{BASE_URL}/file/{msg.id}"
    await message.reply(f"⚡ {link}")

# ===== STREAM =====
async def stream_file(path):
    async with aiofiles.open(path, "rb") as f:
        while True:
            chunk = await f.read(1024 * 1024)
            if not chunk:
                break
            yield chunk

# ===== ROUTE =====
@app.get("/file/{file_id}")
async def serve(file_id: int):

    if file_id not in files_db:
        raise HTTPException(404)

    data = files_db[file_id]

    if time.time() > data["expiry"]:
        raise HTTPException(403)

    path = data["path"]

    # cache hit
    if os.path.exists(path):
        return StreamingResponse(stream_file(path))

    # fallback Telegram stream
    msg = await bot.get_messages(CHANNEL_ID, file_id)

    async def tg_stream():
        async for chunk in bot.stream_media(msg):
            yield chunk

    return StreamingResponse(tg_stream())
