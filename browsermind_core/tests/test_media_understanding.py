"""Tests for MediaAnalyzer and AnalysisResult.

Covers:
  - AnalysisResult.to_dict keys
  - analyze() no local_path → error set
  - analyze() file not found → error set
  - analyze() returns file_size
  - _dhash produces non-empty hex string (PIL skip if absent)
  - _dominant_colors returns list of hex strings (PIL skip if absent)
  - analyze_and_update() writes into asset.understanding
  - analyze_and_update() writes exif into asset.metadata
  - vision_backend is called when provided
  - video analysis without ffprobe → no error, codec is None
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


def _pil_available() -> bool:
    try:
        import PIL
        return True
    except ImportError:
        return False


# ── AnalysisResult.to_dict ────────────────────────────────────────────────────

def test_analysis_result_to_dict_keys():
    from browsermind_core.media.understanding.analyzer import AnalysisResult
    r    = AnalysisResult(content_hash="abc", media_type="image")
    d    = r.to_dict()
    keys = {"content_hash", "media_type", "file_size", "dimensions",
            "duration_seconds", "dominant_colors", "perceptual_hash",
            "ocr_text", "exif", "codec"}
    assert keys.issubset(d.keys())


# ── Error cases ───────────────────────────────────────────────────────────────

def test_analyze_no_local_path():
    from browsermind_core.media.understanding.analyzer import MediaAnalyzer
    from browsermind_core.media.media_asset import MediaAsset
    asset  = MediaAsset.from_bytes(b"x", source_url="https://x.com/x")
    result = MediaAnalyzer().analyze(asset)
    assert result.error is not None
    assert "local_path" in result.error


def test_analyze_file_not_found(tmp_path):
    from browsermind_core.media.understanding.analyzer import MediaAnalyzer
    from browsermind_core.media.media_asset import MediaAsset
    asset            = MediaAsset.from_bytes(b"x", source_url="https://x.com/x")
    asset.local_path = str(tmp_path / "nonexistent.png")
    result           = MediaAnalyzer().analyze(asset)
    assert result.error is not None
    assert "not found" in result.error.lower() or "File" in result.error


# ── File size ─────────────────────────────────────────────────────────────────

def test_analyze_returns_file_size(tmp_path):
    from browsermind_core.media.understanding.analyzer import MediaAnalyzer
    from browsermind_core.media.media_asset import MediaAsset, MediaType
    p = tmp_path / "test.png"
    p.write_bytes(b"x" * 500)
    asset = MediaAsset.from_bytes(b"x" * 500, source_url="https://x.com/x",
                                  media_type=MediaType.IMAGE)
    asset.local_path = str(p)
    result = MediaAnalyzer().analyze(asset)
    assert result.file_size == 500


# ── Perceptual hash ───────────────────────────────────────────────────────────

@pytest.mark.skipif(not _pil_available(), reason="PIL not installed")
def test_dhash_produces_hex_string(tmp_path):
    from PIL import Image
    from browsermind_core.media.understanding.analyzer import MediaAnalyzer

    img = Image.new("RGB", (50, 50), color=(200, 200, 200))
    h   = MediaAnalyzer()._dhash(img)
    assert isinstance(h, str)
    assert len(h) > 0
    int(h, 16)  # should be valid hex


@pytest.mark.skipif(not _pil_available(), reason="PIL not installed")
def test_dhash_different_for_different_images(tmp_path):
    from PIL import Image
    from browsermind_core.media.understanding.analyzer import MediaAnalyzer

    # Decreasing gradient: pixel[x] > pixel[x+1] everywhere → dhash bits = 1
    # dhash compares each pixel vs its right neighbour; decreasing → bit=1
    img1 = Image.new("L", (64, 64))
    for y in range(64):
        for x in range(64):
            img1.putpixel((x, y), max(0, 252 - x * 4))  # 252 → 0 right-to-left

    # Solid black: pixel[x] == pixel[x+1] → all bits = 0
    img2 = Image.new("L", (64, 64), 0)

    a  = MediaAnalyzer()
    h1 = a._dhash(img1)
    h2 = a._dhash(img2)
    assert isinstance(h1, str) and len(h1) > 0
    assert isinstance(h2, str) and len(h2) > 0
    assert h1 != h2  # decreasing gradient vs solid must produce different hashes


# ── Dominant colors ───────────────────────────────────────────────────────────

@pytest.mark.skipif(not _pil_available(), reason="PIL not installed")
def test_dominant_colors_returns_hex_list():
    from PIL import Image
    from browsermind_core.media.understanding.analyzer import MediaAnalyzer

    img    = Image.new("RGB", (100, 100), color=(255, 0, 0))
    colors = MediaAnalyzer()._dominant_colors(img)
    assert isinstance(colors, list)
    assert len(colors) > 0
    for c in colors:
        assert c.startswith("#")
        assert len(c) == 7  # #rrggbb


@pytest.mark.skipif(not _pil_available(), reason="PIL not installed")
def test_full_image_analysis(tmp_path):
    from PIL import Image
    from browsermind_core.media.understanding.analyzer import MediaAnalyzer
    from browsermind_core.media.media_asset import MediaAsset, MediaType

    img = Image.new("RGB", (80, 60), color=(100, 150, 200))
    p   = tmp_path / "test.png"
    img.save(str(p))

    asset = MediaAsset.from_bytes(p.read_bytes(), source_url="https://x.com/x",
                                  media_type=MediaType.IMAGE)
    asset.local_path = str(p)

    result = MediaAnalyzer().analyze(asset)
    assert result.dimensions == (80, 60)
    assert result.perceptual_hash is not None
    assert len(result.dominant_colors) > 0


# ── analyze_and_update ────────────────────────────────────────────────────────

def test_analyze_and_update_populates_understanding(tmp_path):
    from browsermind_core.media.understanding.analyzer import MediaAnalyzer
    from browsermind_core.media.media_asset import MediaAsset, MediaType

    p = tmp_path / "img.png"
    p.write_bytes(b"x" * 100)
    asset = MediaAsset.from_bytes(b"x" * 100, source_url="https://x.com/x",
                                  media_type=MediaType.IMAGE)
    asset.local_path = str(p)

    MediaAnalyzer().analyze_and_update(asset)
    assert "file_size" in asset.understanding
    assert asset.understanding["file_size"] == 100


# ── vision_backend ────────────────────────────────────────────────────────────

def test_vision_backend_called_when_provided(tmp_path):
    from browsermind_core.media.understanding.analyzer import MediaAnalyzer
    from browsermind_core.media.media_asset import MediaAsset, MediaType

    p = tmp_path / "img.png"
    p.write_bytes(b"bytes")
    asset = MediaAsset.from_bytes(b"bytes", source_url="https://x.com/x",
                                  media_type=MediaType.IMAGE)
    asset.local_path = str(p)

    backend = MagicMock()
    backend.analyze.return_value = {"ocr_text": "hello world"}

    result = MediaAnalyzer(vision_backend=backend).analyze(asset)
    backend.analyze.assert_called_once()
    assert result.ocr_text == "hello world"


# ── video without ffprobe ─────────────────────────────────────────────────────

def test_analyze_video_no_ffprobe(tmp_path):
    from browsermind_core.media.understanding.analyzer import MediaAnalyzer
    from browsermind_core.media.media_asset import MediaAsset, MediaType

    p = tmp_path / "clip.mp4"
    p.write_bytes(b"fake video")
    asset = MediaAsset.from_bytes(b"fake video", source_url="https://youtube.com/v",
                                  media_type=MediaType.VIDEO)
    asset.local_path = str(p)

    with patch("shutil.which", return_value=None):
        result = MediaAnalyzer().analyze(asset)

    assert result.error is None  # no error — graceful degradation
    assert result.codec is None
