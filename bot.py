import os
import time
import asyncio
import subprocess
import shutil

# ── FFmpeg auto-setup ─────────────────────────────────────────────────────────
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
    print("static-ffmpeg loaded")
except Exception as e:
    print("static-ffmpeg not available:", e)

def get_ffmpeg_path():
    return shutil.which("ffmpeg") or "ffmpeg"

# ─────────────────────────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def human_size(num):
    for unit in ["B", "KB", "MB", "GB"]:
        if num < 1024:
            return "{:.2f} {}".format(num, unit)
        num /= 1024
    return "{:.2f} TB".format(num)

def progress_bar(current, total):
    pct = (current / total) * 100 if total else 0
    filled = int(pct / 10)
    bar = "█" * filled + "░" * (10 - filled)
    return "[{}] {:.1f}%".format(bar, pct)

async def update_progress(msg, action, current, total, start_time):
    elapsed = time.time() - start_time
    speed = current / elapsed if elapsed > 0 else 0
    eta = (total - current) / speed if speed > 0 else 0
    lines = [
        "**" + action + "**",
        "",
        progress_bar(current, total),
        "",
        "Size: " + human_size(current) + " / " + human_size(total),
        "Speed: " + human_size(speed) + "/s",
        "ETA: " + str(int(eta)) + "s",
    ]
    text = "\n".join(lines)
    try:
        await msg.edit_text(text)
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        pass

def settings_text(s):
    lines = [
        "**Your Settings**",
        "",
        "Resolution: `" + s["resolution"] + "`",
        "Codec: `" + s["codec"] + "`",
        "Bits: `" + s["bits"] + "`",
        "CRF: `" + str(s["crf"]) + "`",
        "Aspect Ratio: `" + s["aspect"] + "`",
        "Upload Mode: `" + s["upload_mode"] + "`",
        "Watermark: `" + str(s["watermark"] or "None") + "`",
        "WM Color: `" + s["wm_color"] + "`",
        "WM Position: `" + s["wm_pos"] + "`",
        "WM Size: `" + str(s["wm_size"]) + "`",
        "Metadata: `" + s["metadata"] + "`",
        "Auto Rename: `" + str(s["rename"] or "None") + "`",
    ]
    return "\n".join(lines)

def settings_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Resolution", callback_data="set_res"),
         InlineKeyboardButton("Codec", callback_data="set_codec")],
        [InlineKeyboardButton("Bits", callback_data="set_bits"),
         InlineKeyboardButton("CRF", callback_data="set_crf")],
        [InlineKeyboardButton("Aspect Ratio", callback_data="set_aspect"),
         InlineKeyboardButton("Upload Mode", callback_data="set_upload")],
        [InlineKeyboardButton("Watermark", callback_data="set_wm"),
         InlineKeyboardButton("Metadata", callback_data="set_meta")],
        [InlineKeyboardButton("Auto Rename", callback_data="set_rename")],
        [InlineKeyboardButton("Reset All", callback_data="reset_settings"),
         InlineKeyboardButton("Close", callback_data="close")],
    ])

def build_ffmpeg_cmd(input_path, output_path, s):
    vf_filters = []

    res_map = {
        "1080p": "1920:1080", "720p": "1280:720",
        "576p": "1024:576",   "480p": "854:480",
        "360p": "640:360",    "240p": "426:240",
        "Original": None,
    }
    scale = res_map.get(s["resolution"])
    if scale:
        vf_filters.append("scale=" + scale)

    if s["aspect"] != "None":
        vf_filters.append("setdar=" + s["aspect"].replace(":", "/"))

    wm = s.get("watermark")
    if wm and wm != "None":
        pos_map = {
            "top":    "x=(w-text_w)/2:y=10",
            "center": "x=(w-text_w)/2:y=(h-text_h)/2",
            "bottom": "x=(w-text_w)/2:y=h-text_h-10",
        }
        pos = pos_map.get(s["wm_pos"], pos_map["bottom"])
        vf_filters.append(
            "drawtext=text='" + wm + "':fontsize=" + str(s["wm_size"]) +
            ":fontcolor=" + s["wm_color"] + ":" + pos
        )

    vf = ",".join(vf_filters) if vf_filters else None

    codec_map = {
        "x264": "libx264", "x265": "libx265",
        "VP9":  "libvpx-vp9", "AV1": "libaom-av1",
    }
    vcodec = codec_map.get(s["codec"], "libx264")
    pix = "yuv420p10le" if s["bits"] == "10 Bits" else "yuv420p"

    cmd = [
        get_ffmpeg_path(), "-i", input_path,
        "-c:v", vcodec,
        "-crf", str(s["crf"]),
        "-preset", "fast",
        "-pix_fmt", pix,
        "-c:a", "aac",
        "-b:a", "128k",
    ]
    if vf:
        cmd += ["-vf", vf]
    if s["metadata"] == "Disabled":
        cmd += ["-map_metadata", "-1"]
    cmd += [output_path, "-y"]
    return cmd

