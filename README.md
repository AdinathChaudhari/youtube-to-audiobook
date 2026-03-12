# 🎧 YouTube → Audiobook Converter v8

Convert any YouTube video or playlist into a fully chapterized `.m4b` audiobook — with embedded cover art, rich metadata, and hardware-accelerated encoding.

![Python](https://img.shields.io/badge/python-3.8%2B-blue?logo=python&logoColor=white)
![FFmpeg](https://img.shields.io/badge/ffmpeg-required-green?logo=ffmpeg)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey)
![License](https://img.shields.io/badge/license-MIT-informational)

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [How It Works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Interactive Walkthrough](#interactive-walkthrough)
- [Playlist & Channel Support](#playlist--channel-support)
- [Custom Chapters](#custom-chapters)
- [Output Quality & Encoding](#output-quality--encoding)
- [Metadata](#metadata)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)
- [Changelog](#changelog)

---

## Overview

`youtube_to_audiobook_v8.py` downloads the highest-quality audio stream available from a YouTube video (or entire playlist), packages it into an `.m4b` audiobook file, and embeds:

- **Chapters** — from YouTube's own chapter markers, or your own custom timestamps
- **Cover art** — from the video thumbnail, or a custom image you supply
- **Rich metadata** — title, author, narrator, year, genre, and description
- **Hardware-accelerated encoding** — uses Apple AudioToolbox on macOS (`aac_at`) or the best available software encoder elsewhere

The output is a single `.m4b` file that plays natively in Apple Books, Overcast, Pocket Casts, VLC, and any other audiobook-aware player.

---

## Features

| Feature | Details |
|---|---|
| 🎵 True best-quality download | Inspects every available audio stream, sorts by bitrate, picks the highest |
| 📐 Adaptive output bitrate | Never upsamples — output bitrate matches or stays below the source ceiling |
| ⚡ Hardware acceleration | Auto-detects `aac_at` (Apple) → `libfdk_aac` → `aac` with live validation |
| 📦 Two-pass pipeline | Encode-then-mux: cleaner, faster, no intermediate quality loss |
| 📖 Auto chapters | Reads YouTube chapter markers and embeds them directly |
| ✏️ Custom chapters | Paste your own `HH:MM:SS - Title` timestamps, or provide a file |
| 🖼️ Cover art | Uses YouTube thumbnail or a custom JPG/PNG you supply |
| 🏷️ Rich metadata | Author, narrator, year, genre, description — all embedded in M4B tags |
| 📋 Playlist support | Pass a playlist or channel URL — one M4B per video, processed in sequence |
| 🔔 Completion sound | Audio notification when encoding finishes (macOS/Windows/Linux) |
| 🖥️ Interactive CLI | Friendly prompts walk you through every option — no flags to memorize |

---

## How It Works

The script runs in three stages:

```
YouTube URL
    │
    ▼
┌─────────────────────────────────────┐
│  Stage 1 — Download                 │
│  • Inspect all audio streams        │
│  • Pick highest bitrate stream      │
│  • Download thumbnail               │
│  • Extract YouTube chapter markers  │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  Stage 2 — Encode (Pass 1)          │
│  • Detect best AAC encoder          │
│  • Measure source bitrate           │
│  • Pick adaptive output bitrate     │
│  • Encode audio → .m4a              │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  Stage 3 — Mux (Pass 2)             │
│  • Combine audio + cover + chapters │
│  • Embed all metadata tags          │
│  • Output final .m4b                │
└─────────────────────────────────────┘
```

---

## Requirements

### System Dependencies

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.8+ | Runtime |
| FFmpeg | 4.0+ | Audio encoding and muxing |
| FFprobe | (ships with FFmpeg) | Stream inspection |

### Installing FFmpeg

**macOS (Homebrew):**
```bash
brew install ffmpeg
```

**Ubuntu / Debian:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**Windows:**
Download a build from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html) and add the `bin/` folder to your `PATH`.

> **macOS note:** For hardware acceleration, the standard Homebrew FFmpeg includes `aac_at` automatically. No extra steps needed.

> **libfdk_aac note:** If you want the best software encoder quality, install an FFmpeg build with `libfdk_aac` support (e.g. via `brew install ffmpeg --with-fdk-aac` or a custom build). The script detects it automatically if present.

---

## Installation

**1. Clone the repository:**
```bash
git clone https://github.com/yourname/youtube-to-audiobook.git
cd youtube-to-audiobook
```

**2. Create a virtual environment (recommended):**
```bash
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows
```

**3. Install Python dependencies:**
```bash
pip install -r requirements.txt
```

**`requirements.txt`:**
```
yt-dlp
Pillow
pandas
tqdm
```

---

## Usage

### Basic (interactive)
```bash
python youtube_to_audiobook_v8.py
```
The script will prompt you for everything it needs.

### Pass a URL directly (skips the URL prompt)
```bash
python youtube_to_audiobook_v8.py --url "https://www.youtube.com/watch?v=XXXXXXXXXXX"
```

### Playlist or channel URL
```bash
python youtube_to_audiobook_v8.py --url "https://www.youtube.com/playlist?list=XXXXXXXXXX"
```

### Disable completion sound
```bash
python youtube_to_audiobook_v8.py --no-notification
```

### All flags
```
usage: youtube_to_audiobook_v8.py [-h] [--url URL] [--no-notification]

optional arguments:
  -h, --help          Show this help message and exit
  --url URL           YouTube video or playlist URL
  --no-notification   Disable the completion sound
```

---

## Interactive Walkthrough

When you run the script, it guides you through each decision. Here is a full example session:

```
╔══════════════════════════════════════════════════════════════════╗
║   🎧  YouTube → Audiobook Converter  v8  (Best Quality Edition) ║
╚══════════════════════════════════════════════════════════════════╝

🔍 Detecting best AAC encoder...
   ⚡ Hardware → Apple AudioToolbox — hardware accelerated (macOS)

📺 Enter YouTube URL (video or playlist): https://www.youtube.com/watch?v=...

📺 Video  : The Art of War - Full Audiobook
⏱️  Duration: 01:12:34

--- Cover Image ---
Use the video's thumbnail as cover? (yes/no): yes

--- Metadata ---
Author name           : Sun Tzu
Narrator name         : (Enter to skip)
Year (e.g. 2024)      : 2024
Genre/Category        : Audiobook
Description/Comment   : Classic Chinese military treatise

--- Title ---
Use YouTube title 'The Art of War - Full Audiobook'? (yes/no): yes

--- Chapters ---
Do you have custom chapter timestamps? (yes/no): no
  Using YouTube chapter metadata if available.

🔍 Inspecting available audio streams...
🎵 Best stream: OPUS @ 160 kbps  [webm]  (format: 251)
⬇️  Downloading: 100.0%  (3.20MiB/s)
✅ Download complete

📊 Analysing source audio quality...
   Source codec  : OPUS
   Source bitrate: ~160 kbps
   Output bitrate: 160k CBR
   Encoder       : Apple AudioToolbox — hardware accelerated (macOS)
   Mode          : ⚡ Hardware

⚡ Encoding audio (160k CBR)...
Encoding: 100%|████████████████████| 4354/4354 [00:18<00:00, 240s/s]
✅ Encoded in 18.2s  (239.8x realtime)

📦 Muxing into M4B (chapters + cover + metadata)...

✅ Done: The Art of War - Full Audiobook.m4b  (73.4 MB)

════════════════════════════════════════════════════════════════════
🎉 All done!  1/1 audiobook(s) created
⏱️  Total time: 1m 24.6s
   📁 /Users/you/The Art of War - Full Audiobook.m4b
════════════════════════════════════════════════════════════════════
```

---

## Playlist & Channel Support

Pass any YouTube playlist or channel URL and the script will:

1. Detect the playlist automatically and report how many videos it found
2. Use each video's own YouTube title as the audiobook title
3. Use each video's thumbnail as the cover art
4. Apply your shared metadata (author, genre, etc.) to every video
5. Output one `.m4b` per video in your current working directory

```bash
python youtube_to_audiobook_v8.py --url "https://www.youtube.com/playlist?list=XXXXXXXXXX"

📋 Playlist detected: 12 video(s)

════════════════════════════════════════════════════════════════════
  Video 1/12: https://www.youtube.com/watch?v=...
════════════════════════════════════════════════════════════════════
...
```

If one video in a playlist fails (private, geo-blocked, etc.), the script logs the error and continues with the remaining videos.

---

## Custom Chapters

If a video does not have YouTube chapter markers, or you want to override them, you can supply your own timestamps.

### Format

Each line must follow this pattern:
```
HH:MM:SS - Chapter Title
```

**Example:**
```
00:00:00 - Introduction
00:05:30 - Part One: Laying Plans
00:18:45 - Part Two: Waging War
00:31:00 - Part Three: Strategic Attack
01:02:15 - Conclusion
```

### Input methods

**Option A — Paste directly:**
When prompted, choose `P` and paste your timestamps line by line. Press Enter on an empty line when done.

**Option B — Provide a file:**
Save your timestamps to a `.txt` file and choose `F` when prompted, then enter the file path.

### Notes
- Timestamps do not need to be in order — the script sorts them automatically
- The final chapter always extends to the end of the audio
- If a line cannot be parsed, the script warns you and skips it (other chapters are unaffected)

---

## Output Quality & Encoding

### Format Selection

The script queries every audio-only stream YouTube offers for the video and ranks them by:

1. **Bitrate** (highest first)
2. **Codec preference** — `opus` > `aac` > `mp4a` > `vorbis` > `mp3`

It then requests that exact stream by format ID, so you always get the best one available — not just whatever `bestaudio` happens to resolve to.

Typical YouTube audio ceilings:

| Content type | Typical best stream |
|---|---|
| Standard video | Opus 160 kbps |
| Music / high quality | AAC 256 kbps or Opus 160 kbps |
| Older / low-quality uploads | AAC 128 kbps or MP3 128 kbps |

### Adaptive Output Bitrate

After downloading, the script measures the source file's actual bitrate and selects a CBR output target from this ladder:

```
64k → 96k → 128k → 160k → 192k → 256k → 320k
```

It picks the highest step that does **not** exceed the source. This means:
- A 160 kbps source → encoded at **160k**
- A 128 kbps source → encoded at **128k**
- A 256 kbps source → encoded at **256k**

No upsampling. No wasted file size.

### Encoder Priority

| Encoder | Type | Quality | Notes |
|---|---|---|---|
| `aac_at` | ⚡ Hardware | Excellent | Apple AudioToolbox, macOS only |
| `libfdk_aac` | 🖥️ Software | Best software | Requires custom FFmpeg build |
| `aac` | 🖥️ Software | Good | Ships with all FFmpeg builds |

The script tests each encoder with a real 0.1-second encode before selecting it — not just a string match against the encoder list.

### Two-Pass Pipeline

```
Pass 1:  audio file  ──[encode]──►  encoded_audio.m4a
Pass 2:  encoded_audio.m4a
       + cover.jpg
       + metadata.txt (chapters + tags)
         ──[mux, -c copy]──►  final_output.m4b
```

Pass 2 uses `-c copy`, so there is zero re-encoding on the mux step. The cover and chapter data are injected at nearly zero cost.

---

## Metadata

All metadata is embedded directly into the M4B file's MP4 tags and is visible in Apple Books, Overcast, Plex, and other players.

| Prompt | MP4 tag | Example |
|---|---|---|
| Author name | `artist`, `album_artist` | `Sun Tzu` |
| Narrator name | `composer` | `John Smith` |
| Year | `date` | `2024` |
| Genre / Category | `genre` | `Audiobook` |
| Description | `comment` | `Classic military treatise...` |
| Title (from title prompt) | `title`, `album` | `The Art of War` |

All fields are optional — press Enter at any prompt to skip it.

---

## Project Structure

```
youtube-to-audiobook/
├── youtube_to_audiobook_v8.py   # Main script
├── requirements.txt             # Python dependencies
└── README.md                    # This file
```

### Key functions at a glance

| Function | Purpose |
|---|---|
| `detect_ffmpeg_path()` | Locates FFmpeg binary on the system |
| `detect_best_aac_encoder()` | Tests and selects the best available AAC encoder |
| `get_best_audio_format(url)` | Inspects YouTube streams and returns the highest-quality format ID |
| `pick_output_bitrate(source_kbps)` | Chooses adaptive CBR output bitrate from the ladder |
| `download_audio(url, ...)` | Downloads audio using the selected format |
| `download_thumbnail(url, ...)` | Downloads and converts the video thumbnail to JPG |
| `generate_chapters_csv(info, ...)` | Extracts YouTube chapter markers to a CSV |
| `create_audiobook(folder, ...)` | Two-pass encode → mux pipeline, returns `.m4b` path |
| `parse_timestamps(text)` | Parses `HH:MM:SS - Title` lines from user input |
| `expand_urls(url)` | Expands a playlist URL into individual video URLs |
| `play_notification_sound()` | Cross-platform completion sound |
| `main()` | Interactive CLI flow and orchestration |

---

## Troubleshooting

### `FFmpeg not found`
Make sure FFmpeg is installed and on your `PATH`. Run `ffmpeg -version` to verify. See [Installing FFmpeg](#installing-ffmpeg).

### `Hardware encoder (aac_at) failed, falling back to software`
This is expected on Linux and Windows — `aac_at` is macOS-only. The script automatically falls back to the best available software encoder.

### `Expected 1 audio file, found 0`
The download may have failed silently. Check your internet connection and try again. If the video is age-restricted or region-locked, you may need to pass cookies to `yt-dlp` (see the [yt-dlp documentation](https://github.com/yt-dlp/yt-dlp#usage-and-options)).

### `Format detection failed`
This usually means the video is unavailable (private, deleted, or geo-blocked). Try the URL in a browser first to confirm it's accessible.

### Chapters not showing in Apple Books
Make sure the file extension is `.m4b` (not `.m4a`). Apple Books uses the extension to decide whether to treat a file as an audiobook. The script always outputs `.m4b`.

### Large file size
If the output is unexpectedly large, check the source bitrate printed during encoding. A 256 kbps source will naturally produce a larger file than a 128 kbps one. You can manually lower the bitrate by editing `CBR_LADDER` at the top of the script and removing the higher values.

### `yt-dlp` errors or stale formats
Update `yt-dlp` regularly — YouTube changes its internal APIs frequently:
```bash
pip install --upgrade yt-dlp
```

---

## FAQ

**Q: Does this work with YouTube Music or YouTube Shorts?**
Yes — any URL that `yt-dlp` can handle will work, including YouTube Music and Shorts.

**Q: Can I use this for a video with no chapters?**
Yes. If the video has no YouTube chapter markers and you don't supply custom timestamps, the output will be a single-track M4B with no chapter navigation.

**Q: What is the difference between `.m4a` and `.m4b`?**
Both are AAC audio in an MP4 container. The `.m4b` extension signals to audiobook players (Apple Books, Overcast, etc.) that the file is an audiobook — enabling bookmarking, chapter navigation, and variable playback speed. The script always outputs `.m4b`.

**Q: Can I run this without a GUI / in a headless environment?**
Yes. Pass `--url` to skip the URL prompt, and answer the remaining interactive prompts via stdin. All prompts go to stdout so they're visible in a terminal.

**Q: Will this re-encode audio that is already AAC?**
Yes — once. The downloaded stream is encoded to a clean AAC `.m4a` at the adaptive bitrate, then muxed with `-c copy`. There is no second encode during muxing.

**Q: Why does the script download as Opus but encode to AAC?**
M4B/MP4 containers do not support Opus audio. The Opus stream is the highest-quality YouTube offers, so the script downloads it losslessly and re-encodes to AAC for container compatibility. The quality loss is minimal when the target bitrate is at or near the source bitrate.

---

## Changelog

### v8 (current)
- **New:** True best-quality stream selection — sorts all audio-only streams by bitrate, picks highest
- **New:** Adaptive output bitrate — never upsamples, matches source ceiling from CBR ladder
- **New:** Smart encoder detection — validates each encoder with a real test encode before selecting
- **New:** `libfdk_aac` support as a middle-tier software encoder
- **New:** Two-pass pipeline — encode then mux, zero re-encode on mux step
- **New:** Rich metadata prompts — author, narrator, year, genre, description
- **New:** Playlist and channel support — one M4B per video
- **New:** `tqdm` progress bar during audio encoding
- **New:** Cross-platform completion sound notification
- **New:** iPod / M4B compatibility flags (`-brand M4B`, `-movflags +faststart`)
- **Fixed:** Chapters no longer silently dropped when last chapter has no end time
- **Fixed:** Cover art JPG → PNG conversion no longer leaves temp files behind

### v7
- M2 Pro hardware acceleration (`aac_at`) with software fallback
- Smart format detection (lossless / high AAC / compressed)
- Custom chapter timestamp support (paste or file)
- Custom cover art support
- ETA display during encoding

---

## License

MIT License — see `LICENSE` for details.

---

## Acknowledgements

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — the engine behind all YouTube downloading
- [FFmpeg](https://ffmpeg.org) — audio encoding and M4B muxing
- [Pillow](https://python-pillow.org) — cover image handling
- [tqdm](https://github.com/tqdm/tqdm) — progress bars
