import os
import logging
import asyncio
from datetime import datetime
import json
import hashlib
import base64
import threading

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiohttp import web

# ---------------- CONFIG (ENV) ----------------

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("FastFileStreamBot")

# Ye 4 cheeze env se aayengi (local pe set karo, Railway pe Variables me)
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

FQDN = "0.0.0.0"
PORT = int(os.getenv("PORT", "8080"))  # Railway yahi set karega

# PUBLIC_BASE ko env se lo: e.g. local pe http://localhost:8080
# Railway pe: https://<your-app>.up.railway.app
PUBLIC_BASE = os.getenv("PUBLIC_BASE", "filestream-bot-production.up.railway.app:8080").rstrip("/")

# /clean command ke liye owner
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

if not (API_ID and API_HASH and BOT_TOKEN):
    log.error("API_ID / API_HASH / BOT_TOKEN missing in env!")
    raise SystemExit("Set API_ID, API_HASH, BOT_TOKEN env variables.")

app = Client("FastFileStreamBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

STORAGE_FILE = "files.json"
if not os.path.exists(STORAGE_FILE):
    with open(STORAGE_FILE, "w") as f:
        json.dump({}, f)


# ---------------- UTILS ----------------

def load_files():
    with open(STORAGE_FILE, "r") as f:
        return json.load(f)


def save_files(files):
    with open(STORAGE_FILE, "w") as f:
        json.dump(files, f)


def short_id(file_unique_id: str) -> str:
    h = hashlib.md5(file_unique_id.encode()).digest()[:6]
    return base64.urlsafe_b64encode(h).decode()[:6]


def human_size(size: int) -> str:
    if not size or size <= 0:
        return "Unknown"
    s = float(size)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if s < 1024:
            return f"{s:.2f} {unit}"
        s /= 1024
    return f"{s:.2f} PB"


def store_file_from_message(msg: Message):
    """Create/Update entry in files.json from a Pyrogram Message."""
    media = msg.document or msg.video or msg.audio or msg.photo or msg.video_note or msg.voice
    if not media:
        return None

    fid = media.file_unique_id
    sid = short_id(fid)

    name = getattr(media, "file_name", None) or "file"
    size = getattr(media, "file_size", 0)
    name = name.replace(" ", "_")

    files = load_files()
    files[fid] = {
        "sid": sid,
        "name": name,
        "size": size,
        "time": str(datetime.now()),
        "chat_id": msg.chat.id,
        "msg_id": msg.id,
    }
    save_files(files)
    return files[fid]


def find_file_by_sid(shortid: str):
    files = load_files()
    for fid, data in files.items():
        if data["sid"] == shortid:
            return data
    return None


# ---------------- WEB SERVER (STREAM FROM TELEGRAM) ----------------

async def stream_handler(request: web.Request):
    shortid = request.match_info.get("shortid")
    target = find_file_by_sid(shortid)

    if not target:
        return web.Response(status=404, text="Link not found or expired")

    chat_id = target["chat_id"]
    msg_id = target["msg_id"]
    name = target["name"]
    size = target.get("size", 0)

    range_header = request.headers.get("Range")
    start = 0
    if range_header:
        try:
            start_str = range_header.split("=")[1].split("-")[0]
            start = int(start_str)
        except Exception:
            start = 0

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": "application/octet-stream",
        "Content-Disposition": f'inline; filename="{name}"',
    }

    if range_header and size:
        headers["Content-Range"] = f"bytes {start}-{size-1}/{size}"

    resp = web.StreamResponse(
        status=206 if range_header else 200,
        headers=headers,
    )

    await resp.prepare(request)

    async with app:
        msg = await app.get_messages(chat_id, msg_id)
        media = msg.document or msg.video or msg.audio or msg.photo or msg.video_note or msg.voice

        async for chunk in app.stream_media(
            msg,
            offset=start,
            limit=None,
            block_size=1024 * 1024,
        ):
            await resp.write(chunk)

    await resp.write_eof()
    return resp


