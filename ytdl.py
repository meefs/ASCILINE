"""
ytdl.py — Resolve YouTube (and other yt-dlp-supported) URLs to a local file
that the ASCILINE engine can ALWAYS open.

ASCILINE downscales every frame to a tiny character grid, so there is no point
pulling high resolution. We cap at <=480p and produce a single mp4 with audio
(the /audio endpoint runs ffmpeg on the same file). Downloads are cached in
videos/ by video id so re-runs are instant.

Robustness contract (why this file is more than a one-liner):
  The engine reads frames with OpenCV (cv2.VideoCapture) and extracts audio with
  ffmpeg. Both break on the files YouTube actually serves:
    * Best-quality audio is often Opus/WebM. Muxed into mp4 it is a NON-STANDARD
      file that OpenCV/ffmpeg can choke on -> /audio fails or playback crashes.
    * Best-quality video is often VP9/AV1, which OpenCV cannot decode without
      hardware support.
    * YouTube content is frequently variable-frame-rate (VFR). The engine's whole
      timing model assumes a single constant FPS (frame_t = 1/fps), so VFR makes
      cv2's CAP_PROP_FPS unreliable and playback drifts / "the FPS count breaks".
  So after download we PROBE the file with ffprobe and, unless it is already
  H.264 + AAC + constant-frame-rate, we normalize it to exactly that. The engine
  is left untouched: it only ever sees clean, canonical mp4s.
"""
import os
import sys
import json
import shutil
import importlib.util
import subprocess

_URL_HINTS = ("http://", "https://", "youtube.com", "youtu.be")

# What the engine can open without surprises.
_OK_VCODEC = "h264"
_OK_ACODEC = "aac"

# Subprocess guards so a stuck source can never hang the server.
_DL_TIMEOUT = 900      # yt-dlp download of a <=480p clip
_PROBE_TIMEOUT = 60    # ffprobe / metadata reads
_ENCODE_TIMEOUT = 1800  # ffmpeg re-encode of a long video


def is_url(s: str) -> bool:
    s = s.lower()
    return s.startswith(("http://", "https://")) or "youtube.com" in s or "youtu.be" in s


def _entry_url(entry: dict) -> str | None:
    """Best-effort downloadable URL for a single flat-playlist entry."""
    url = entry.get("url") or entry.get("webpage_url")
    if url and "/" in url:          # already a full URL
        return url
    vid = entry.get("id") or url    # bare video id (common for YouTube)
    if vid:
        return f"https://www.youtube.com/watch?v={vid}"
    return None


def expand_playlist(url: str) -> list[str]:
    """
    Expand a playlist/channel URL into a list of individual video URLs.

    Uses `--flat-playlist` so it only reads the index (no per-video download).
    Returns ``[url]`` unchanged for a single video, or if expansion fails for
    any reason, so the caller can still attempt a normal single download.
    """
    _require_ytdlp()
    res = _ytdlp("--flat-playlist", "-J", url, timeout=_PROBE_TIMEOUT)
    if res.returncode != 0 or not res.stdout.strip():
        return [url]
    try:
        info = json.loads(res.stdout)
    except json.JSONDecodeError:
        return [url]
    if info.get("_type") != "playlist":
        return [url]
    urls = [u for u in (_entry_url(e) for e in info.get("entries") or []) if u]
    return urls or [url]


def _require_ytdlp() -> None:
    """Fail early with an actionable message instead of a cryptic import error."""
    if importlib.util.find_spec("yt_dlp") is None:
        raise RuntimeError("yt-dlp is not installed. Install it with: pip install yt-dlp")


def _ytdlp(*args: str, timeout: int = _DL_TIMEOUT) -> subprocess.CompletedProcess:
    # Use the running interpreter's yt_dlp so it always matches the venv.
    try:
        return subprocess.run([sys.executable, "-m", "yt_dlp", *args],
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"yt-dlp timed out after {timeout}s")


