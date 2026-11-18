# 🔒 SPEED ENGINE LOCKED - CRITICAL ARCHITECTURE SPECIFICATION

> ⚠️ **STRICT INSTRUCTION FOR ANY AI ASSISTANT OR DEVELOPER:**
> **DO NOT TOUCH, MODIFY, REFACTOR, SIMPLIFY, DOWNGRADE, OR REMOVE THE SPEED ENGINE AND TRANSFER PIPELINES IN THIS PROJECT UNDER ANY CIRCUMSTANCES.**
> 
> The multi-stream parallel chunk downloader, persistent user connection cache, and concurrency transmission settings are **PERMANENTLY LOCKED** and benchmarked for maximum network throughput on Telegram infrastructure.

---

## 📌 Core Locked Components

### 1. Multi-Stream Parallel Chunk Downloader (`fast_parallel_download`)
- **Location:** `main.py`
- **Mechanism:**
  - Files $\ge 10\text{ MB}$ are partitioned into parallel chunk slices ($\text{1 MiB}$ each).
  - Uses **6 simultaneous worker streams** invoking `client.stream_media(msg, offset=offset, limit=limit)` concurrently across Telegram MTProto.
  - File is pre-allocated on disk using `f.truncate(file_size)` to eliminate write fragmentation.
  - In-place seek-and-write with `asyncio.Lock()` ensures zero file stitching delay and instant finalization.
  - Thread-safe ProgressTracker reports live instant speed, peak speed, ETA, and visual bar.
  - **Graceful Fallback:** Automatically falls back to standard `download_media` if parallel chunk streaming encounters non-streamable files or edge-case protocol responses.
- **Rule:** **NEVER replace with standard sequential `download_media` or reduce worker concurrency.**

---

### 2. Multi-DC Persistent Connection Cache (`CACHED_USER_CLIENTS`)
- **Location:** `main.py` -> `get_or_create_user_client`, `verify_and_save_session`
- **Mechanism:**
  - Keeps active user `Client` instances alive in memory across message and batch downloads.
  - Maintains cached MTProto auth keys for **all Data Centers (DC1, DC2, DC3, DC4, DC5)**.
  - Prevents Telegram from triggering `Waiting for 16 seconds (upload.GetFile)` and `AuthKeyDuplicated` errors caused by frequent client reconnections.
- **Rule:** **NEVER create throwaway/temporary Client instances per message or disconnect the user client after each download.**

---

### 3. Client Concurrency & Network Pipeline Tuning
- **Download Client (`user_app`):**
  ```python
  Client(
      name=f"persistent_user_{user_id}",
      api_id=API_ID,
      api_hash=API_HASH,
      session_string=session_str,
      workers=64,
      max_concurrent_transmissions=16,  # LOCKED: Allows 6 parallel streams without throttling
      sleep_threshold=180,
      no_updates=True,                  # LOCKED: Stops wasteful background update packets
      skip_updates=True,                # LOCKED: Skips old queue processing
      in_memory=True
  )
  ```
- **Upload Client (`bot`):**
  ```python
  bot_kwargs = {
      "name": "universal_bot_interface",
      "api_id": API_ID,
      "api_hash": API_HASH,
      "workers": 64,
      "max_concurrent_transmissions": 8,  # LOCKED: Sweet spot for upload speed without SaveBigFilePart floodwait
      "parse_mode": enums.ParseMode.HTML,
      "sleep_threshold": 180
  }
  ```
- **Rule:** **DO NOT remove `no_updates=True` or alter transmission concurrency values.**

---

### 4. Fast Async Event Loop & Cryptography Libraries
- **Libraries:** `kurigram`, `kuricrypt` (Rust native MTProto AES/IGE crypto), `uvloop` (C-based libuv event loop).
- **Rule:** **DO NOT replace `kurigram` with older unmaintained libraries or remove `uvloop`.**

---

### 5. Zero-Lag Batch Transmission Interval
- Batch message delay is set to `0.3s` (`await asyncio.sleep(0.3)`).
- **Rule:** **DO NOT increase this sleep delay back to 1.5s or higher.**

---

**🔒 STATUS: VERIFIED, BENCHMARKED & LOCKED BY PROJECT OWNER.**

