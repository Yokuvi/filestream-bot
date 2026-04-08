import os
import time
import asyncio
import aiofiles
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pyrogram import Client, filters

# ===== CONFIG =====
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
BASE_URL = os.getenv("BASE_URL")

CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

app = FastAPI()

bot = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

files_db = {}  # file_id: {expiry, size, path}

# ===== START =====
@app.on_event("startup")
async def startup():
    await bot.start()

@app.on_event("shutdown")
async def shutdown():
    await bot.stop()

# ===== BOT =====
@bot.on_message(filters.private & filters.media)
async def handle_file(client, message):

    msg = await message.copy(CHANNEL_ID)

    size = 0
    if msg.document:
        size = msg.document.file_size
    elif msg.video:
        size = msg.video.file_size

    files_db[msg.id] = {
        "expiry": time.time() + 3600 * 12,
        "size": size,
        "path": f"{CACHE_DIR}/{msg.id}"
    }

    link = f"{BASE_URL}/file/{msg.id}"
    await message.reply(f"⚡ {link}")

# ===== BACKGROUND PREFETCH =====
async def prefetch(msg, path):
    if os.path.exists(path):
        return
    await bot.download_media(msg, file_name=path)

# ===== MULTI-CHUNK STREAM =====
async def stream_file(path, start=0, end=None):
    async with aiofiles.open(path, "rb") as f:
        await f.seek(start)
        remaining = end - start if end else None

        while True:
            chunk = await f.read(2 * 1024 * 1024)  # 2MB chunks
            if not chunk:
                break

            if remaining:
                if len(chunk) > remaining:
                    chunk = chunk[:remaining]
                remaining -= len(chunk)

            yield chunk

# ===== ROUTE =====
@app.get("/file/{file_id}")
async def serve(file_id: int, request: Request):

    if file_id not in files_db:
        raise HTTPException(404)

    data = files_db[file_id]

    if time.time() > data["expiry"]:
        raise HTTPException(403, "Expired")

    msg = await bot.get_messages(CHANNEL_ID, file_id)
    path = data["path"]

    # ===== PRE-WARM =====
    if not os.path.exists(path):
        asyncio.create_task(prefetch(msg, path))

    # wait a bit to avoid empty stream
    for _ in range(5):
        if os.path.exists(path):
            break
        await asyncio.sleep(0.5)

    if not os.path.exists(path):
        raise HTTPException(503, "Preparing file, retry in a few seconds")

    file_size = os.path.getsize(path)
    range_header = request.headers.get("range")

    if range_header:
        start, end = range_header.replace("bytes=", "").split("-")
        start = int(start)
        end = int(end) if end else file_size - 1

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
            "Content-Type": "application/octet-stream"
        }

        return StreamingResponse(
            stream_file(path, start, end + 1),
            status_code=206,
            headers=headers
        )

    return StreamingResponse(
        stream_file(path),
        headers={
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes"
        }
    )