def _probe_remote(url: str) -> tuple[str, bool]:
    """Return (video_id, is_live) for a single video URL, without downloading."""
    res = _ytdlp("--no-playlist", "--print", "id", "--print", "is_live", url,
                 timeout=_PROBE_TIMEOUT)
    if res.returncode != 0 or not res.stdout.strip():
        raise RuntimeError(f"yt-dlp could not read {url!r}: {res.stderr.strip()[:200]}")
    lines = res.stdout.strip().splitlines()
    video_id = lines[0].strip()
    is_live = len(lines) > 1 and lines[1].strip().lower() == "true"
    return video_id, is_live


def download(url: str, cache_dir: str = "videos") -> str:
    """Download `url` (<=480p) into cache_dir as a canonical mp4 and return the path."""
    _require_ytdlp()
    os.makedirs(cache_dir, exist_ok=True)

    video_id, is_live = _probe_remote(url)
    if is_live:
        raise RuntimeError(
            f"{url!r} is a live stream; ASCILINE plays finite videos only")

    out = os.path.join(cache_dir, f"{video_id}.mp4")
    # A file at `out` is only ever created by the atomic rename below, so its
    # mere existence guarantees a complete, already-normalized video.
    if os.path.exists(out):
        print(f"[YT] cached: {out}")
        return out

    print(f"[YT] downloading {url}  (<=480p) ...")
    # Bias the selection toward a clean container in the first place: H.264 video
    # (avc1) that OpenCV decodes everywhere, paired with AAC audio (mp4a) that is
    # standard inside mp4. Each fallback widens what we accept; normalize() below
    # repairs whatever the chosen format could not give us cleanly.
    fmt = ("bv*[vcodec^=avc1][height<=480]+ba[acodec^=mp4a]/"  # avc1 + aac  -> clean
           "bv*[vcodec^=avc1][height<=480]+ba/"                # avc1 + any audio
           "b[vcodec^=avc1][height<=480]/"                     # progressive avc1
           "bv*[height<=480]+ba/b[height<=480]/b")             # last resort

    # Download + normalize into a temp file, then atomically rename. An
    # interruption (crash, Ctrl-C, full disk) leaves only the temp file, never a
    # half-written `out` that a later run would mistake for a good cache hit.
    tmp = out + ".part.mp4"
    _unlink(tmp)
    try:
        res = _ytdlp("--no-playlist", "-f", fmt,
                     "--merge-output-format", "mp4", "-o", tmp, url)
        if res.returncode != 0 or not os.path.exists(tmp):
            raise RuntimeError(f"yt-dlp download failed: {res.stderr.strip()[-300:]}")
        normalize(tmp)
        os.replace(tmp, out)        # atomic finalize
    except BaseException:
        _unlink(tmp)
        raise

    print(f"[YT] saved: {out}")
    return out


def _unlink(path: str) -> None:
    """Best-effort remove; never raises (used in cleanup paths)."""
    try:
        os.remove(path)
    except OSError:
        pass


# ── format normalization ────────────────────────────────────────────────────

def _probe(path: str) -> dict:
    """
    Return {'vcodec','acodec','fps','cfr'} via ffprobe.

    fps is the *average* real frame rate (avg_frame_rate); cfr is True only when
    the container's nominal rate (r_frame_rate) matches the average, i.e. the
    file is genuinely constant-frame-rate and safe for the engine's timing model.
    """
    info = {"vcodec": None, "acodec": None, "fps": None, "cfr": False}
    if not shutil.which("ffprobe"):
        return info
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,codec_name,r_frame_rate,avg_frame_rate",
             "-of", "json", path],
            capture_output=True, text=True, timeout=_PROBE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return info
    if res.returncode != 0:
        return info
    try:
        streams = json.loads(res.stdout).get("streams", [])
    except json.JSONDecodeError:
        return info
    for st in streams:
        if st.get("codec_type") == "video" and info["vcodec"] is None:
            info["vcodec"] = st.get("codec_name")
            r_fps = _ratio(st.get("r_frame_rate"))
            a_fps = _ratio(st.get("avg_frame_rate"))
            info["fps"] = a_fps or r_fps
            # CFR when both rates are known and agree within rounding.
            info["cfr"] = bool(r_fps and a_fps and abs(r_fps - a_fps) < 0.01)
        elif st.get("codec_type") == "audio" and info["acodec"] is None:
            info["acodec"] = st.get("codec_name")
    return info


