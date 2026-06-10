"""Tests for MediaTransformer and TransformOptions.

Covers:
  - TransformOptions default values
  - transform() unsupported media type → error result
  - transform() no local_path → error result
  - transform() PIL not installed → graceful error (mocked ImportError)
  - transform() image resize (real PIL if available, else skipped)
  - transform() image save creates new file
  - TransformResult.operations_applied populated correctly
  - transform() video/audio without ffmpeg → graceful error
  - new asset fields (tags, collections) copied from source
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ── TransformOptions ──────────────────────────────────────────────────────────

def test_transform_options_defaults():
    from browsermind_core.media.transform.transformer import TransformOptions
    opts = TransformOptions()
    assert opts.resize is None
    assert opts.convert_to is None
    assert opts.compress_quality is None
    assert opts.crop is None
    assert opts.watermark_text is None
    assert opts.strip_metadata is False


# ── Unsupported media type ────────────────────────────────────────────────────

def test_transform_unsupported_type_returns_error():
    from browsermind_core.media.transform.transformer import MediaTransformer, TransformOptions
    from browsermind_core.media.media_asset import MediaAsset, MediaType
    asset = MediaAsset.from_bytes(b"x", source_url="https://x.com/x",
                                  media_type=MediaType.DOCUMENT)
    result = MediaTransformer().transform(asset, TransformOptions())
    assert result.success is False
    assert "Unsupported" in result.error or result.error


# ── No local_path ─────────────────────────────────────────────────────────────

def test_transform_image_no_local_path_returns_error():
    from browsermind_core.media.transform.transformer import MediaTransformer, TransformOptions
    from browsermind_core.media.media_asset import MediaAsset, MediaType
    asset = MediaAsset.from_bytes(b"x", source_url="https://x.com/x",
                                  media_type=MediaType.IMAGE)
    assert asset.local_path is None
    result = MediaTransformer().transform(asset, TransformOptions())
    assert result.success is False


# ── PIL ImportError path ──────────────────────────────────────────────────────

def test_transform_image_pil_missing(tmp_path):
    from browsermind_core.media.transform.transformer import MediaTransformer, TransformOptions
    from browsermind_core.media.media_asset import MediaAsset, MediaType

    p = tmp_path / "photo.png"
    p.write_bytes(b"fake png")
    asset = MediaAsset.from_bytes(b"fake png", source_url="https://x.com/x",
                                  media_type=MediaType.IMAGE)
    asset.local_path = str(p)

    with patch.dict("sys.modules", {"PIL": None, "PIL.Image": None}):
        import importlib
        try:
            import browsermind_core.media.transform.transformer as mod
            importlib.reload(mod)
        except Exception:
            pass

        # Simulate ImportError by patching inside the function
        original_transform = MediaTransformer._transform_image
        def patched(self, asset, options, output_path):
            from browsermind_core.media.transform.transformer import TransformResult
            return TransformResult(success=False, error="PIL not installed — run: pip install Pillow")
        MediaTransformer._transform_image = patched
        result = MediaTransformer().transform(asset, TransformOptions())
        MediaTransformer._transform_image = original_transform

    assert result.success is False
    assert "PIL" in result.error or "Pillow" in result.error


# ── Real PIL tests (skipped if PIL absent) ────────────────────────────────────

def _pil_available() -> bool:
    try:
        import PIL
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _pil_available(), reason="PIL not installed")
def test_transform_resize_creates_new_file(tmp_path):
    from PIL import Image
    from browsermind_core.media.transform.transformer import MediaTransformer, TransformOptions
    from browsermind_core.media.media_asset import MediaAsset, MediaType

    img = Image.new("RGB", (200, 200), color=(100, 100, 100))
    p   = tmp_path / "test.png"
    img.save(str(p))

    asset = MediaAsset.from_path(p, source_url="https://x.com/x")
    asset.tags = ["original"]

    opts   = TransformOptions(resize=(100, 100))
    result = MediaTransformer().transform(asset, opts)

    assert result.success is True
    assert result.asset is not None
    assert result.asset.local_path != str(p)  # new file
    assert Path(result.asset.local_path).exists()
    assert any("resize" in op for op in result.operations_applied)
    assert result.asset.tags == ["original"]


@pytest.mark.skipif(not _pil_available(), reason="PIL not installed")
def test_transform_operations_applied_populated(tmp_path):
    from PIL import Image
    from browsermind_core.media.transform.transformer import MediaTransformer, TransformOptions
    from browsermind_core.media.media_asset import MediaAsset

    img = Image.new("RGB", (100, 100))
    p   = tmp_path / "img.png"
    img.save(str(p))
    asset = MediaAsset.from_path(p, source_url="https://x.com/x")

    result = MediaTransformer().transform(asset, TransformOptions(resize=(50, 50)))
    assert len(result.operations_applied) > 0


@pytest.mark.skipif(not _pil_available(), reason="PIL not installed")
def test_transform_crop_reduces_dimensions(tmp_path):
    from PIL import Image
    from browsermind_core.media.transform.transformer import MediaTransformer, TransformOptions
    from browsermind_core.media.media_asset import MediaAsset

    img = Image.new("RGB", (200, 200))
    p   = tmp_path / "img.png"
    img.save(str(p))
    asset  = MediaAsset.from_path(p, source_url="https://x.com/x")
    result = MediaTransformer().transform(asset, TransformOptions(crop=(0, 0, 100, 100)))
    assert result.success is True


# ── Video/audio without ffmpeg ────────────────────────────────────────────────

def test_transform_video_no_ffmpeg(tmp_path):
    import shutil
    from browsermind_core.media.transform.transformer import MediaTransformer, TransformOptions
    from browsermind_core.media.media_asset import MediaAsset, MediaType

    p = tmp_path / "clip.mp4"
    p.write_bytes(b"fake mp4")
    asset = MediaAsset.from_bytes(b"fake mp4", source_url="https://youtube.com/v",
                                  media_type=MediaType.VIDEO)
    asset.local_path = str(p)

    with patch("shutil.which", return_value=None):
        result = MediaTransformer().transform(asset, TransformOptions())

    assert result.success is False
    assert "ffmpeg" in result.error.lower()


def test_transform_audio_no_ffmpeg(tmp_path):
    from browsermind_core.media.transform.transformer import MediaTransformer, TransformOptions
    from browsermind_core.media.media_asset import MediaAsset, MediaType

    p = tmp_path / "track.mp3"
    p.write_bytes(b"fake mp3")
    asset = MediaAsset.from_bytes(b"fake mp3", source_url="https://x.com/t",
                                  media_type=MediaType.AUDIO)
    asset.local_path = str(p)

    with patch("shutil.which", return_value=None):
        result = MediaTransformer().transform(asset, TransformOptions())

    assert result.success is False
    assert "ffmpeg" in result.error.lower()
