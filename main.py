import os
import threading
import asyncio
from flask import Flask, send_file
from pyrogram import Client, filters

# ===== CONFIG =====
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
BASE_URL = os.getenv("BASE_URL")

app = Flask(__name__)

bot = Client(
    "bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ===== BOT =====
@bot.on_message(filters.private)
async def handle(client, message):

    # ignore commands
    if message.text and message.text.startswith("/"):
        await message.reply("Send file or forward file.")
        return

    file = message.document or message.video or message.audio

    try:
        if file:
            msg = await message.copy(CHANNEL_ID)

        elif message.forward_from_chat and message.forward_from_message_id:
            msg = await client.copy_message(
                chat_id=CHANNEL_ID,
                from_chat_id=message.forward_from_chat.id,
                message_id=message.forward_from_message_id
            )
        else:
            return

        link = f"{BASE_URL}/file/{msg.id}"
        await message.reply(link)

    except Exception as e:
        await message.reply(f"Error: {str(e)}")

# ===== DOWNLOAD =====
@app.route("/file/<int:file_id>")
def download(file_id):

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def get_file():
        msg = await bot.get_messages(CHANNEL_ID, file_id)
        file_path = await bot.download_media(msg)
        return file_path

    try:
        file_path = loop.run_until_complete(get_file())
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        return f"ERROR: {str(e)}", 500

# ===== RUN =====
def run_web():
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    bot.run()