def _ratio(s: str | None) -> float | None:
    """Parse ffprobe rationals like '30000/1001' -> 29.97; '0/0' -> None."""
    if not s or "/" not in s:
        return None
    num, den = s.split("/", 1)
    try:
        num_f, den_f = float(num), float(den)
    except ValueError:
        return None
    return num_f / den_f if den_f else None


def normalize(path: str) -> bool:
    """
    Ensure `path` is a canonical mp4 the engine can always open:
    H.264 video + AAC audio (or no audio) at a constant frame rate.

    Fast path: if the file already satisfies the contract, do nothing and return
    False. Otherwise transcode in place and return True. Re-encoding is the only
    reliable way to repair VP9/AV1 video, Opus-in-mp4 audio, and VFR timing — a
    plain remux cannot.
    """
    info = _probe(path)
    if info["vcodec"] is None:
        # No decodable video stream — nothing ASCILINE can render.
        what = "audio-only source" if info["acodec"] else "unreadable file"
        raise RuntimeError(f"{path!r}: no video stream ({what})")
    has_audio = info["acodec"] is not None
    clean = (info["vcodec"] == _OK_VCODEC
             and (not has_audio or info["acodec"] == _OK_ACODEC)
             and info["cfr"])
    if clean and _decodable(path):
        return False

    reason = []
    if info["vcodec"] != _OK_VCODEC:
        reason.append(f"video={info['vcodec']}")
    if has_audio and info["acodec"] != _OK_ACODEC:
        reason.append(f"audio={info['acodec']}")
    if not info["cfr"]:
        reason.append("vfr")
    print(f"[YT] normalizing ({', '.join(reason) or 'unreadable'}) -> H.264/AAC/CFR ...")
    _transcode(path, fps=info["fps"], has_audio=has_audio)
    return True


def _decodable(path: str) -> bool:
    """True if OpenCV can actually read the first frame (last-ditch sanity check)."""
    try:
        import cv2
    except ImportError:
        return True  # can't check; assume fine
    cap = cv2.VideoCapture(path)
    ok, _ = cap.read()
    cap.release()
    return ok


def _transcode(path: str, fps: float | None, has_audio: bool) -> None:
    """Transcode in place to H.264 + AAC at a constant frame rate."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found; cannot normalize downloaded video")
    tmp = path + ".norm.mp4"
    # -fps_mode cfr + an explicit -r force a constant frame rate so the engine's
    # 1/fps timing stays in sync; yuv420p keeps OpenCV/browsers happy.
    rate = f"{fps:.6f}" if fps and fps > 0 else "30"
    cmd = ["ffmpeg", "-y", "-i", path,
           "-map", "0:v:0",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
           "-pix_fmt", "yuv420p", "-r", rate, "-fps_mode", "cfr"]
    if has_audio:
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "128k"]
    else:
        cmd += ["-an"]
    cmd += ["-movflags", "+faststart", "-loglevel", "error", tmp]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=_ENCODE_TIMEOUT)
    except subprocess.TimeoutExpired:
        _unlink(tmp)
        raise RuntimeError(f"normalize timed out after {_ENCODE_TIMEOUT}s")
    if res.returncode != 0 or not os.path.exists(tmp):
        _unlink(tmp)
        raise RuntimeError(f"normalize failed: {res.stderr.strip()[-300:]}")
    os.replace(tmp, path)
