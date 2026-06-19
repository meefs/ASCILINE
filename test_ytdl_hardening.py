"""
Hardening tests for ytdl: missing dependency, livestreams, atomic caching,
and audio-only sources. All but one are offline (yt-dlp/ffprobe are mocked).
"""
import shutil
import subprocess
from unittest import mock

import pytest

import ytdl


def _cp(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode,
                                       stdout=stdout, stderr=stderr)


def test_missing_ytdlp_gives_actionable_error(tmp_path):
    with mock.patch("importlib.util.find_spec", return_value=None):
        with pytest.raises(RuntimeError, match="pip install yt-dlp"):
            ytdl.download("https://youtu.be/x", cache_dir=str(tmp_path))


def test_download_rejects_livestream(tmp_path):
    # _probe_remote sees id on line 1, is_live=True on line 2.
    with mock.patch("importlib.util.find_spec", return_value=object()), \
         mock.patch.object(ytdl, "_ytdlp", return_value=_cp("vid123\nTrue\n")):
        with pytest.raises(RuntimeError, match="live stream"):
            ytdl.download("https://youtu.be/live", cache_dir=str(tmp_path))


def test_download_is_atomic_on_normalize_failure(tmp_path):
    """A failed normalize must leave no cache file a later run would trust."""
    out = tmp_path / "vid123.mp4"

    def fake_ytdlp(*args, **kwargs):
        if "is_live" in args:                 # _probe_remote
            return _cp("vid123\nFalse\n")
        if "-o" in args:                      # the download itself
            target = args[args.index("-o") + 1]
            with open(target, "wb") as f:     # simulate a downloaded file
                f.write(b"\x00\x00")
            return _cp("ok")
        return _cp("")

    with mock.patch("importlib.util.find_spec", return_value=object()), \
         mock.patch.object(ytdl, "_ytdlp", side_effect=fake_ytdlp), \
         mock.patch.object(ytdl, "normalize", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            ytdl.download("https://youtu.be/x", cache_dir=str(tmp_path))

    assert not out.exists()                          # no poisoned cache
    assert not (tmp_path / "vid123.mp4.part.mp4").exists()  # temp cleaned up


def test_cached_file_short_circuits_without_download(tmp_path):
    out = tmp_path / "vid123.mp4"
    out.write_bytes(b"already here")

    def fake_ytdlp(*args, **kwargs):
        if "is_live" in args:
            return _cp("vid123\nFalse\n")
        raise AssertionError("must not download when cached")

    with mock.patch("importlib.util.find_spec", return_value=object()), \
         mock.patch.object(ytdl, "_ytdlp", side_effect=fake_ytdlp):
        assert ytdl.download("https://youtu.be/x", cache_dir=str(tmp_path)) == str(out)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")
def test_normalize_rejects_audio_only(tmp_path):
    audio = tmp_path / "audio_only.mp4"
    r = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-c:a", "aac", "-loglevel", "error", str(audio)],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    with pytest.raises(RuntimeError, match="no video stream"):
        ytdl.normalize(str(audio))
