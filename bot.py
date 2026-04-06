import os
import asyncio
from flask import Flask, Response
from pyrogram import Client, filters
from pyrogram.types import Message

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
BASE_URL = os.getenv("BASE_URL", "")

app = Flask(__name__)

tg = Client(
    "bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@tg.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def handle_file(client: Client, message: Message):
    msg = await message.copy(CHANNEL_ID)
    link = f"{BASE_URL}/file/{msg.id}"
    await message.reply(f"🔗 {link}")

@app.route("/file/<int:file_id>")
def stream(file_id):
    async def generator():
        try:
            msg = await tg.get_messages(CHANNEL_ID, file_id)
            async for chunk in tg.stream_media(msg):
                yield chunk
        except Exception as e:
            print(e)

    return Response(generator(), headers={
        "Content-Disposition": "attachment"
    })

def start_bot():
    tg.run()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(asyncio.to_thread(start_bot))

    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
