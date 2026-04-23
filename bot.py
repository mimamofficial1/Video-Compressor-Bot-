import os
import time
import asyncio
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from config import Config
from database import Database

app = Client(
    "VideoCompressorBot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
)

db = Database()

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def human_size(num):
    for unit in ["B", "KB", "MB", "GB"]:
        if num < 1024:
            return f"{num:.2f} {unit}"
        num /= 1024
    return f"{num:.2f} TB"

def progress_bar(current, total):
    pct = (current / total) * 100 if total else 0
    filled = int(pct / 10)
    bar = "█" * filled + "░" * (10 - filled)
    return f"[{bar}] {pct:.1f}%"

async def update_progress(msg, action, current, total, start_time):
    elapsed = time.time() - start_time
    speed = current / elapsed if elapsed > 0 else 0
    eta = (total - current) / speed if speed > 0 else 0
    text = (
        f"**{action}**\n\n"
        f"{progress_bar(current, total)}\n\n"
        f"📦 **Size:** {human_size(current)} / {human_size(total)}\n"
        f"⚡ **Speed:** {human_size(speed)}/s\n"
        f"⏱ **ETA:** {int(eta)}s"
    )
    try:
        await msg.edit_text(text)
    except FloodWait as e:
        await asyncio.sleep(e.value)

def settings_text(s):
    return (
        f"**⚙️ Your Settings**\n\n"
        f"🎞 **Resolution:** `{s['resolution']}`\n"
        f"🎬 **Codec:** `{s['codec']}`\n"
        f"🔢 **Bits:** `{s['bits']}`\n"
        f"📊 **CRF:** `{s['crf']}`\n"
        f"📐 **Aspect Ratio:** `{s['aspect']}`\n"
        f"📤 **Upload Mode:** `{s['upload_mode']}`\n"
        f"💧 **Watermark:** `{s['watermark'] or 'None'}`\n"
        f"🏷 **WM Color:** `{s['wm_color']}`\n"
        f"📍 **WM Position:** `{s['wm_pos']}`\n"
        f"📏 **WM Size:** `{s['wm_size']}`\n"
        f"🔇 **Metadata:** `{s['metadata']}`\n"
        f"✏️ **Auto Rename:** `{s['rename'] or 'None'}`\n"
    )

def settings_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎞 Resolution", callback_data="set_res"),
         InlineKeyboardButton("🎬 Codec", callback_data="set_codec")],
        [InlineKeyboardButton("🔢 Bits", callback_data="set_bits"),
         InlineKeyboardButton("📊 CRF", callback_data="set_crf")],
        [InlineKeyboardButton("📐 Aspect Ratio", callback_data="set_aspect"),
         InlineKeyboardButton("📤 Upload Mode", callback_data="set_upload")],
        [InlineKeyboardButton("💧 Watermark", callback_data="set_wm"),
         InlineKeyboardButton("🔇 Metadata", callback_data="set_meta")],
        [InlineKeyboardButton("✏️ Auto Rename", callback_data="set_rename")],
        [InlineKeyboardButton("🔄 Reset All", callback_data="reset_settings"),
         InlineKeyboardButton("❌ Close", callback_data="close")],
    ])

def build_ffmpeg_cmd(input_path, output_path, s, wm_text=None):
    vf_filters = []

    # Resolution
    res_map = {
        "1080p": "1920:1080", "720p": "1280:720",
        "576p": "1024:576",  "480p": "854:480",
        "360p": "640:360",   "240p": "426:240",
        "Original": None,
    }
    scale = res_map.get(s["resolution"])
    if scale:
        vf_filters.append(f"scale={scale}")

    # Aspect ratio
    if s["aspect"] != "None":
        vf_filters.append(f"setdar={s['aspect'].replace(':','/')}")

    # Watermark
    if wm_text and wm_text != "None":
        pos_map = {
            "top":    "x=(w-text_w)/2:y=10",
            "center": "x=(w-text_w)/2:y=(h-text_h)/2",
            "bottom": "x=(w-text_w)/2:y=h-text_h-10",
        }
        pos = pos_map.get(s["wm_pos"], pos_map["bottom"])
        vf_filters.append(
            f"drawtext=text='{wm_text}':fontsize={s['wm_size']}:"
            f"fontcolor={s['wm_color']}:{pos}"
        )

    vf = ",".join(vf_filters) if vf_filters else None

    codec_map = {
        "x264": "libx264", "x265": "libx265",
        "VP9":  "libvpx-vp9", "AV1": "libaom-av1",
    }
    vcodec = codec_map.get(s["codec"], "libx264")

    pix = "yuv420p10le" if s["bits"] == "10 Bits" else "yuv420p"

    cmd = ["ffmpeg", "-i", input_path, "-c:v", vcodec,
           "-crf", str(s["crf"]), "-preset", "fast",
           "-pix_fmt", pix, "-c:a", "aac", "-b:a", "128k"]

    if vf:
        cmd += ["-vf", vf]

    # Strip metadata
    if s["metadata"] == "Disabled":
        cmd += ["-map_metadata", "-1"]

    cmd += [output_path, "-y"]
    return cmd

