import os
import time
import asyncio
import aiofiles
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pyrogram import Client, filters

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
BASE_URL = os.getenv("BASE_URL")

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

# ===== BACKGROUND CACHE =====
async def cache_file(msg, path):
    if os.path.exists(path):
        return
    try:
        await bot.download_media(msg, file_name=path)
    except:
        pass

# ===== BOT =====
@bot.on_message(filters.private & filters.media)
async def handle_file(client, message):

    msg = await message.copy(CHANNEL_ID)
    path = f"{CACHE_DIR}/{msg.id}"

    files_db[msg.id] = {
        "path": path,
        "expiry": time.time() + 3600 * 6
    }

    # 🔥 preload cache
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

    # ✅ If cached → instant
    if os.path.exists(path):
        return StreamingResponse(
            stream_file(path),
            headers={"Content-Disposition": "attachment"}
        )

    # ❌ If not cached → fallback to Telegram stream
    msg = await bot.get_messages(CHANNEL_ID, file_id)

    async def tg_stream():
        async for chunk in bot.stream_media(msg):
            yield chunk

    return StreamingResponse(
        tg_stream(),
        headers={"Content-Disposition": "attachment"}
    )