# ─────────────────────────────────────────────────────────────────────────────
#  COMMANDS
# ─────────────────────────────────────────────────────────────────────────────

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message: Message):
    await message.reply_text(
        "Hi! I'm a **Video Compressor Bot**\n\n"
        "Send me any video and I'll compress it.\n\n"
        "Commands:\n"
        "/settings - Configure compression\n"
        "/help - How to use\n\n"
        "18+ content is NOT allowed.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Settings", callback_data="open_settings"),
             InlineKeyboardButton("Help", callback_data="help")]
        ])
    )

@app.on_message(filters.command("settings") & filters.private)
async def settings_cmd(client, message: Message):
    s = db.get_settings(message.from_user.id)
    await message.reply_text(settings_text(s), reply_markup=settings_keyboard())

@app.on_message(filters.command("help") & filters.private)
async def help_cmd(client, message: Message):
    await message.reply_text(
        "**How to use:**\n\n"
        "1. Send a video file (MP4, MKV, AVI, MOV)\n"
        "2. Bot compresses with your /settings\n"
        "3. Receive compressed file!\n\n"
        "Lower CRF = better quality but bigger file.\n"
        "x265 gives smaller files than x264."
    )

# ─────────────────────────────────────────────────────────────────────────────
#  VIDEO HANDLER
# ─────────────────────────────────────────────────────────────────────────────

@app.on_message((filters.video | filters.document) & filters.private)
async def handle_video(client, message: Message):
    file = message.video or message.document
    if not file:
        return
    if message.document and not message.document.mime_type.startswith("video/"):
        await message.reply_text("Please send a valid video file.")
        return
    if file.file_size > Config.MAX_FILE_SIZE:
        await message.reply_text("File too large! Max: " + human_size(Config.MAX_FILE_SIZE))
        return

    s = db.get_settings(message.from_user.id)
    status_msg = await message.reply_text("Downloading your video...")

    start = time.time()

    async def dl_progress(current, total):
        await update_progress(status_msg, "Downloading", current, total, start)

    try:
        dl_path = await message.download(progress=dl_progress)
    except Exception as e:
        await status_msg.edit_text("Download failed: " + str(e))
        return

    orig_size = os.path.getsize(dl_path)
    ext = ".mp4" if s["codec"] in ["x264", "x265"] else ".mkv"
    out_name = s["rename"] if s["rename"] else os.path.splitext(os.path.basename(dl_path))[0]
    out_path = "downloads/" + str(message.from_user.id) + "_" + out_name + "_compressed" + ext
    os.makedirs("downloads", exist_ok=True)

    await status_msg.edit_text(
        "Compressing...\n\n"
        "File: `" + os.path.basename(dl_path) + "`\n"
        "Settings: `" + s["resolution"] + " | " + s["codec"] + " | CRF " + str(s["crf"]) + "`"
    )

    cmd = build_ffmpeg_cmd(dl_path, out_path, s)
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=Config.FFMPEG_TIMEOUT)
        if proc.returncode != 0:
            err = proc.stderr.decode()[-500:]
            await status_msg.edit_text("FFmpeg error:\n```" + err + "```")
            return
    except subprocess.TimeoutExpired:
        await status_msg.edit_text("Compression timed out.")
        return
    except Exception as e:
        await status_msg.edit_text("Error: " + str(e))
        return

    comp_size = os.path.getsize(out_path)
    saved_pct = ((orig_size - comp_size) / orig_size * 100) if orig_size > 0 else 0

    caption = (
        "**Compression Done!**\n\n"
        "Original: `" + human_size(orig_size) + "`\n"
        "Compressed: `" + human_size(comp_size) + "`\n"
        "Saved: `{:.1f}%`\n\n".format(saved_pct) +
        "Settings: `" + s["resolution"] + " | " + s["codec"] + " | CRF " + str(s["crf"]) + "`"
    )

    ul_start = time.time()
    await status_msg.edit_text("Uploading compressed video...")

    async def ul_progress(current, total):
        await update_progress(status_msg, "Uploading", current, total, ul_start)

    try:
        if s["upload_mode"] == "Document":
            await message.reply_document(out_path, caption=caption, progress=ul_progress)
        else:
            await message.reply_video(out_path, caption=caption, progress=ul_progress)
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text("Upload failed: " + str(e))
    finally:
        for f in [dl_path, out_path]:
            try:
                if f and os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass

