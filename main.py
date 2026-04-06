import os
import threading
import asyncio
from flask import Flask, send_file
from pyrogram import Client, filters
from pyrogram.types import Message

# ===== CONFIG =====
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

# ===== BOT =====
@tg.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply("🔥 Bot ready. Send or forward file.")

@tg.on_message(filters.private)
async def handle_file(client: Client, message: Message):

    file = message.document or message.video or message.audio

    # DIRECT FILE
    if file:
        msg = await message.copy(CHANNEL_ID)

    # FORWARDED FILE (TYPE 1 - normal forward)
    elif message.forward_from_chat and message.forward_from_message_id:
        try:
            msg = await client.copy_message(
                chat_id=CHANNEL_ID,
                from_chat_id=message.forward_from_chat.id,
                message_id=message.forward_from_message_id
            )
        except:
            return  # ignore silently (no spam)

    # FORWARDED FILE (TYPE 2 - hidden origin / protected)
    elif message.document or message.video or message.audio:
        try:
            msg = await message.copy(CHANNEL_ID)
        except:
            return

    else:
        return  # no spam reply

    link = f"{BASE_URL}/file/{msg.id}"

    await message.reply(f"⚡ Download:\n{link}")

# ===== DOWNLOAD ROUTE =====
@app.route("/file/<int:file_id>")
def download(file_id):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def fetch():
        msg = await tg.get_messages(CHANNEL_ID, file_id)
        path = await tg.download_media(msg)
        return path

    try:
        file_path = loop.run_until_complete(fetch())
    except Exception as e:
        return f"ERROR: {str(e)}", 500

    return send_file(file_path, as_attachment=True)

# ===== RUN =====
def run_flask():
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    tg.run()