async def web_server():
    aio_app = web.Application()
    aio_app.router.add_get("/s/{shortid}", stream_handler)
    aio_app.router.add_get("/d/{shortid}", stream_handler)
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, FQDN, PORT)
    await site.start()
    log.info(f"🚀 Public stream server on http://{FQDN}:{PORT}/s/SHORTID")


def start_web():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(web_server())
    loop.run_forever()


web_thread = threading.Thread(target=start_web, daemon=True)
web_thread.start()


# ---------------- BOT HANDLERS ----------------

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    await message.reply(
        "**🎉 Fast FileStream Bot**\n\n"
        "📤 Send any **file / video / photo**\n"
        "⚡ Get **instant public link** (no local download wait)\n\n"
        "**Works in:** Browser, VLC, IDM, MX Player\n"
        "**No login, just share links.**",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📚 How to use", callback_data="help")]]
        ),
    )


@app.on_message(filters.media & filters.private)
async def handle_media(client: Client, message: Message):
    wait_msg = await message.reply("⏳ Generating instant link...")

    meta = store_file_from_message(message)
    if not meta:
        await wait_msg.edit("❌ Unsupported media.")
        return

    sid = meta["sid"]
    name = meta["name"]
    size = meta["size"]

    stream_link = f"{PUBLIC_BASE}/s/{sid}"
    download_link = f"{PUBLIC_BASE}/d/{sid}"

    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎥 Stream", url=stream_link)],
            [InlineKeyboardButton("⬇️ Download", url=download_link)],
            [InlineKeyboardButton("➕ More Files", callback_data="more")],
        ]
    )

    caption = f"""
**✅ File Ready Instantly!**

📁 **{name}**
📊 **{human_size(size)}**

🔗 **Stream:** `{stream_link}`
⬇️ **Download:** `{download_link}`

✨ **Public - Share anywhere, no login!**
""".strip()

    await wait_msg.delete()
    await message.reply(caption, reply_markup=kb)


# -------- /fdl command (reply to existing message) --------

@app.on_message(filters.command("fdl") & filters.private)
async def fdl_cmd(client: Client, message: Message):
    if not message.reply_to_message:
        await message.reply("Reply to a file/message with /fdl ❌")
        return

    reply = message.reply_to_message
    media = reply.document or reply.video or reply.audio or reply.photo or reply.video_note or reply.voice
    if not media:
        await message.reply("❌ Only Video/Audio/Files/Photos supported")
        return

    wait_msg = await message.reply("⏳ Generating link from replied message...")

    meta = store_file_from_message(reply)
    if not meta:
        await wait_msg.edit("❌ Failed to read media.")
        return

    sid = meta["sid"]
    name = meta["name"]
    size = meta["size"]

    stream_link = f"{PUBLIC_BASE}/s/{sid}"
    download_link = f"{PUBLIC_BASE}/d/{sid}"

    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📥 Download", url=download_link)],
            [InlineKeyboardButton("▶️ Stream", url=stream_link)],
        ]
    )

    text = (
        f"**File Name:** `{name}`\n"
        f"**Size:** `{human_size(size)}`\n\n"
        f"**Download:** `{download_link}`\n"
        f"**Stream:** `{stream_link}`\n\n"
        f"Open in any browser or player."
    )

    await wait_msg.edit(text, reply_markup=kb, disable_web_page_preview=True)


# ------------- CALLBACKS + CLEAN -------------

@app.on_callback_query(filters.regex(r"help|more"))
async def cb_handler(client: Client, query):
    if query.data == "help":
        await query.answer(
            "Send file → Get link instantly → Open in browser/VLC.\n"
            "Links are public; share with anyone.",
            show_alert=True,
        )
    else:
        await query.answer("Send more files! 😊", show_alert=True)


@app.on_message(filters.command("clean") & filters.user(OWNER_ID))
async def clean(client: Client, message: Message):
    files = load_files()
    count = len(files)
    files.clear()
    save_files(files)
    await message.reply(f"🧹 Cleared {count} saved links (Telegram messages stay safe)")


# ---------------- MAIN ----------------

if __name__ == "__main__":
    print("🤖 Starting FAST FileStreamBot...")
    print(f"🌐 Example link will look like: {PUBLIC_BASE}/s/ABC123")
    app.run()
