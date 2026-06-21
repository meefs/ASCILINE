"""Unit tests for ytdl.expand_playlist parsing (no network — _ytdlp is mocked)."""
import json
import subprocess
from unittest import mock

import ytdl


def _cp(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode,
                                       stdout=stdout, stderr=stderr)


def test_expand_playlist_returns_each_entry_url():
    info = {
        "_type": "playlist",
        "entries": [
            {"id": "aaa", "url": "https://www.youtube.com/watch?v=aaa"},
            {"id": "bbb", "url": "https://www.youtube.com/watch?v=bbb"},
        ],
    }
    with mock.patch.object(ytdl, "_ytdlp", return_value=_cp(json.dumps(info))):
        assert ytdl.expand_playlist("https://youtube.com/playlist?list=PL") == [
            "https://www.youtube.com/watch?v=aaa",
            "https://www.youtube.com/watch?v=bbb",
        ]


def test_expand_playlist_builds_url_from_bare_id():
    # Some yt-dlp versions emit a bare id in 'url' for flat entries.
    info = {"_type": "playlist", "entries": [{"id": "xyz", "url": "xyz"}]}
    with mock.patch.object(ytdl, "_ytdlp", return_value=_cp(json.dumps(info))):
        assert ytdl.expand_playlist("https://youtube.com/playlist?list=PL") == [
            "https://www.youtube.com/watch?v=xyz",
        ]


def test_expand_playlist_single_video_returns_input_unchanged():
    info = {"_type": "video", "id": "single"}
    url = "https://youtu.be/single"
    with mock.patch.object(ytdl, "_ytdlp", return_value=_cp(json.dumps(info))):
        assert ytdl.expand_playlist(url) == [url]


def test_expand_playlist_falls_back_on_ytdlp_failure():
    url = "https://youtu.be/whatever"
    with mock.patch.object(ytdl, "_ytdlp", return_value=_cp("", returncode=1, stderr="boom")):
        assert ytdl.expand_playlist(url) == [url]


def test_expand_playlist_falls_back_on_bad_json():
    url = "https://youtu.be/whatever"
    with mock.patch.object(ytdl, "_ytdlp", return_value=_cp("not json{")):
        assert ytdl.expand_playlist(url) == [url]


def test_expand_playlist_skips_unusable_entries():
    info = {"_type": "playlist", "entries": [{"title": "no id or url"},
                                             {"id": "ok"}]}
    with mock.patch.object(ytdl, "_ytdlp", return_value=_cp(json.dumps(info))):
        assert ytdl.expand_playlist("https://youtube.com/playlist?list=PL") == [
            "https://www.youtube.com/watch?v=ok",
        ]
