"""MediaTransformer — apply transformations to MediaAsset objects.

Image operations require PIL/Pillow (pip install Pillow).
Video/audio operations require ffmpeg on PATH.
Both dependencies are optional — the transformer degrades gracefully and
returns TransformResult(success=False, error=...) when they are absent.

No LLM. No cloud API. All transforms are local and deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from browsermind_core.media.media_asset import MediaAsset, MediaType


@dataclass
class TransformOptions:
    """Transformation directives for one MediaTransformer.transform() call."""
    resize: Optional[Tuple[int, int]] = None         # (width, height) in pixels
    convert_to: Optional[str] = None                 # target format: "png", "jpg", "mp4" …
    compress_quality: Optional[int] = None           # 1–100 for JPEG / WebP
    crop: Optional[Tuple[int, int, int, int]] = None # (left, top, right, bottom)
    watermark_text: Optional[str] = None             # text overlay (images only)
    strip_metadata: bool = False


@dataclass
class TransformResult:
    success: bool
    asset: Optional[MediaAsset] = None
    error: Optional[str] = None
    operations_applied: List[str] = field(default_factory=list)


class MediaTransformer:
    """Apply deterministic transformations to a MediaAsset.

    Dispatch is by media_type. Each method returns a NEW MediaAsset whose
    local_path points to the transformed file; the original is preserved.
    """

    def transform(
        self,
        asset: MediaAsset,
        options: TransformOptions,
        output_path: Optional[Path] = None,
    ) -> TransformResult:
        if asset.media_type in (MediaType.IMAGE, MediaType.GIF):
            return self._transform_image(asset, options, output_path)
        if asset.media_type == MediaType.VIDEO:
            return self._transform_video(asset, options, output_path)
        if asset.media_type == MediaType.AUDIO:
            return self._transform_audio(asset, options, output_path)
        return TransformResult(
            success=False,
            error=f"Unsupported media type for transformation: {asset.media_type}",
        )

    # ── Image ──────────────────────────────────────────────────────────────────

    def _transform_image(
        self,
        asset: MediaAsset,
        options: TransformOptions,
        output_path: Optional[Path],
    ) -> TransformResult:
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            return TransformResult(
                success=False,
                error="PIL not installed — run: pip install Pillow",
            )

        if not asset.local_path:
            return TransformResult(success=False, error="Asset has no local_path")

        applied: List[str] = []
        try:
            img = Image.open(asset.local_path)

            if options.crop:
                img = img.crop(options.crop)
                applied.append(f"crop:{options.crop}")

            if options.resize:
                img = img.resize(options.resize, Image.LANCZOS)
                applied.append(f"resize:{options.resize[0]}x{options.resize[1]}")

            if options.watermark_text:
                img = self._add_watermark(img, options.watermark_text)
                applied.append("watermark")

            src_path   = Path(asset.local_path)
            raw_format = (options.convert_to or "").lower().strip(".")
            if not raw_format:
                raw_format = src_path.suffix.lstrip(".").lower()
            if raw_format in ("jpg", ""):
                raw_format = "jpeg"

            out = output_path or src_path.parent / f"{src_path.stem}_transformed.{raw_format}"

            save_kwargs: Dict[str, Any] = {}
            if options.compress_quality and raw_format in ("jpeg", "webp"):
                save_kwargs["quality"] = options.compress_quality
            if options.strip_metadata:
                img.info.clear()

            pil_format = raw_format.upper()
            if pil_format == "JPG":
                pil_format = "JPEG"
            if img.mode in ("RGBA", "P") and pil_format == "JPEG":
                img = img.convert("RGB")

            img.save(str(out), format=pil_format, **save_kwargs)
            applied.append(f"save:{raw_format}")

            new_asset              = MediaAsset.from_path(out, source_url=asset.source_url, source=asset.source)
            new_asset.title        = asset.title
            new_asset.author       = asset.author
            new_asset.tags         = list(asset.tags)
            new_asset.collections  = list(asset.collections)
            new_asset.metadata.update(asset.metadata)
            new_asset.understanding.update(asset.understanding)

            return TransformResult(success=True, asset=new_asset, operations_applied=applied)

        except Exception as exc:
            return TransformResult(success=False, error=str(exc), operations_applied=applied)

    def _add_watermark(self, img, text: str):
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        w, h = img.size
        draw.text((10, h - 30), text, fill=(255, 255, 255), font=font)
        return img

    # ── Video ──────────────────────────────────────────────────────────────────

    def _transform_video(
        self,
        asset: MediaAsset,
        options: TransformOptions,
        output_path: Optional[Path],
    ) -> TransformResult:
        return self._ffmpeg_transform(asset, options, output_path, is_video=True)

    def _transform_audio(
        self,
        asset: MediaAsset,
        options: TransformOptions,
        output_path: Optional[Path],
    ) -> TransformResult:
        return self._ffmpeg_transform(asset, options, output_path, is_video=False)

    def _ffmpeg_transform(
        self,
        asset: MediaAsset,
        options: TransformOptions,
        output_path: Optional[Path],
        is_video: bool,
    ) -> TransformResult:
        if not asset.local_path:
            return TransformResult(success=False, error="Asset has no local_path")
        try:
            import subprocess
            import shutil
            if not shutil.which("ffmpeg"):
                return TransformResult(success=False, error="ffmpeg not found on PATH")

            in_path    = Path(asset.local_path)
            target_ext = (options.convert_to or in_path.suffix.lstrip(".")).lower()
            out        = output_path or in_path.parent / f"{in_path.stem}_transformed.{target_ext}"

            cmd: List[str] = ["ffmpeg", "-y", "-i", str(in_path)]
            applied: List[str] = []

            if is_video and options.resize:
                cmd += ["-vf", f"scale={options.resize[0]}:{options.resize[1]}"]
                applied.append(f"resize:{options.resize[0]}x{options.resize[1]}")
            if options.strip_metadata:
                cmd += ["-map_metadata", "-1"]
                applied.append("strip_metadata")

            cmd.append(str(out))
            subprocess.run(cmd, check=True, capture_output=True)
            applied.append(f"ffmpeg:{target_ext}")

            new_asset             = MediaAsset.from_path(out, source_url=asset.source_url, source=asset.source)
            new_asset.title       = asset.title
            new_asset.tags        = list(asset.tags)
            new_asset.collections = list(asset.collections)
            return TransformResult(success=True, asset=new_asset, operations_applied=applied)

        except Exception as exc:
            err = getattr(exc, "stderr", b"")
            if isinstance(err, bytes):
                err = err.decode(errors="replace")[:200]
            return TransformResult(success=False, error=str(exc) if not err else err)
