#!/usr/bin/env python3

"""
YouTube to Chapterized Audiobook Converter v8
----------------------------------------------
IMPROVEMENTS OVER v7:
- True best-quality YouTube format selection (sorts by bitrate, prefers opus/AAC)
- Smart encoder detection: aac_at → libfdk_aac → aac (tests each encoder actually works)
- Adaptive output bitrate based on source quality (no upsampling, no unnecessary downgrade)
- Rich metadata support: author, narrator, year, genre, description
- Two-pass pipeline: encode first, then mux (cleaner, faster)
- Completion sound notification (macOS/Windows/Linux)
- tqdm progress bar during encoding
- Playlist/channel support (multiple videos → one audiobook per video)
- iPod/M4B compatibility flags
- Cross-platform (macOS, Linux, Windows)
"""

import os
import csv
import sys
import shutil
import subprocess
import time
import argparse
import tempfile
import re
from PIL import Image
from pathlib import Path
from datetime import datetime
import pandas as pd
import yt_dlp
from tqdm import tqdm

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────

SUPPORTED_AUDIO_EXTS = {'.mp3', '.mp4', '.m4a', '.flac', '.wav', '.aac', '.ogg', '.opus'}
OUTPUT_FOLDER_NAME   = "Audiobook_Output"

# Bitrate ladder used when recommending CBR targets
CBR_LADDER = [64, 96, 128, 160, 192, 256, 320]

# ─────────────────────────────────────────────
#  FFMPEG DETECTION
# ─────────────────────────────────────────────

