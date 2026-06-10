"""MediaAnalyzer — pure-Python media analysis. No LLM. No vision API.

What it can do (stdlib + optional Pillow):
  - File size
  - Image dimensions
  - Perceptual hash (dhash) — similarity search / deduplication
  - Dominant colors (PIL quantize) — top-N as hex strings
  - EXIF metadata extraction
  - OCR text  (requires pytesseract + tesseract binary)
  - Audio/video duration + codec (requires ffprobe/ffmpeg)

What it CANNOT do without a vision model:
  - People detection
  - Object classification
  - Logo recognition
  - Scene understanding

Architecture: vision_backend parameter allows plugging in CLIP, BLIP, or any
local vision model later without changing the interface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from browsermind_core.media.media_asset import MediaAsset, MediaType


@dataclass
class AnalysisResult:
    """Output of MediaAnalyzer.analyze()."""
    content_hash: str
    media_type: str
    file_size: int = 0
    dimensions: Optional[Tuple[int, int]] = None      # (width, height)
    duration_seconds: Optional[float] = None           # audio / video
    dominant_colors: List[str] = field(default_factory=list)  # hex "#rrggbb"
    perceptual_hash: Optional[str] = None              # dhash hex string
    ocr_text: Optional[str] = None
    exif: Dict[str, Any] = field(default_factory=dict)
    codec: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content_hash":     self.content_hash,
            "media_type":       self.media_type,
            "file_size":        self.file_size,
            "dimensions":       list(self.dimensions) if self.dimensions else None,
            "duration_seconds": self.duration_seconds,
            "dominant_colors":  self.dominant_colors,
            "perceptual_hash":  self.perceptual_hash,
            "ocr_text":         self.ocr_text,
            "exif":             self.exif,
            "codec":            self.codec,
        }


class MediaAnalyzer:
    """Analyze a MediaAsset without any LLM or cloud call.

    Usage
    ─────
      analyzer = MediaAnalyzer()
      result   = analyzer.analyze(asset)
      asset    = analyzer.analyze_and_update(asset)  # writes into asset.understanding
    """

    def __init__(self, vision_backend=None):
        self._vision_backend = vision_backend

    def analyze(self, asset: MediaAsset) -> AnalysisResult:
        result = AnalysisResult(
            content_hash=asset.content_hash,
            media_type=asset.media_type,
        )
        if not asset.local_path:
            result.error = "Asset has no local_path"
            return result
        path = Path(asset.local_path)
        if not path.exists():
            result.error = f"File not found: {path}"
            return result

        result.file_size = path.stat().st_size

        if asset.media_type in (MediaType.IMAGE, MediaType.GIF):
            self._analyze_image(path, result)
        elif asset.media_type == MediaType.VIDEO:
            self._analyze_video(path, result)
        elif asset.media_type == MediaType.AUDIO:
            self._analyze_audio(path, result)

        if self._vision_backend is not None:
            try:
                extra = self._vision_backend.analyze(path)
                if isinstance(extra, dict):
                    for k, v in extra.items():
                        if hasattr(result, k):
                            setattr(result, k, v)
            except Exception:
                pass

        return result

    def analyze_and_update(self, asset: MediaAsset) -> MediaAsset:
        """Analyze and write results into asset.understanding and asset.metadata."""
        r = self.analyze(asset)
        asset.understanding.update(r.to_dict())
        if r.exif:
            asset.metadata.setdefault("exif", r.exif)
        return asset

    # ── Image ──────────────────────────────────────────────────────────────────

    def _analyze_image(self, path: Path, result: AnalysisResult) -> None:
        try:
            from PIL import Image, ExifTags
        except ImportError:
            return

        try:
            img = Image.open(path)
            result.dimensions = img.size

            # EXIF
            try:
                raw = img._getexif()
                if raw:
                    result.exif = {
                        ExifTags.TAGS.get(k, str(k)): str(v)
                        for k, v in raw.items()
                        if isinstance(v, (str, int, float))
                    }
            except Exception:
                pass

            result.perceptual_hash  = self._dhash(img)
            result.dominant_colors  = self._dominant_colors(img)

        except Exception as exc:
            result.error = f"Image analysis: {exc}"

        self._try_ocr(path, result)

    def _dhash(self, img, size: int = 8) -> str:
        """Difference hash — robust to minor rescaling and edits."""
        try:
            from PIL import Image
            gray   = img.convert("L").resize((size + 1, size), Image.LANCZOS)
            pixels = list(gray.getdata())  # type: ignore[attr-defined]
            bits   = []
            for row in range(size):
                for col in range(size):
                    idx = row * (size + 1) + col
                    bits.append("1" if pixels[idx] > pixels[idx + 1] else "0")
            val = int("".join(bits), 2)
            return f"{val:0{size * size // 4}x}"
        except Exception:
            return ""

    def _dominant_colors(self, img, n: int = 5) -> List[str]:
        """Return n dominant colors as #rrggbb hex strings."""
        try:
            from PIL import Image
            small = img.copy().convert("RGB").resize((100, 100), Image.LANCZOS)
            # quantize gives us a palette with n representative colors
            quantized = small.quantize(colors=n)
            palette   = quantized.getpalette()
            colors    = []
            for i in range(min(n, len(palette) // 3)):
                r, g, b = palette[i * 3], palette[i * 3 + 1], palette[i * 3 + 2]
                colors.append(f"#{r:02x}{g:02x}{b:02x}")
            return colors
        except Exception:
            return []

    def _try_ocr(self, path: Path, result: AnalysisResult) -> None:
        try:
            import pytesseract
            from PIL import Image
            text = pytesseract.image_to_string(Image.open(path)).strip()
            if text:
                result.ocr_text = text
        except ImportError:
            pass
        except Exception:
            pass

    # ── Video / Audio ──────────────────────────────────────────────────────────

    def _analyze_video(self, path: Path, result: AnalysisResult) -> None:
        self._ffprobe(path, result, want_video=True)

    def _analyze_audio(self, path: Path, result: AnalysisResult) -> None:
        self._ffprobe(path, result, want_video=False)

    def _ffprobe(self, path: Path, result: AnalysisResult, want_video: bool) -> None:
        try:
            import subprocess
            import shutil
            import json as _json
            if not shutil.which("ffprobe"):
                return
            cmd = [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", "-show_format", str(path),
            ]
            proc = subprocess.run(cmd, capture_output=True, timeout=15)
            if proc.returncode != 0:
                return
            data = _json.loads(proc.stdout)
            fmt  = data.get("format", {})
            dur  = float(fmt.get("duration", 0) or 0)
            if dur:
                result.duration_seconds = dur
            for stream in data.get("streams", []):
                if want_video and stream.get("codec_type") == "video":
                    result.dimensions = (stream.get("width"), stream.get("height"))
                    result.codec      = stream.get("codec_name")
                    break
                if not want_video and stream.get("codec_type") == "audio":
                    result.codec = stream.get("codec_name")
                    break
            result.exif.update({
                k: v for k, v in fmt.items()
                if isinstance(v, (str, int, float)) and k not in ("filename", "nb_streams")
            })
        except Exception:
            pass