# ─────────────────────────────────────────────
#  COMMANDS
# ─────────────────────────────────────────────

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message: Message):
    await message.reply_text(
        "👋 **Hi! I'm a Video Compressor Bot**\n\n"
        "Send me any video and I'll compress it while keeping good quality.\n\n"
        "📌 **Commands:**\n"
        "/settings – Configure compression\n"
        "/help – How to use\n\n"
        "🚫 18+ content is **not** allowed.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Settings", callback_data="open_settings"),
             InlineKeyboardButton("❓ Help", callback_data="help")]
        ])
    )

@app.on_message(filters.command("settings") & filters.private)
async def settings_cmd(client, message: Message):
    s = db.get_settings(message.from_user.id)
    await message.reply_text(
        settings_text(s),
        reply_markup=settings_keyboard()
    )

@app.on_message(filters.command("help") & filters.private)
async def help_cmd(client, message: Message):
    await message.reply_text(
        "**📖 How to use:**\n\n"
        "1️⃣ Send a video file (MP4, MKV, AVI, MOV)\n"
        "2️⃣ Bot will auto-compress with your settings\n"
        "3️⃣ Receive compressed file!\n\n"
        "**Tips:**\n"
        "• Lower CRF = better quality but bigger file\n"
        "• x265 gives smaller files than x264\n"
        "• Use /settings to customize everything"
    )

# ─────────────────────────────────────────────
#  VIDEO HANDLER
# ─────────────────────────────────────────────

@app.on_message((filters.video | filters.document) & filters.private)
async def handle_video(client, message: Message):
    file = message.video or message.document
    if not file:
        return

    # Check if it's a video document
    if message.document and not message.document.mime_type.startswith("video/"):
        await message.reply_text("⚠️ Please send a valid video file.")
        return

    if file.file_size > Config.MAX_FILE_SIZE:
        await message.reply_text(
            f"❌ File too large! Max size: {human_size(Config.MAX_FILE_SIZE)}"
        )
        return

    s = db.get_settings(message.from_user.id)
    status_msg = await message.reply_text("⏬ **Downloading your video...**")

    # Download
    start = time.time()
    dl_path = None

    async def dl_progress(current, total):
        await update_progress(status_msg, "⏬ Downloading", current, total, start)

    try:
        dl_path = await message.download(progress=dl_progress)
    except Exception as e:
        await status_msg.edit_text(f"❌ Download failed: {e}")
        return

    orig_size = os.path.getsize(dl_path)
    ext = ".mp4" if s["codec"] in ["x264", "x265"] else ".mkv"
    out_name = s["rename"] if s["rename"] else os.path.splitext(os.path.basename(dl_path))[0]
    out_path = f"downloads/{message.from_user.id}_{out_name}_compressed{ext}"
    os.makedirs("downloads", exist_ok=True)

    # Compress
    await status_msg.edit_text(
        f"🔄 **Compressing...**\n\n"
        f"📁 File: `{os.path.basename(dl_path)}`\n"
        f"⚙️ Settings: `{s['resolution']} | {s['codec']} | CRF {s['crf']}`"
    )

    cmd = build_ffmpeg_cmd(dl_path, out_path, s, s.get("watermark"))
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=Config.FFMPEG_TIMEOUT)
        if proc.returncode != 0:
            err = proc.stderr.decode()[-500:]
            await status_msg.edit_text(f"❌ **FFmpeg error:**\n```{err}```")
            return
    except subprocess.TimeoutExpired:
        await status_msg.edit_text("❌ Compression timed out (file too large or slow server).")
        return
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {e}")
        return

    comp_size = os.path.getsize(out_path)
    saved_pct = ((orig_size - comp_size) / orig_size * 100) if orig_size > 0 else 0

    caption = (
        f"✅ **Compression Done!**\n\n"
        f"📦 Original: `{human_size(orig_size)}`\n"
        f"📦 Compressed: `{human_size(comp_size)}`\n"
        f"💾 Saved: `{saved_pct:.1f}%`\n\n"
        f"⚙️ `{s['resolution']} | {s['codec']} | CRF {s['crf']}`"
    )

    # Upload
    ul_start = time.time()
    await status_msg.edit_text("📤 **Uploading compressed video...**")

    async def ul_progress(current, total):
        await update_progress(status_msg, "📤 Uploading", current, total, ul_start)

    try:
        if s["upload_mode"] == "Document":
            await message.reply_document(
                out_path, caption=caption, progress=ul_progress
            )
        else:
            await message.reply_video(
                out_path, caption=caption, progress=ul_progress
            )
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Upload failed: {e}")
    finally:
        for f in [dl_path, out_path]:
            try:
                if f and os.path.exists(f):
                    os.remove(f)
            except:
                pass

