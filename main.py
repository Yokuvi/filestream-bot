import os
import time
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from pyrogram import Client, filters

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")

app = FastAPI()

bot = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

links_db = {}  # file_id: {expiry, size}

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
    elif msg.audio:
        size = msg.audio.file_size

    expiry = 3600
    links_db[msg.id] = {
        "expiry": time.time() + expiry,
        "size": size
    }

    link = f"{BASE_URL}/file/{msg.id}"

    await message.reply(f"⚡ Link:\n{link}")

# ===== STATUS PAGE =====
@app.get("/file/{file_id}", response_class=HTMLResponse)
async def status_page(file_id: int):

    if file_id not in links_db:
        return "Invalid link"

    size = links_db[file_id]["size"]

    # fake ETA logic (approx)
    speed = 5 * 1024 * 1024  # 5MB/s assumption
    eta = int(size / speed)

    return f"""
    <html>
    <head>
        <title>Preparing Download</title>
    </head>
    <body style="background:#111;color:#fff;text-align:center;margin-top:100px;font-family:sans-serif;">
        <h2>⏳ Preparing your file...</h2>
        <p>Estimated time: {eta} seconds</p>
        <p>File size: {round(size/1024/1024,2)} MB</p>
        <p>Please wait...</p>

        <script>
            setTimeout(function(){{
                window.location.href = "/download/{file_id}";
            }}, 2000);
        </script>
    </body>
    </html>
    """

# ===== ACTUAL DOWNLOAD =====
@app.get("/download/{file_id}")
async def stream(file_id: int):

    if file_id not in links_db:
        raise HTTPException(404)

    if time.time() > links_db[file_id]["expiry"]:
        raise HTTPException(403, "Link expired")

    msg = await bot.get_messages(CHANNEL_ID, file_id)

    async def generator():
        async for chunk in bot.stream_media(msg):
            yield chunk

    return StreamingResponse(
        generator(),
        headers={
            "Content-Disposition": "attachment"
        }
    )
