import os
import time
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pyrogram import Client, filters

# ===== CONFIG =====
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")  # public username recommended
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")

app = FastAPI()

bot = Client(
    "bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=10
)

# ===== IN-MEM DB =====
links_db = {}  # {message_id: expiry_timestamp}

# ===== STARTUP / SHUTDOWN =====
@app.on_event("startup")
async def startup_event():
    # ensure event loop exists
    loop = asyncio.get_event_loop()
    if not loop.is_running():
        asyncio.set_event_loop(asyncio.new_event_loop())
    await bot.start()

@app.on_event("shutdown")
async def shutdown_event():
    await bot.stop()

# ===== BOT =====
@bot.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply("Send file → get fast download link ⚡")

@bot.on_message(filters.private & filters.media)
async def handle_file(client, message):
    try:
        # copy to channel
        msg = await message.copy(CHANNEL_ID)

        # get file size
        size = 0
        if msg.document:
            size = msg.document.file_size
        elif msg.video:
            size = msg.video.file_size
        elif msg.audio:
            size = msg.audio.file_size

        # ===== TIMER =====
        if size < 50 * 1024 * 1024:
            expiry = 3600 * 24
        elif size < 500 * 1024 * 1024:
            expiry = 3600 * 6
        else:
            expiry = 3600 * 1

        expire_time = time.time() + expiry
        links_db[msg.id] = expire_time

        link = f"{BASE_URL}/file/{msg.id}"

        await message.reply(
            f"⚡ Link:\n{link}\n⏳ Expires in {expiry//3600}h"
        )

    except Exception as e:
        await message.reply(f"Error: {str(e)}")

# ===== STREAM =====
@app.get("/file/{file_id}")
async def stream(file_id: int):

    # check valid
    if file_id not in links_db:
        raise HTTPException(status_code=404, detail="Invalid link")

    if time.time() > links_db[file_id]:
        raise HTTPException(status_code=403, detail="Link expired")

    try:
        msg = await bot.get_messages(CHANNEL_ID, file_id)

        async def file_stream():
            async for chunk in bot.stream_media(msg):
                yield chunk

        return StreamingResponse(
            file_stream(),
            headers={
                "Content-Disposition": "attachment",
                "Content-Type": "application/octet-stream"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