# ─────────────────────────────────────────────
#  CALLBACK HANDLERS
# ─────────────────────────────────────────────

@app.on_callback_query()
async def cb_handler(client, cb: CallbackQuery):
    uid = cb.from_user.id
    data = cb.data

    if data == "open_settings":
        s = db.get_settings(uid)
        await cb.message.edit_text(settings_text(s), reply_markup=settings_keyboard())
        return

    if data == "help":
        await cb.answer(
            "Send a video file and I'll compress it with your settings!",
            show_alert=True
        )
        return

    if data == "close":
        await cb.message.delete()
        return

    if data == "reset_settings":
        db.reset_settings(uid)
        s = db.get_settings(uid)
        await cb.message.edit_text(settings_text(s), reply_markup=settings_keyboard())
        await cb.answer("✅ Settings reset to default!")
        return

    # Resolution
    if data == "set_res":
        await cb.message.edit_reply_markup(InlineKeyboardMarkup([
            [InlineKeyboardButton("1080p", callback_data="res_1080p"),
             InlineKeyboardButton("720p",  callback_data="res_720p"),
             InlineKeyboardButton("576p",  callback_data="res_576p")],
            [InlineKeyboardButton("480p",  callback_data="res_480p"),
             InlineKeyboardButton("360p",  callback_data="res_360p"),
             InlineKeyboardButton("240p",  callback_data="res_240p")],
            [InlineKeyboardButton("Original", callback_data="res_Original")],
            [InlineKeyboardButton("« Back", callback_data="open_settings")],
        ]))
        return

    if data.startswith("res_"):
        db.update_setting(uid, "resolution", data[4:])
        s = db.get_settings(uid)
        await cb.message.edit_text(settings_text(s), reply_markup=settings_keyboard())
        await cb.answer(f"✅ Resolution set to {data[4:]}")
        return

    # Codec
    if data == "set_codec":
        await cb.message.edit_reply_markup(InlineKeyboardMarkup([
            [InlineKeyboardButton("x264 (fast)", callback_data="codec_x264"),
             InlineKeyboardButton("x265 (smaller)", callback_data="codec_x265")],
            [InlineKeyboardButton("VP9", callback_data="codec_VP9"),
             InlineKeyboardButton("AV1 (slowest)", callback_data="codec_AV1")],
            [InlineKeyboardButton("« Back", callback_data="open_settings")],
        ]))
        return

    if data.startswith("codec_"):
        db.update_setting(uid, "codec", data[6:])
        s = db.get_settings(uid)
        await cb.message.edit_text(settings_text(s), reply_markup=settings_keyboard())
        await cb.answer(f"✅ Codec set to {data[6:]}")
        return

    # Bits
    if data == "set_bits":
        await cb.message.edit_reply_markup(InlineKeyboardMarkup([
            [InlineKeyboardButton("8 Bits", callback_data="bits_8 Bits"),
             InlineKeyboardButton("10 Bits", callback_data="bits_10 Bits")],
            [InlineKeyboardButton("« Back", callback_data="open_settings")],
        ]))
        return

    if data.startswith("bits_"):
        db.update_setting(uid, "bits", data[5:])
        s = db.get_settings(uid)
        await cb.message.edit_text(settings_text(s), reply_markup=settings_keyboard())
        await cb.answer(f"✅ Bits set to {data[5:]}")
        return

    # CRF
    if data == "set_crf":
        await cb.message.edit_reply_markup(InlineKeyboardMarkup([
            [InlineKeyboardButton("18 (Best)", callback_data="crf_18"),
             InlineKeyboardButton("23", callback_data="crf_23"),
             InlineKeyboardButton("28", callback_data="crf_28")],
            [InlineKeyboardButton("30 (Default)", callback_data="crf_30"),
             InlineKeyboardButton("35", callback_data="crf_35"),
             InlineKeyboardButton("40", callback_data="crf_40")],
            [InlineKeyboardButton("45", callback_data="crf_45"),
             InlineKeyboardButton("51 (Smallest)", callback_data="crf_51")],
            [InlineKeyboardButton("« Back", callback_data="open_settings")],
        ]))
        return

    if data.startswith("crf_"):
        db.update_setting(uid, "crf", int(data[4:]))
        s = db.get_settings(uid)
        await cb.message.edit_text(settings_text(s), reply_markup=settings_keyboard())
        await cb.answer(f"✅ CRF set to {data[4:]}")
        return

    # Aspect Ratio
    if data == "set_aspect":
        await cb.message.edit_reply_markup(InlineKeyboardMarkup([
            [InlineKeyboardButton("16:9", callback_data="aspect_16:9"),
             InlineKeyboardButton("4:3",  callback_data="aspect_4:3"),
             InlineKeyboardButton("1:1",  callback_data="aspect_1:1")],
            [InlineKeyboardButton("None (Keep Original)", callback_data="aspect_None")],
            [InlineKeyboardButton("« Back", callback_data="open_settings")],
        ]))
        return

    if data.startswith("aspect_"):
        db.update_setting(uid, "aspect", data[7:])
        s = db.get_settings(uid)
        await cb.message.edit_text(settings_text(s), reply_markup=settings_keyboard())
        await cb.answer(f"✅ Aspect ratio set to {data[7:]}")
        return

    # Upload Mode
    if data == "set_upload":
        await cb.message.edit_reply_markup(InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Document", callback_data="upload_Document"),
             InlineKeyboardButton("🎬 Video", callback_data="upload_Video")],
            [InlineKeyboardButton("« Back", callback_data="open_settings")],
        ]))
        return

    if data.startswith("upload_"):
        db.update_setting(uid, "upload_mode", data[7:])
        s = db.get_settings(uid)
        await cb.message.edit_text(settings_text(s), reply_markup=settings_keyboard())
        await cb.answer(f"✅ Upload mode set to {data[7:]}")
        return

    # Watermark
    if data == "set_wm":
        await cb.message.reply_text(
            "💧 **Set Watermark**\n\nSend your watermark text as a reply to this message.\n"
            "Send `none` to remove watermark."
        )
        return

    # Metadata
    if data == "set_meta":
        await cb.message.edit_reply_markup(InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Keep Metadata", callback_data="meta_Enabled"),
             InlineKeyboardButton("❌ Remove Metadata", callback_data="meta_Disabled")],
            [InlineKeyboardButton("« Back", callback_data="open_settings")],
        ]))
        return

    if data.startswith("meta_"):
        db.update_setting(uid, "metadata", data[5:])
        s = db.get_settings(uid)
        await cb.message.edit_text(settings_text(s), reply_markup=settings_keyboard())
        await cb.answer(f"✅ Metadata set to {data[5:]}")
        return

    # Auto Rename
    if data == "set_rename":
        await cb.message.reply_text(
            "✏️ **Set Auto Rename**\n\nReply with the filename prefix.\n"
            "Send `none` to disable auto rename.\n\n"
            "Example: `MyVideo` → output will be `MyVideo_compressed.mp4`"
        )
        return

    await cb.answer()

