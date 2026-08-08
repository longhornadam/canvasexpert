"""Local-only laws and one example for ordinary media-recording evidence."""
from __future__ import annotations

import subprocess
import wave

import pytest

from api.powergrader import media_recordings, session_builder


def _wav(path):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * 16000)


@pytest.mark.parametrize(("media_type", "content_type"), [("audio", "audio/mp4"), ("video", "video/mp4")])
def test_documented_canvas_media_comment_categories_are_accepted(media_type, content_type):
    source, held = media_recordings.normalize_media_comment({
        "media_id": "synthetic-media", "display_name": "synthetic", "media_type": media_type,
        "content-type": content_type, "url": "https://canvas.invalid/signed",
    })
    assert held is None
    assert source["declared_media_type"] == content_type
    assert source["content_indicator"] == {
        "media_id": "synthetic-media", "display_name": "synthetic", "media_type": media_type,
        "content-type": content_type,
    }


def test_audio_and_video_are_private_originals_with_canonical_audio(tmp_path):
    original = tmp_path / "synthetic.wav"
    canonical = tmp_path / "synthetic.canonical.wav"
    _wav(original)
    source = {"media_id": "media-1", "filename": "synthetic.wav", "attempt": 1,
              "declared_media_type": "audio/wav", "content_indicator": {"media_id": "media-1"}}
    audio = media_recordings.finalize_recording(source=source, original_path=str(original), canonical_path=str(canonical))
    assert audio["download_status"] == "downloaded"
    assert original.exists() and canonical.exists()
    assert audio["duration_seconds"] == 1.0
    assert audio["canonical_sha256"]

    video = tmp_path / "synthetic.mp4"
    video_canonical = tmp_path / "synthetic-video.canonical.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=8x8:d=1",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest", str(video)], check=True)
    converted = media_recordings.finalize_recording(
        source={**source, "media_id": "media-2", "filename": "synthetic.mp4", "declared_media_type": "video/mp4"},
        original_path=str(video), canonical_path=str(video_canonical),
    )
    assert converted["download_status"] == "downloaded"
    assert video.exists() and video_canonical.exists()


def test_missing_source_is_held_and_url_never_reaches_review_projection():
    source, held = media_recordings.normalize_media_comment({"media_id": "m-1", "display_name": "synthetic", "media_type": "audio/wav"})
    assert source is None
    assert held["error_code"] == "media_source_missing"
    record = {
        "media_recording": True, "filename": "synthetic.wav", "item_id": "m-1", "attempt": 1,
        "download_status": "downloaded", "extraction_status": "validated", "duration_seconds": 4.2,
        "original_path": "C:/private/original.wav", "canonical_path": "C:/private/audio.wav",
        "url": "https://canvas.invalid/signed", "authorization": "secret",
    }
    projected = session_builder._attachment_metadata(record)
    assert projected["media_recording"] is True
    assert projected["stream_key"] == media_recordings.stream_key("m-1")
    assert not ({"url", "authorization", "original_path", "canonical_path", "item_id"} & set(projected))