def detect_ffmpeg_path():
    for candidate in [shutil.which('ffmpeg'), "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
        if candidate and os.path.exists(candidate):
            return candidate
    raise RuntimeError(
        "FFmpeg not found! Install it:\n"
        "  macOS:   brew install ffmpeg\n"
        "  Linux:   sudo apt install ffmpeg\n"
        "  Windows: https://ffmpeg.org/download.html"
    )

FFMPEG_PATH  = detect_ffmpeg_path()
FFPROBE_PATH = shutil.which('ffprobe') or FFMPEG_PATH.replace('ffmpeg', 'ffprobe')

# ─────────────────────────────────────────────
#  NOTIFICATION SOUND
# ─────────────────────────────────────────────

def play_notification_sound():
    """Play a completion sound — cross-platform."""
    print('\a')
    sys.stdout.flush()
    try:
        if sys.platform == 'darwin':
            subprocess.run(['say', 'Audiobook encoding complete'],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == 'win32':
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        elif sys.platform.startswith('linux'):
            for cmd in [
                ['paplay', '/usr/share/sounds/freedesktop/stereo/complete.oga'],
                ['aplay',  '/usr/share/sounds/sound-icons/finish.wav'],
            ]:
                try:
                    subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=3)
                    break
                except Exception:
                    pass
    except Exception:
        pass

# ─────────────────────────────────────────────
#  ENCODER DETECTION
# ─────────────────────────────────────────────

def detect_best_aac_encoder():
    """
    Test encoders in priority order and return the first one that actually works.
    Priority: aac_at (Apple HW) → libfdk_aac (best SW quality) → aac (FFmpeg native)
    Returns (encoder_name, is_hardware, description)
    """
    candidates = [
        ('aac_at',     True,  'Apple AudioToolbox — hardware accelerated (macOS)'),
        ('libfdk_aac', False, 'Fraunhofer FDK AAC — best quality software encoder'),
        ('aac',        False, 'FFmpeg native AAC — reliable software fallback'),
    ]

    try:
        result = subprocess.run(
            [FFMPEG_PATH, '-hide_banner', '-encoders'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5
        )
        available = result.stdout
    except Exception:
        return ('aac', False, 'FFmpeg native AAC (fallback — could not query encoders)')

    for encoder, is_hw, desc in candidates:
        if encoder not in available:
            continue
        # Validate it actually runs
        try:
            val = subprocess.run(
                [FFMPEG_PATH, '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono',
                 '-t', '0.1', '-c:a', encoder, '-b:a', '64k', '-f', 'null', '-'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5
            )
            if val.returncode == 0:
                return (encoder, is_hw, desc)
        except Exception:
            continue

    return ('aac', False, 'FFmpeg native AAC (ultimate fallback)')

# ─────────────────────────────────────────────
#  QUIET LOGGER
# ─────────────────────────────────────────────

class QuietLogger:
    def debug(self, msg):   pass
    def warning(self, msg): pass
    def error(self, msg):   pass

# ─────────────────────────────────────────────
#  YOUTUBE: BEST QUALITY FORMAT SELECTION
# ─────────────────────────────────────────────

def get_best_audio_format(url):
    """
    Inspect all available audio streams and choose the highest-bitrate one.
    Returns a yt-dlp format string and a quality description dict.
    """
    ydl_opts = {'quiet': True, 'logger': QuietLogger(), 'no_warnings': True}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = info.get('formats', [])
        audio_only = [
            f for f in formats
            if f.get('acodec') not in (None, 'none')
            and f.get('vcodec') in (None, 'none', 'video only')
            and f.get('acodec') != 'video only'
        ]

        if not audio_only:
            return 'bestaudio/best', {'codec': 'unknown', 'abr': 0, 'format_id': 'bestaudio'}

        # Sort: prefer higher abr; break ties by preferring opus > aac > mp4a > other
        codec_pref = {'opus': 0, 'aac': 1, 'mp4a': 1, 'vorbis': 2, 'mp3': 3}

        def sort_key(f):
            abr  = f.get('abr') or f.get('tbr') or 0
            codec = (f.get('acodec') or '').lower()
            pref  = next((v for k, v in codec_pref.items() if k in codec), 99)
            return (-abr, pref)

        audio_only.sort(key=sort_key)
        best = audio_only[0]

        fmt_id  = best.get('format_id', 'bestaudio')
        abr     = best.get('abr') or best.get('tbr') or 0
        codec   = (best.get('acodec') or 'unknown').lower()
        ext     = best.get('ext', 'unknown')

        quality_info = {
            'codec':     codec,
            'abr':       abr,
            'ext':       ext,
            'format_id': fmt_id,
        }

        # Use a specific format ID so yt-dlp picks exactly this stream
        format_str = f'{fmt_id}/bestaudio/best'
        return format_str, quality_info

    except Exception as e:
        print(f"⚠️  Format detection failed ({e}), using bestaudio/best fallback")
        return 'bestaudio/best', {'codec': 'unknown', 'abr': 0, 'format_id': 'bestaudio'}


def pick_output_bitrate(source_abr_kbps: float, encoder: str) -> str:
    """
    Choose the best CBR output bitrate:
    - Never upsample beyond source
    - Pick the closest ladder step at or below source (with a small headroom)
    - Minimum 64k, maximum 256k for audiobooks
    """
    if source_abr_kbps <= 0:
        return '192k'   # Sensible default if detection failed

    # Allow up to 10 % headroom above source to account for measurement noise
    ceiling = source_abr_kbps * 1.10

    # Walk the ladder from high to low; pick the first that fits under the ceiling
    for kbps in reversed(CBR_LADDER):
        if kbps <= ceiling:
            return f'{kbps}k'

    return '64k'   # Below lowest ladder rung → use minimum

# ─────────────────────────────────────────────
#  MEDIA INFO
# ─────────────────────────────────────────────

def get_media_info(file_path: Path) -> dict:
    """Return duration_ms, codec, and bitrate_kbps for an audio file."""
    try:
        dur_out = subprocess.run(
            [FFPROBE_PATH, '-v', 'error',
             '-show_entries', 'format=duration,bit_rate',
             '-of', 'default=noprint_wrappers=1:nokey=0',
             str(file_path)],
            check=True, capture_output=True, text=True
        ).stdout

        duration_ms = 0
        bitrate_kbps = 0
        for line in dur_out.splitlines():
            if line.startswith('duration='):
                try:    duration_ms = int(float(line.split('=')[1]) * 1000)
                except: pass
            if line.startswith('bit_rate='):
                try:    bitrate_kbps = int(line.split('=')[1]) // 1000
                except: pass

        codec_out = subprocess.run(
            [FFPROBE_PATH, '-v', 'error',
             '-select_streams', 'a:0',
             '-show_entries', 'stream=codec_name',
             '-of', 'default=noprint_wrappers=1:nokey=1',
             str(file_path)],
            check=True, capture_output=True, text=True
        ).stdout.strip().lower()

        return {'duration_ms': duration_ms, 'codec': codec_out, 'bitrate_kbps': bitrate_kbps}
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Media analysis failed: {e.stderr}") from e

# ─────────────────────────────────────────────
#  THUMBNAIL
# ─────────────────────────────────────────────

def download_thumbnail(url, folder, raw_title):
    out = os.path.join(folder, f"{raw_title}_thumbnail")
    opts = {
        'skip_download': True,
        'writethumbnail': True,
        'outtmpl': f'{out}.%(ext)s',
        'ffmpeg_location': FFMPEG_PATH,
        'quiet': True,
        'logger': QuietLogger(),
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    for ext in ['jpg', 'png', 'webp', 'bmp']:
        src = f"{out}.{ext}"
        if os.path.exists(src):
            jpg = f"{out}.jpg"
            subprocess.run(
                [FFMPEG_PATH, '-i', src, jpg, '-y'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if src != jpg and os.path.exists(src):
                os.remove(src)
            return jpg
    return None

# ─────────────────────────────────────────────
#  CHAPTERS CSV
# ─────────────────────────────────────────────

def generate_chapters_csv(info, folder, raw_title):
    chapters = info.get('chapters', [])
    if not chapters:
        return None

    csv_path = os.path.join(folder, f"{raw_title}_chapters.csv")
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['start', 'end', 'title'])
        for i, ch in enumerate(chapters):
            s = ch['start_time']
            start = f"{int(s//3600):02}:{int(s%3600//60):02}:{int(s%60):02}"
            if i < len(chapters) - 1:
                e = chapters[i+1]['start_time']
                end = f"{int(e//3600):02}:{int(e%3600//60):02}:{int(e%60):02}"
            else:
                end = ""
            w.writerow([start, end, ch['title']])
    return csv_path

# ─────────────────────────────────────────────
#  AUDIO DOWNLOAD
# ─────────────────────────────────────────────

def download_audio(url, folder, raw_title):
    """Download the absolute best audio stream YouTube has for this video."""
    print("🔍 Inspecting available audio streams...")
    format_str, quality_info = get_best_audio_format(url)

    abr   = quality_info['abr']
    codec = quality_info['codec']
    ext   = quality_info.get('ext', '?')
    print(f"🎵 Best stream: {codec.upper()} @ {abr:.0f} kbps  [{ext}]  (format: {quality_info['format_id']})")

    downloaded = {'file': None}

    def progress_hook(d):
        if d.get('status') == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            if total:
                pct = (d['downloaded_bytes'] / total) * 100
                print(f"\r⬇️  Downloading: {pct:.1f}%  ({d.get('_speed_str','')})  ", end='')
        elif d.get('status') == 'finished':
            print(f"\r✅ Download complete                                   ")
            downloaded['file'] = d.get('filename')

    opts = {
        'format': format_str,
        'outtmpl': os.path.join(folder, f"{raw_title}_audio.%(ext)s"),
        'ffmpeg_location': FFMPEG_PATH,
        'progress_hooks': [progress_hook],
        'quiet': True,
        'logger': QuietLogger(),
        'no_warnings': True,
        # Keep original codec — no forced conversion here; we handle it in encoding step
        'postprocessors': [],
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    return quality_info

# ─────────────────────────────────────────────
#  FULL YOUTUBE VIDEO PROCESSING
# ─────────────────────────────────────────────

def process_youtube_video(url, base_dir, custom_cover=None, custom_title=None, metadata=None):
    """Download audio + thumbnail + chapters for one YouTube URL."""
    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'logger': QuietLogger()}) as ydl:
        info = ydl.extract_info(url, download=False)

    raw_title = (custom_title or info.get('title', 'Youtube_Video')).replace('/', '-')
    folder = os.path.join(base_dir, raw_title)
    os.makedirs(folder, exist_ok=True)

    # Cover image
    if custom_cover:
        ext = '.png' if custom_cover.lower().endswith('.png') else '.jpg'
        dest = os.path.join(folder, f"{raw_title}_thumbnail{ext}")
        shutil.copy2(custom_cover, dest)
        if custom_cover.endswith('_converted.png') and os.path.exists(custom_cover):
            os.remove(custom_cover)
    else:
        print("🖼️  Downloading thumbnail...")
        download_thumbnail(url, folder, raw_title)

    # Chapters CSV
    generate_chapters_csv(info, folder, raw_title)

    # Audio (best quality)
    quality_info = download_audio(url, folder, raw_title)

    # Write metadata file if provided
    if metadata:
        meta_path = os.path.join(folder, f"{raw_title}_meta.txt")
        with open(meta_path, 'w', encoding='utf-8') as f:
            for k, v in metadata.items():
                if v:
                    f.write(f"{k}={v}\n")

    return folder, quality_info

# ─────────────────────────────────────────────
#  AUDIOBOOK CREATION (Two-pass: encode → mux)
# ─────────────────────────────────────────────

def create_audiobook(source_folder: Path, encoder_info: tuple, metadata: dict = None) -> Path:
    """
    Two-pass M4B creation:
      Pass 1 — encode audio to AAC .m4a (with hardware acceleration if available)
      Pass 2 — mux audio + cover + chapters + metadata into final .m4b
    """
    encoder_name, is_hardware, encoder_desc = encoder_info

    audio_files  = [f for f in source_folder.glob('*') if f.suffix.lower() in SUPPORTED_AUDIO_EXTS]
    csv_file     = next(source_folder.glob("*.csv"), None)
    cover_image  = next((f for f in source_folder.glob('*')
                         if f.suffix.lower() in ['.jpg', '.jpeg', '.png']), None)

    if len(audio_files) != 1:
        raise ValueError(f"Expected 1 audio file in {source_folder}, found {len(audio_files)}")
    if not cover_image:
        raise ValueError("Cover image not found in source folder")

    audio_file = audio_files[0]
    output_root = source_folder / OUTPUT_FOLDER_NAME
    output_root.mkdir(exist_ok=True)

    # ── Determine adaptive output bitrate ───────────────────────────────────
    print("\n📊 Analysing source audio quality...")
    media_info   = get_media_info(audio_file)
    source_kbps  = media_info.get('bitrate_kbps', 0)
    source_codec = media_info.get('codec', 'unknown')
    duration_ms  = media_info['duration_ms']
    duration_sec = duration_ms / 1000

    target_bitrate = pick_output_bitrate(source_kbps, encoder_name)
    target_kbps    = int(target_bitrate.rstrip('k'))

    print(f"   Source codec : {source_codec.upper()}")
    print(f"   Source bitrate : ~{source_kbps} kbps")
    print(f"   Output bitrate : {target_bitrate} CBR  {'(matches source ceiling)' if target_kbps < source_kbps else ''}")
    print(f"   Encoder : {encoder_desc}")
    hw_tag = "⚡ Hardware" if is_hardware else "🖥️  Software"
    print(f"   Mode : {hw_tag}")

    # ── Build chapter metadata ───────────────────────────────────────────────
    metadata_file = None
    has_chapters  = csv_file is not None

    if has_chapters:
        try:
            df = pd.read_csv(csv_file)
            missing = {'start', 'end', 'title'} - set(df.columns)
            if missing:
                raise ValueError(f"Missing CSV columns: {missing}")

            def parse_time(t):
                clean = str(t).replace(',', '.').strip()
                parts = list(map(float, clean.split(':')))
                mults = [1000, 60000, 3600000]
                return int(sum(p * mults[i] for i, p in enumerate(reversed(parts))))

            segments = []
            for _, row in df.iterrows():
                start = parse_time(row['start'])
                end   = parse_time(row['end']) if pd.notna(row['end']) and row['end'] != "" else None
                segments.append((start, end, str(row['title']).strip()))

            if segments and segments[-1][1] is None:
                segments[-1] = (segments[-1][0], duration_ms, segments[-1][2])

            metadata_file = output_root / "metadata.txt"
            with open(metadata_file, 'w', encoding='utf-8-sig') as mf:
                mf.write(";FFMETADATA1\n")
                # Book-level tags
                if metadata:
                    tag_map = {
                        'title':        'title',
                        'author':       'artist',
                        'album':        'album',
                        'narrator':     'composer',
                        'year':         'date',
                        'genre':        'genre',
                        'description':  'comment',
                    }
                    for key, tag in tag_map.items():
                        val = metadata.get(key)
                        if val:
                            mf.write(f"{tag}={val}\n")
                    # album_artist duplicate of author
                    if metadata.get('author'):
                        mf.write(f"album_artist={metadata['author']}\n")
                mf.write("\n")
                for start, end, title in segments:
                    mf.write(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={start}\nEND={end}\ntitle={title}\n\n")

        except Exception as e:
            print(f"⚠️  Chapter processing failed: {e} — creating audiobook without chapters")
            has_chapters  = False
            metadata_file = None

    # ── PASS 1: Encode audio ─────────────────────────────────────────────────
    encoded_audio = output_root / "encoded_audio.m4a"
    encode_cmd = [
        FFMPEG_PATH, '-y',
        '-i', str(audio_file),
        '-vn',
        '-c:a', encoder_name,
        '-b:a', target_bitrate,
        str(encoded_audio)
    ]

    print(f"\n{'⚡' if is_hardware else '🖥️ '} Encoding audio ({target_bitrate} CBR)...")
    enc_start = time.time()

    pbar = tqdm(total=int(duration_sec), unit='s', desc="Encoding", ncols=70)
    proc = subprocess.Popen(
        encode_cmd + ['-progress', 'pipe:1', '-nostats'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    last_sec = 0
    for line in proc.stdout:
        if 'out_time_ms=' in line:
            try:
                ms  = int(line.split('=')[1].strip())
                cur = min(ms // 1000, int(duration_sec))
                pbar.update(cur - last_sec)
                last_sec = cur
            except ValueError:
                pass
    proc.wait()
    pbar.close()

    if proc.returncode != 0:
        # Fallback to native aac
        print("⚠️  Encoder failed, falling back to native aac...")
        encode_cmd[encode_cmd.index(encoder_name)] = 'aac'
        subprocess.run(encode_cmd, check=True, capture_output=True)

    enc_elapsed = time.time() - enc_start
    speed = duration_sec / enc_elapsed if enc_elapsed > 0 else 0
    print(f"✅ Encoded in {enc_elapsed:.1f}s  ({speed:.1f}x realtime)")

    # ── PASS 2: Mux into M4B ─────────────────────────────────────────────────
    final_output = output_root / f"{source_folder.name}.m4b"
    mux_cmd = [FFMPEG_PATH, '-y',
               '-i', str(encoded_audio),
               '-i', str(cover_image)]

    if has_chapters and metadata_file:
        mux_cmd += ['-f', 'ffmetadata', '-i', str(metadata_file),
                    '-map_metadata', '2', '-map_chapters', '2']

    mux_cmd += [
        '-map', '0:a', '-map', '1:v',
        '-c', 'copy',
        '-disposition:v:0', 'attached_pic',
        '-movflags', '+faststart',
        '-brand', 'M4B ',
        '-f', 'mp4',
        str(final_output)
    ]

    print("📦 Muxing into M4B (chapters + cover + metadata)...")
    result = subprocess.run(mux_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"⚠️  Mux error: {result.stderr[-500:]}")
        raise RuntimeError("Muxing failed")

    # Cleanup intermediates
    encoded_audio.unlink(missing_ok=True)
    if metadata_file and metadata_file.exists():
        metadata_file.unlink()

    return final_output

# ─────────────────────────────────────────────
#  CUSTOM CHAPTER TIMESTAMP HELPERS
# ─────────────────────────────────────────────

def parse_timestamps(text):
    pattern = re.compile(r'(\d{1,2}:\d{2}:\d{2})\s*[-–]\s*(.+)')
    result = []
    for line in text.strip().splitlines():
        m = pattern.match(line.strip())
        if m:
            result.append((m.group(1), m.group(2).strip()))
        elif line.strip():
            print(f"  ⚠️  Could not parse: '{line}'")
    return result

def seconds_to_hms(s):
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02}:{m:02}:{sec:02}"

def hms_to_seconds(t):
    parts = [int(x) for x in t.strip().split(':')]
    if len(parts) == 3:   return parts[0]*3600 + parts[1]*60 + parts[2]
    if len(parts) == 2:   return parts[0]*60 + parts[1]
    return parts[0]

def write_custom_chapters_csv(chapters, folder, raw_title, total_sec):
    parsed = sorted([(hms_to_seconds(t), title) for t, title in chapters])
    rows = []
    for i, (start, title) in enumerate(parsed):
        end = parsed[i+1][0] if i < len(parsed)-1 else total_sec
        rows.append([seconds_to_hms(start), seconds_to_hms(end), title])

    csv_path = os.path.join(folder, f"{raw_title}_chapters.csv")
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['start', 'end', 'title'])
        w.writerows(rows)
    return csv_path

# ─────────────────────────────────────────────
#  INTERACTIVE UI HELPERS
# ─────────────────────────────────────────────

def ask_cover(youtube_title):
    """Return path to custom cover, or None to use YouTube thumbnail."""
    while True:
        choice = input("Use the video's thumbnail as cover? (yes/no): ").strip().lower()
        if choice == 'yes':
            return None
        if choice == 'no':
            path = input("Path to cover image (JPG or PNG): ").strip()
            if not os.path.isfile(path):
                print("  File not found, try again.")
                continue
            try:
                with Image.open(path) as im:
                    fmt = im.format.lower()
                if fmt == 'jpeg':
                    new = os.path.splitext(path)[0] + '_converted.png'
                    with Image.open(path) as im:
                        im.save(new, 'PNG')
                    print(f"  Converted to PNG: {new}")
                    return new
                elif fmt == 'png':
                    return path
                else:
                    print(f"  Unsupported format '{fmt}'. Use JPG or PNG.")
            except Exception as e:
                print(f"  Image error: {e}")
        else:
            print("  Please answer yes or no.")

def ask_title(youtube_title):
    while True:
        choice = input(f"Use YouTube title '{youtube_title}'? (yes/no): ").strip().lower()
        if choice == 'yes':
            return youtube_title
        if choice == 'no':
            t = input("Enter audiobook title: ").strip()
            if t:
                return t
            print("  Title cannot be empty.")
        else:
            print("  Please answer yes or no.")

def ask_metadata():
    """Collect optional rich metadata from the user."""
    print("\n--- Optional Metadata (press Enter to skip) ---")
    author      = input("Author name           : ").strip() or None
    narrator    = input("Narrator name         : ").strip() or None
    year        = input("Year (e.g. 2024)      : ").strip() or None
    genre       = input("Genre/Category        : ").strip() or None
    description = input("Description/Comment   : ").strip() or None
    return {
        'author':      author,
        'narrator':    narrator,
        'year':        year,
        'genre':       genre,
        'description': description,
    }

def ask_chapters():
    """Ask user for custom chapters; return list of (time, title) or None."""
    choice = input("Do you have custom chapter timestamps? (yes/no): ").strip().lower()
    if choice != 'yes':
        print("  Using YouTube chapter metadata if available.")
        return None

    mode = input("Paste timestamps (P) or provide a file path (F)? [P/F]: ").strip().lower()
    if mode == 'f':
        path = input("File path: ").strip()
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                text = fh.read()
        except Exception as e:
            print(f"  Error reading file: {e}")
            return None
    else:
        print("Paste timestamps (HH:MM:SS - Title), one per line. Empty line to finish:")
        lines = []
        while True:
            line = input()
            if not line.strip():
                break
            lines.append(line)
        text = "\n".join(lines)

    chapters = parse_timestamps(text)
    if chapters:
        print(f"✅ Parsed {len(chapters)} chapter timestamps:")
        for t, title in chapters[:3]:
            print(f"   {t} - {title}")
        if len(chapters) > 3:
            print(f"   … and {len(chapters)-3} more")
    else:
        print("⚠️  No valid timestamps parsed.")
    return chapters or None

# ─────────────────────────────────────────────
#  PLAYLIST SUPPORT
# ─────────────────────────────────────────────

def expand_urls(raw_url):
    """Return a list of individual video URLs from a URL (handles playlists)."""
    opts = {
        'quiet': True, 'logger': QuietLogger(), 'no_warnings': True,
        'extract_flat': True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(raw_url, download=False)

        if info.get('_type') == 'playlist':
            entries = info.get('entries', [])
            urls = [e.get('url') or e.get('webpage_url') or f"https://www.youtube.com/watch?v={e['id']}"
                    for e in entries if e]
            print(f"📋 Playlist detected: {len(urls)} video(s)")
            return urls
        else:
            return [raw_url]
    except Exception as e:
        print(f"⚠️  URL inspection failed ({e}), treating as single video")
        return [raw_url]

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="YouTube to Chapterized Audiobook Converter v8")
    parser.add_argument("--url", help="YouTube video or playlist URL")
    parser.add_argument("--no-notification", action='store_true', help="Disable completion sound")
    args = parser.parse_args()

    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║   🎧  YouTube → Audiobook Converter  v8  (Best Quality Edition) ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    # ── Encoder detection ──────────────────────────────────────────────────
    print("\n🔍 Detecting best AAC encoder...")
    encoder_info = detect_best_aac_encoder()
    enc_name, enc_hw, enc_desc = encoder_info
    hw_label = "⚡ Hardware" if enc_hw else "🖥️  Software"
    print(f"   {hw_label} → {enc_desc}")

    # ── URL input ──────────────────────────────────────────────────────────
    raw_url = (args.url or input("\n📺 Enter YouTube URL (video or playlist): ")).strip()

    urls = expand_urls(raw_url)
    if not urls:
        print("❌ No valid URLs found.")
        sys.exit(1)

    # For playlist: shared metadata / chapters only make sense per-video
    # For single video: ask everything
    is_playlist = len(urls) > 1

    # ── Per-run options (applies to all videos in playlist) ────────────────
    print("\n--- Cover Image ---")
    if is_playlist:
        print("  (Playlist mode: YouTube thumbnails will be used for each video)")
        shared_cover = None
    else:
        # Peek at first video title
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'logger': QuietLogger()}) as ydl:
            peek = ydl.extract_info(urls[0], download=False)
        yt_title = peek.get('title', 'Youtube_Video')
        duration = peek.get('duration', 0)
        print(f"\n📺 Video  : {yt_title}")
        print(f"⏱️  Duration: {seconds_to_hms(duration)}")
        shared_cover = ask_cover(yt_title)

    print("\n--- Metadata ---")
    shared_meta = ask_metadata()

    # ── Process each video ─────────────────────────────────────────────────
    total_start = time.time()
    produced = []

    for idx, url in enumerate(urls, 1):
        if is_playlist:
            print(f"\n{'═'*68}")
            print(f"  Video {idx}/{len(urls)}: {url}")
            print(f"{'═'*68}")

        # Get info for this video
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'logger': QuietLogger()}) as ydl:
            info = ydl.extract_info(url, download=False)

        yt_title = info.get('title', 'Youtube_Video')
        duration = info.get('duration', 0)

        if not is_playlist:
            print("\n--- Title ---")
            custom_title = ask_title(yt_title)
        else:
            custom_title = yt_title  # Use YouTube title per video in playlists

        # Merge YouTube title into metadata album field if not set
        meta = dict(shared_meta)
        if not meta.get('title'):
            meta['title'] = custom_title
        meta['album'] = meta.get('album') or custom_title

        # Chapter options (per video, skip for playlists)
        custom_chapters = None
        if not is_playlist:
            print("\n--- Chapters ---")
            custom_chapters = ask_chapters()

        try:
            with tempfile.TemporaryDirectory() as tmp:
                print(f"\n🚀 Processing: {custom_title}")

                folder, quality_info = process_youtube_video(
                    url,
                    base_dir=tmp,
                    custom_cover=shared_cover if not is_playlist else None,
                    custom_title=custom_title,
                    metadata=meta,
                )

                # Override chapters if user provided custom ones
                if custom_chapters:
                    raw_title   = os.path.basename(folder)
                    audio_files = list(Path(folder).glob('*'))
                    audio_files = [f for f in audio_files if f.suffix.lower() in SUPPORTED_AUDIO_EXTS]
                    if audio_files:
                        mi = get_media_info(audio_files[0])
                        total_sec = mi['duration_ms'] / 1000
                        # Remove auto-generated CSV
                        auto = os.path.join(folder, f"{raw_title}_chapters.csv")
                        if os.path.exists(auto):
                            os.remove(auto)
                        write_custom_chapters_csv(custom_chapters, folder, raw_title, total_sec)
                        print(f"📖 Applied {len(custom_chapters)} custom chapters")

                print("\n📚 Creating M4B audiobook...")
                m4b_path = create_audiobook(Path(folder), encoder_info, metadata=meta)

                # Move to cwd
                final = Path(os.getcwd()) / m4b_path.name
                shutil.move(str(m4b_path), str(final))
                produced.append(final)

                size_mb = final.stat().st_size / (1024 * 1024)
                print(f"\n✅ Done: {final.name}  ({size_mb:.1f} MB)")

        except Exception as e:
            print(f"\n❌ Failed for '{custom_title}': {e}")
            if not is_playlist:
                sys.exit(1)

    # ── Summary ────────────────────────────────────────────────────────────
    elapsed = time.time() - total_start
    print(f"\n{'═'*68}")
    print(f"🎉 All done!  {len(produced)}/{len(urls)} audiobook(s) created")
    print(f"⏱️  Total time: {int(elapsed//60)}m {elapsed%60:.1f}s")
    for p in produced:
        print(f"   📁 {p}")
    print(f"{'═'*68}")

    if not args.no_notification:
        play_notification_sound()


if __name__ == "__main__":
    main()