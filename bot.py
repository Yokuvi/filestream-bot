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
import aiofiles

# ---------------- CONFIG (ENV) ----------------

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("FastFileStreamBot")

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

FQDN = "0.0.0.0"
PORT = int(os.getenv("PORT", "8080"))  # Railway will set this

PUBLIC_BASE = os.getenv("PUBLIC_BASE", "http://localhost:8080").rstrip("/")

OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# storage limit: 500 MB
MAX_STORAGE_BYTES = 500 * 1024 * 1024

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


def build_meta_from_message(msg: Message):
    media = (
        msg.document
        or msg.video
        or msg.animation   # GIF
        or msg.audio
        or msg.photo
        or msg.video_note
        or msg.voice
    )
    if not media:
        return None

    fid = media.file_unique_id
    sid = short_id(fid)

    name = "file"
    size = 0

    if msg.document:
        # ZIP, RAR, PDF, APK, etc. come as document
        name = msg.document.file_name or "file"
        size = msg.document.file_size or 0
    elif msg.video:
        name = getattr(msg.video, "file_name", None) or "video.mp4"
        size = msg.video.file_size or 0
    elif msg.animation:
        name = getattr(msg.animation, "file_name", None) or "animation.gif"
        size = msg.animation.file_size or 0
    elif msg.audio:
        name = getattr(msg.audio, "file_name", None) or "audio"
        size = msg.audio.file_size or 0
    elif msg.photo:
        ph = msg.photo[-1]
        name = "photo.jpg"
        size = ph.file_size or 0
    elif msg.video_note:
        name = "video_note.mp4"
        size = msg.video_note.file_size or 0
    elif msg.voice:
        name = "voice.ogg"
        size = msg.voice.file_size or 0

    name = name.replace(" ", "_")

    os.makedirs("files", exist_ok=True)
    file_path = os.path.join("files", f"{fid}")

    return {
        "fid": fid,
        "sid": sid,
        "name": name,
        "size": int(size),
        "path": file_path,
        "chat_id": msg.chat.id,
        "msg_id": msg.id,
    }


def find_file_by_sid(shortid: str):
    files = load_files()
    for fid, data in files.items():
        if data["sid"] == shortid:
            return data
    return None


def total_storage_size(files: dict) -> int:
    total = 0
    for data in files.values():
        p = data.get("path")
        if p and os.path.exists(p):
            try:
                total += os.path.getsize(p)
            except Exception:
                pass
    return total


def enforce_storage_limit(files: dict, max_bytes: int = MAX_STORAGE_BYTES) -> dict:
    # delete oldest files until total size <= max_bytes
    current = total_storage_size(files)
    if current <= max_bytes:
        return files

    # sort by time (oldest first)
    items = sorted(
        files.items(),
        key=lambda kv: kv[1].get("time", "")
    )

    for fid, data in items:
        path = data.get("path")
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
        del files[fid]
        current = total_storage_size(files)
        if current <= max_bytes:
            break

    save_files(files)
    log.info("Storage limit enforced. Current size: %s", human_size(current))
    return files


# ---------------- WEB SERVER (SERVE LOCAL FILES) ----------------

async def stream_handler(request: web.Request):
    shortid = request.match_info.get("shortid")
    all_files = load_files()

    target = None
    for fid, data in all_files.items():
        if data["sid"] == shortid:
            target = data
            break

    if not target:
        return web.Response(status=404, text="Link not found or expired")

    file_path = target.get("path")
    name = target["name"]
    size = int(target.get("size", 0) or 0)

    if not file_path or not os.path.exists(file_path):
        return web.Response(status=404, text="File not found (maybe cleaned)")

    range_header = request.headers.get("Range")
    start = 0
    end = size - 1 if size > 0 else None

    if range_header and size > 0:
        try:
            ranges = range_header.strip().split("=")[1]
            start_str, end_str = ranges.split("-")
            start = int(start_str) if start_str else 0
            if end_str:
                end = int(end_str)
        except Exception:
            start = 0

    chunk_size = 1024 * 1024

    async def file_iter():
        nonlocal start
        async with aiofiles.open(file_path, "rb") as f:
            await f.seek(start)
            remaining = None
            if end is not None:
                remaining = end - start + 1
            while True:
                read_size = chunk_size if remaining is None else min(chunk_size, remaining)
                data = await f.read(read_size)
                if not data:
                    break
                if remaining is not None:
                    remaining -= len(data)
                    if remaining <= 0:
                        yield data
                        break
                yield data

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": "application/octet-stream",
        "Content-Disposition": f'inline; filename="{name}"',
    }

    status = 200
    body = file_iter()

    if range_header and size > 0 and end is not None:
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        headers["Content-Length"] = str(end - start + 1)
    elif size > 0:
        headers["Content-Length"] = str(size)

    resp = web.Response(status=status, headers=headers, body=body)
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
        "📤 Send any **file / video / photo / GIF / ZIP / RAR**\n"
        "⚡ Get **public stream + download links**\n\n"
        "Storage auto-cleans when it exceeds 500 MB.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📚 How to use", callback_data="help")]]
        ),
    )


