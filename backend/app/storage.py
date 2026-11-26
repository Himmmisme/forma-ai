import hashlib
import io
import os
import re
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core import fail
from app.models import Asset, new_id

UPLOAD_LIMIT = 12 * 1024 * 1024
OUTPUT_LIMIT = 24 * 1024 * 1024
MAX_PIXELS = 24_000_000
FORMATS = {"PNG": ("image/png", "png"), "JPEG": ("image/jpeg", "jpg"), "WEBP": ("image/webp", "webp")}


def safe_filename(value: str, fallback: str) -> str:
    value = re.sub(r'[\x00-\x1f\x7f/\\:<>|"*?]', "_", value or "").strip(" .")
    return value[:150] or fallback


def asset_path(data_dir: Path, asset_id: str) -> Path:
    if not re.fullmatch("[a-f0-9]{32}", asset_id):
        fail(404, "图片不存在")
    return data_dir / "images" / asset_id[:2] / asset_id


def validate_image(content: bytes, limit: int = UPLOAD_LIMIT):
    if not content or len(content) > limit:
        fail(413, f"图片大小应在 1 字节至 {limit // (1024 * 1024)} MB 之间")
    try:
        image = Image.open(io.BytesIO(content))
        if image.format not in FORMATS or getattr(image, "is_animated", False):
            fail(415, "请上传静态 PNG、JPEG 或 WebP 图片")
        if image.width * image.height > MAX_PIXELS:
            fail(413, "图片像素超过 2400 万")
        image.load()
        return image
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, SyntaxError, ValueError):
        fail(415, "图片格式不受支持或文件已损坏")


def store_image(
    data_dir: Path, project_id: str, kind: str, filename: str, content: bytes, *, preserve: bool = False
) -> Asset:
    image = validate_image(content, OUTPUT_LIMIT if preserve else UPLOAD_LIMIT)
    if preserve:
        mime, extension = FORMATS[image.format]
    else:
        # Standardize orientation and remove EXIF and other upload metadata.
        image = ImageOps.exif_transpose(image)
        image.thumbnail((2800, 2800), Image.Resampling.LANCZOS)
        mode = "RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB"
        normalized = Image.frombytes(mode, image.size, image.convert(mode).tobytes())
        buffer = io.BytesIO()
        normalized.save(buffer, "WEBP", quality=92, method=4)
        content = buffer.getvalue()
        mime, extension = FORMATS["WEBP"]
    asset_id = new_id()
    path = asset_path(data_dir, asset_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    try:
        with partial.open("xb") as file:
            file.write(content)
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)
    stem = Path(safe_filename(filename, "forma")).stem
    return Asset(
        id=asset_id, project_id=project_id, kind=kind, filename=f"{stem}.{extension}",
        mime=mime, width=image.width, height=image.height, size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )
