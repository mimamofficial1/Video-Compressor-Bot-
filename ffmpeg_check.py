"""
Auto-detect or install ffmpeg.
Priority:
  1. System ffmpeg (already in PATH)
  2. static-ffmpeg bundled binary (pip install static-ffmpeg)
  3. Download portable binary from GitHub
"""
import os
import shutil
import subprocess
import sys

FFMPEG_PATH = None

def check_ffmpeg() -> str:
    global FFMPEG_PATH

    # 1. System ffmpeg
    system_ff = shutil.which("ffmpeg")
    if system_ff:
        print(f"✅ System ffmpeg found: {system_ff}")
        FFMPEG_PATH = system_ff
        return FFMPEG_PATH

    # 2. static-ffmpeg package
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
        path = shutil.which("ffmpeg")
        if path:
            print(f"✅ static-ffmpeg found: {path}")
            FFMPEG_PATH = path
            return FFMPEG_PATH
    except ImportError:
        pass

    # 3. Try downloading a portable static build
    print("⚠️  ffmpeg not found — trying to download static binary...")
    _download_ffmpeg()
    path = shutil.which("ffmpeg")
    if path:
        FFMPEG_PATH = path
        return FFMPEG_PATH

    raise RuntimeError(
        "❌ ffmpeg could not be found or installed.\n"
        "Run:  pip install static-ffmpeg\n"
        "Or install ffmpeg on your system."
    )


def get_ffmpeg_path() -> str:
    if FFMPEG_PATH:
        return FFMPEG_PATH
    return check_ffmpeg()


def _download_ffmpeg():
    """Download a static ffmpeg binary for Linux x86_64."""
    import urllib.request
    import tarfile
    import stat

    dest_dir = os.path.expanduser("~/.local/bin")
    os.makedirs(dest_dir, exist_ok=True)
    ff_bin = os.path.join(dest_dir, "ffmpeg")

    if os.path.exists(ff_bin):
        os.environ["PATH"] = dest_dir + ":" + os.environ.get("PATH", "")
        return

    url = (
        "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
        "ffmpeg-master-latest-linux64-gpl.tar.xz"
    )
    archive = "/tmp/ffmpeg.tar.xz"
    print(f"Downloading ffmpeg ...")
    try:
        urllib.request.urlretrieve(url, archive)
        with tarfile.open(archive, "r:xz") as tar:
            for member in tar.getmembers():
                if member.name.endswith("/ffmpeg") and member.isfile():
                    member.name = "ffmpeg"
                    tar.extract(member, dest_dir)
                    break
        os.chmod(ff_bin, os.stat(ff_bin).st_mode | stat.S_IEXEC)
        os.environ["PATH"] = dest_dir + ":" + os.environ.get("PATH", "")
        print(f"✅ ffmpeg downloaded to {ff_bin}")
    except Exception as e:
        print(f"❌ Auto-download failed: {e}")
