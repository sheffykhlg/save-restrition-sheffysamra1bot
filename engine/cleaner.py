import os
import gc
import json
import time
import shutil
import subprocess
try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None
from core.config import WORK_DIR, logger
from core.client import cleanup_idle_clients

def cleanup_message_files(message_id: int, download_path: str = None, thumb_path: str = None):
    try:
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
            except Exception:
                pass
        if thumb_path and os.path.exists(thumb_path):
            try:
                os.remove(thumb_path)
            except Exception:
                pass
        if os.path.exists(WORK_DIR):
            prefix = f"{message_id}_"
            thumb_prefix = f"thumb_{message_id}"
            for f in os.listdir(WORK_DIR):
                if f.startswith(prefix) or f.startswith(thumb_prefix):
                    p = os.path.join(WORK_DIR, f)
                    try:
                        if os.path.isfile(p) or os.path.islink(p):
                            os.unlink(p)
                        elif os.path.isdir(p):
                            shutil.rmtree(p)
                    except Exception:
                        pass
        gc.collect()
    except Exception as e:
        logger.debug(f"cleanup_message_files note for {message_id}: {e}")

def cleanup_ram_and_disk(force_all=False):
    """
    Cleans up idle client sessions (Heroku 2X 1024MB RAM protection)
    and purges older temporary media files from WORK_DIR.
    """
    try:
        cleanup_idle_clients()
        if os.path.exists(WORK_DIR):
            now = time.time()
            for file_name in os.listdir(WORK_DIR):
                file_path = os.path.join(WORK_DIR, file_name)
                try:
                    if not force_all:
                        mtime = os.path.getmtime(file_path)
                        if (now - mtime) < 1800:
                            continue
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    logger.debug(f"Cleanup check note {file_path}: {e}")
        gc.collect()
    except Exception as e:
        logger.error(f"Cleanup Error: {e}", exc_info=True)

def get_video_metadata(file_path: str):
    """Calculates exact duration, width and height using FFprobe."""
    duration, width, height = 0, 0, 0
    try:
        if imageio_ffmpeg is not None:
            ffprobe_bin = imageio_ffmpeg.get_ffmpeg_exe().replace("ffmpeg", "ffprobe")
        else:
            ffprobe_bin = "ffprobe"
        cmd = [
            ffprobe_bin,
            "-v", "error",
            "-show_entries", "format=duration:stream=width,height",
            "-of", "json",
            file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        data = json.loads(result.stdout)
        if "format" in data and "duration" in data["format"]:
            duration = int(float(data["format"]["duration"]))
        if "streams" in data:
            for stream in data["streams"]:
                if "width" in stream and "height" in stream:
                    width = int(stream["width"])
                    height = int(stream["height"])
                    break
    except Exception as e:
        logger.error(f"FFprobe metadata extraction failed for {file_path}: {e}", exc_info=True)
    return duration, width, height