async def save_file_and_register(msg: Message, meta: dict):
    fid = meta["fid"]
    sid = meta["sid"]
    name = meta["name"]
    size = meta["size"]
    path = meta["path"]

    # download file
    await app.download_media(msg, file_name=path)

    files = load_files()
    files[fid] = {
        "sid": sid,
        "name": name,
        "size": size,
        "time": str(datetime.now()),
        "chat_id": msg.chat.id,
        "msg_id": msg.id,
        "path": path,
    }
    # enforce 500MB limit
    files = enforce_storage_limit(files, MAX_STORAGE_BYTES)
    save_files(files)

    return sid, name, size


@app.on_message(filters.media & filters.private)
async def handle_media(client: Client, message: Message):
    wait_msg = await message.reply("⏳ Downloading & preparing your file...")

    meta = build_meta_from_message(message)
    if not meta:
        await wait_msg.edit("❌ Unsupported media.")
        return

    try:
        sid, name, size = await save_file_and_register(message, meta)

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
**✅ File Ready!**

📁 **{name}**
📊 **{human_size(size)}**

🔗 **Stream:** `{stream_link}`
⬇️ **Download:** `{download_link}`

✨ Storage auto-cleans when over 500 MB.
""".strip()

        await wait_msg.delete()
        await message.reply(caption, reply_markup=kb)
    except Exception as e:
        await wait_msg.edit(f"❌ Error while preparing file: {e}")


@app.on_message(filters.command("fdl") & filters.private)
async def fdl_cmd(client: Client, message: Message):
    if not message.reply_to_message:
        await message.reply("Reply to a file/message with /fdl ❌")
        return

    reply = message.reply_to_message
    media = (
        reply.document
        or reply.video
        or reply.animation
        or reply.audio
        or reply.photo
        or reply.video_note
        or reply.voice
    )
    if not media:
        await message.reply("❌ Only Video/Audio/Files/Photos/GIFs supported")
        return

    wait_msg = await message.reply("⏳ Downloading & preparing your file...")

    meta = build_meta_from_message(reply)
    if not meta:
        await wait_msg.edit("❌ Failed to read media.")
        return

    try:
        sid, name, size = await save_file_and_register(reply, meta)

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
            f"Storage auto-cleans when over 500 MB."
        )

        await wait_msg.edit(text, reply_markup=kb, disable_web_page_preview=True)
    except Exception as e:
        await wait_msg.edit(f"❌ Error while preparing file: {e}")


@app.on_callback_query(filters.regex(r"help|more"))
async def cb_handler(client: Client, query):
    if query.data == "help":
        await query.answer(
            "Send file → Bot downloads & creates links → Open in browser/VLC.\n"
            "Old files are deleted automatically when storage > 500 MB.",
            show_alert=True,
        )
    else:
        await query.answer("Send more files! 😊", show_alert=True)


@app.on_message(filters.command("clean") & filters.user(OWNER_ID))
async def clean(client: Client, message: Message):
    files = load_files()
    count = len(files)
    for fid, data in list(files.items()):
        path = data.get("path")
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
        del files[fid]
    save_files(files)
    await message.reply(f"🧹 Manually cleared {count} files & links.")


# ---------------- MAIN ----------------

if __name__ == "__main__":
    print("🤖 Starting FAST FileStreamBot...")
    print(f"🌐 Example link will look like: {PUBLIC_BASE}/s/ABC123")
    app.run()
