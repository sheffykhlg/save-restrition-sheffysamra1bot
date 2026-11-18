import os
import logging
import subprocess

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s"
)
logger = logging.getLogger("Aria2NitroEngine")

from configs import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    ADMIN_ID,
    MONGO_URI,
    WORK_DIR,
    LOG_GROUP_ID,
    LOG_CHANNEL_ID,
    FSUB_CHANNEL,
    ENCRYPTION_KEY,
    encrypt_session,
    decrypt_session
)

def start_aria2_daemon():
    try:
        aria_cmd = [
            "aria2c",
            "--enable-rpc",
            "--rpc-listen-all=false",
            "--rpc-listen-port=6800",
            "--max-connection-per-server=16",
            "--split=16",
            "--min-split-size=1M"
        ]
        if os.name != "nt":
            aria_cmd.append("--daemon=true")
        subprocess.Popen(aria_cmd)
        logger.info("⚡ ARIA2C DAEMON ACTIVE FOR HIGH SPEED MEDIA TRANSFERS!")
    except Exception as e:
        logger.error(f"Aria2c startup exception: {e}", exc_info=True)