# ─────────────────────────────────────────────
#  WATERMARK & RENAME TEXT INPUT
# ─────────────────────────────────────────────

@app.on_message(filters.text & filters.private & ~filters.command(["start","help","settings"]))
async def text_handler(client, message: Message):
    uid = message.from_user.id
    text = message.text.strip()

    # Simple keyword detection for watermark/rename setting flows
    # (In production, use conversation states / FSM)
    lower = text.lower()
    if lower == "none":
        db.update_setting(uid, "watermark", None)
        db.update_setting(uid, "rename", None)
        await message.reply_text("✅ Cleared!")
        return

    # Heuristic: short text could be rename or watermark
    await message.reply_text(
        f"❓ Did you want to set:\n\n"
        f"1️⃣ **Watermark** text → `{text}`\n"
        f"2️⃣ **Auto Rename** → `{text}`",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💧 Set as Watermark", callback_data=f"setwm_{text[:30]}")],
            [InlineKeyboardButton("✏️ Set as Auto Rename", callback_data=f"setrename_{text[:30]}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="close")],
        ])
    )

@app.on_callback_query(filters.regex("^setwm_"))
async def setwm_cb(client, cb: CallbackQuery):
    val = cb.data[6:]
    db.update_setting(cb.from_user.id, "watermark", val)
    await cb.message.edit_text(f"✅ Watermark set to: `{val}`")

@app.on_callback_query(filters.regex("^setrename_"))
async def setrename_cb(client, cb: CallbackQuery):
    val = cb.data[10:]
    db.update_setting(cb.from_user.id, "rename", val)
    await cb.message.edit_text(f"✅ Auto rename set to: `{val}`")

# ─────────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("🤖 Bot starting...")
    os.makedirs("downloads", exist_ok=True)
    app.run()
