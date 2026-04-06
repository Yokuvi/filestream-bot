import os
import asyncio
from flask import Flask, Response
from pyrogram import Client, filters
from pyrogram.types import Message

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
BASE_URL = os.getenv("BASE_URL")

app = Flask(__name__)

tg = Client(
    "bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=10
)

@tg.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def handle_file(client: Client, message: Message):
    msg = await message.copy(CHANNEL_ID)
    link = f"{BASE_URL}/file/{msg.id}"

    await message.reply(f"🔗 {link}")

@app.route("/file/<int:file_id>")
def stream(file_id):
    async def generator():
        msg = await tg.get_messages(CHANNEL_ID, file_id)
        async for chunk in tg.stream_media(msg):
            yield chunk

    return Response(generator(), headers={
        "Content-Disposition": "attachment"
    })

def run_bot():
    tg.run()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(asyncio.to_thread(run_bot))
    app.run(host="0.0.0.0", port=5000)
