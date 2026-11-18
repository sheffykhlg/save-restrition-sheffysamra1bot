import time
import asyncio
from core.client import safe_edit_text

class ProgressTracker:
    def __init__(self):
        self.last_update = 0
        self.last_bytes = 0
        self.peak_speed = 0.0
        self._lock = asyncio.Lock()

    async def callback(self, current, total, status_msg, action_type, start_time, cancel_event):
        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError("Process force cancelled.")

        async with self._lock:
            now = time.time()
            if self.last_update == 0:
                self.last_update = now
                self.last_bytes = current

            time_diff = max(now - self.last_update, 0.001)
            percentage = (current / total) * 100 if total > 0 else 0
            instant_speed = (current - self.last_bytes) / time_diff / (1024 * 1024) if now > self.last_update else 0.0
            elapsed = max(now - start_time, 0.01)
            avg_speed = current / elapsed / (1024 * 1024)
            display_speed = instant_speed if instant_speed > 0 else avg_speed

            if display_speed > self.peak_speed:
                self.peak_speed = display_speed

            current_mb = current / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            remaining_bytes = max(total - current, 0)
            eta_seconds = int(remaining_bytes / (display_speed * 1024 * 1024)) if display_speed > 0 else 0
            eta_min, eta_sec = divmod(eta_seconds, 60)
            eta_str = f"{eta_min}m {eta_sec}s" if eta_min > 0 else f"{eta_sec}s"

            # Sleek 10-block progress bar
            filled_blocks = int(percentage / 10)
            progress_bar = "▰" * filled_blocks + "▱" * (10 - filled_blocks)

            if (now - self.last_update >= 3.0) or current == total or (self.last_bytes == 0 and current > 0):
                self.last_update = now
                self.last_bytes = current

                # Premium UI Layout
                progress_card = (
                    f"⚡ <b>{action_type}</b>\n"
                    f"<code>[{progress_bar}]</code> <b>{percentage:.1f}%</b>\n\n"
                    f"📦 <b>Size:</b> <code>{current_mb:.1f} MB</code> / <code>{total_mb:.1f} MB</code>\n"
                    f"🚀 <b>Speed:</b> <code>{display_speed:.2f} MB/s</code> (Peak: <code>{self.peak_speed:.2f} MB/s</code>)\n"
                    f"⏱️ <b>ETA:</b> <code>{eta_str}</code>"
                )

                await safe_edit_text(status_msg, progress_card)

