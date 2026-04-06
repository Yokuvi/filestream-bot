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
    "bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ========= BOT =========
@tg.on_message(filters.private & filters.command("start"))
async def start_cmd(client, message):
    await message.reply(
        "🔥 Send me any file\n\nI will give you a FAST direct download link 😎"
    )

@tg.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def handle_file(client: Client, message: Message):
    msg = await message.copy(CHANNEL_ID)

    link = f"{BASE_URL}/file/{msg.id}"

    await message.reply(
        f"✅ Uploaded successfully!\n\n⚡ Fast Link:\n{link}"
    )

# ========= STREAM =========
@app.route("/file/<int:file_id>")
def stream(file_id):

    async def generate():
        msg = await tg.get_messages(CHANNEL_ID, file_id)
        async for chunk in tg.stream_media(msg):
            yield chunk

    return Response(generate(), headers={
        "Content-Disposition": "attachment"
    })

# ========= MAIN =========
async def main():
    await tg.start()

    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    asyncio.run(main())