# ─────────────────────────────────────────────────────────────────────────────
#  CALLBACKS
# ─────────────────────────────────────────────────────────────────────────────

@app.on_callback_query()
async def cb_handler(client, cb: CallbackQuery):
    uid = cb.from_user.id
    data = cb.data

    if data == "open_settings":
        s = db.get_settings(uid)
        await cb.message.edit_text(settings_text(s), reply_markup=settings_keyboard())

    elif data == "help":
        await cb.answer("Send a video file and I'll compress it!", show_alert=True)

    elif data == "close":
        await cb.message.delete()

    elif data == "reset_settings":
        db.reset_settings(uid)
        s = db.get_settings(uid)
        await cb.message.edit_text(settings_text(s), reply_markup=settings_keyboard())
        await cb.answer("Settings reset!")

    elif data == "set_res":
        await cb.message.edit_reply_markup(InlineKeyboardMarkup([
            [InlineKeyboardButton("1080p", callback_data="res_1080p"),
             InlineKeyboardButton("720p",  callback_data="res_720p"),
             InlineKeyboardButton("576p",  callback_data="res_576p")],
            [InlineKeyboardButton("480p",  callback_data="res_480p"),
             InlineKeyboardButton("360p",  callback_data="res_360p"),
             InlineKeyboardButton("240p",  callback_data="res_240p")],
            [InlineKeyboardButton("Original", callback_data="res_Original")],
            [InlineKeyboardButton("Back", callback_data="open_settings")],
        ]))

    elif data.startswith("res_"):
        db.update_setting(uid, "resolution", data[4:])
        s = db.get_settings(uid)
        await cb.message.edit_text(settings_text(s), reply_markup=settings_keyboard())
        await cb.answer("Resolution: " + data[4:])

    elif data == "set_codec":
        await cb.message.edit_reply_markup(InlineKeyboardMarkup([
            [InlineKeyboardButton("x264 (fast)", callback_data="codec_x264"),
             InlineKeyboardButton("x265 (smaller)", callback_data="codec_x265")],
            [InlineKeyboardButton("VP9", callback_data="codec_VP9"),
             InlineKeyboardButton("AV1 (slowest)", callback_data="codec_AV1")],
            [InlineKeyboardButton("Back", callback_data="open_settings")],
        ]))

    elif data.startswith("codec_"):
        db.update_setting(uid, "codec", data[6:])
        s = db.get_settings(uid)
        await cb.message.edit_text(settings_text(s), reply_markup=settings_keyboard())
        await cb.answer("Codec: " + data[6:])

    elif data == "set_bits":
        await cb.message.edit_reply_markup(InlineKeyboardMarkup([
            [InlineKeyboardButton("8 Bits", callback_data="bits_8 Bits"),
             InlineKeyboardButton("10 Bits", callback_data="bits_10 Bits")],
            [InlineKeyboardButton("Back", callback_data="open_settings")],
        ]))

    elif data.startswith("bits_"):
        db.update_setting(uid, "bits", data[5:])
        s = db.get_settings(uid)
        await cb.message.edit_text(settings_text(s), reply_markup=settings_keyboard())
        await cb.answer("Bits: " + data[5:])

    elif data == "set_crf":
        await cb.message.edit_reply_markup(InlineKeyboardMarkup([
            [InlineKeyboardButton("18 (Best)", callback_data="crf_18"),
             InlineKeyboardButton("23", callback_data="crf_23"),
             InlineKeyboardButton("28", callback_data="crf_28")],
            [InlineKeyboardButton("30 (Default)", callback_data="crf_30"),
             InlineKeyboardButton("35", callback_data="crf_35"),
             InlineKeyboardButton("40", callback_data="crf_40")],
            [InlineKeyboardButton("45", callback_data="crf_45"),
             InlineKeyboardButton("51 (Smallest)", callback_data="crf_51")],
            [InlineKeyboardButton("Back", callback_data="open_settings")],
        ]))

    elif data.startswith("crf_"):
        db.update_setting(uid, "crf", int(data[4:]))
        s = db.get_settings(uid)
        await cb.message.edit_text(settings_text(s), reply_markup=settings_keyboard())
        await cb.answer("CRF: " + data[4:])

    elif data == "set_aspect":
        await cb.message.edit_reply_markup(InlineKeyboardMarkup([
            [InlineKeyboardButton("16:9", callback_data="aspect_16:9"),
             InlineKeyboardButton("4:3",  callback_data="aspect_4:3"),
             InlineKeyboardButton("1:1",  callback_data="aspect_1:1")],
            [InlineKeyboardButton("None (Original)", callback_data="aspect_None")],
            [InlineKeyboardButton("Back", callback_data="open_settings")],
        ]))

    elif data.startswith("aspect_"):
        db.update_setting(uid, "aspect", data[7:])
        s = db.get_settings(uid)
        await cb.message.edit_text(settings_text(s), reply_markup=settings_keyboard())
        await cb.answer("Aspect: " + data[7:])

    elif data == "set_upload":
        await cb.message.edit_reply_markup(InlineKeyboardMarkup([
            [InlineKeyboardButton("Document", callback_data="upload_Document"),
             InlineKeyboardButton("Video", callback_data="upload_Video")],
            [InlineKeyboardButton("Back", callback_data="open_settings")],
        ]))

    elif data.startswith("upload_"):
        db.update_setting(uid, "upload_mode", data[7:])
        s = db.get_settings(uid)
        await cb.message.edit_text(settings_text(s), reply_markup=settings_keyboard())
        await cb.answer("Upload mode: " + data[7:])

    elif data == "set_wm":
        await cb.message.reply_text(
            "Send your watermark text as a message.\n"
            "Send `none` to remove watermark."
        )

    elif data == "set_meta":
        await cb.message.edit_reply_markup(InlineKeyboardMarkup([
            [InlineKeyboardButton("Keep Metadata", callback_data="meta_Enabled"),
             InlineKeyboardButton("Remove Metadata", callback_data="meta_Disabled")],
            [InlineKeyboardButton("Back", callback_data="open_settings")],
        ]))

    elif data.startswith("meta_"):
        db.update_setting(uid, "metadata", data[5:])
        s = db.get_settings(uid)
        await cb.message.edit_text(settings_text(s), reply_markup=settings_keyboard())
        await cb.answer("Metadata: " + data[5:])

    elif data == "set_rename":
        await cb.message.reply_text(
            "Send the filename prefix as a message.\n"
            "Send `none` to disable."
        )

    elif data.startswith("setwm_"):
        val = data[6:]
        db.update_setting(uid, "watermark", val)
        await cb.message.edit_text("Watermark set to: `" + val + "`")

    elif data.startswith("setrename_"):
        val = data[10:]
        db.update_setting(uid, "rename", val)
        await cb.message.edit_text("Auto rename set to: `" + val + "`")

    try:
        await cb.answer()
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
#  TEXT HANDLER (watermark / rename input)
# ─────────────────────────────────────────────────────────────────────────────

@app.on_message(filters.text & filters.private & ~filters.command(["start", "help", "settings"]))
async def text_handler(client, message: Message):
    uid = message.from_user.id
    text = message.text.strip()

    if text.lower() == "none":
        db.update_setting(uid, "watermark", None)
        db.update_setting(uid, "rename", None)
        await message.reply_text("Cleared!")
        return

    await message.reply_text(
        "Did you want to set:\n\n"
        "1. **Watermark** text: `" + text + "`\n"
        "2. **Auto Rename**: `" + text + "`",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Set as Watermark", callback_data="setwm_" + text[:30])],
            [InlineKeyboardButton("Set as Auto Rename", callback_data="setrename_" + text[:30])],
            [InlineKeyboardButton("Cancel", callback_data="close")],
        ])
    )

# ─────────────────────────────────────────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ff = get_ffmpeg_path()
    print("ffmpeg path:", ff)
    os.makedirs("downloads", exist_ok=True)
    print("Bot starting...")
    app.run()
