"""Создание превью с водяным знаком (Pillow)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from config import SHOP_NAME

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "DejaVuSans-Bold.ttf",
    "arialbd.ttf",
)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _flatten(img: Image.Image) -> Image.Image:
    """RGBA/P -> RGB на белом фоне."""
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")


def _text_size(text: str, font) -> tuple[int, int]:
    bbox = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox[0], bbox[1]


def make_watermark(src, dst, text: str | None = None, max_side: int = 1280, opacity: float = 0.28, angle: int = -30) -> None:
    """
    Делает уменьшенную копию фото с диагональным «плёночным» водяным знаком
    и подписью лавки в правом нижнем углу. Сохраняет в JPEG.
    """
    text = text or f"© {SHOP_NAME}"
    img = Image.open(src)
    img = ImageOps.exif_transpose(img)
    img = _flatten(img)
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    w, h = img.size

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    # --- диагональные повторяющиеся знаки ---
    font = _load_font(max(20, min(w, h) // 15))
    tw, th, tdx, tdy = _text_size(text, font)
    tile = Image.new("RGBA", (tw + max(40, tw // 3), th + max(36, th)), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text((tile.width // 2 - tdx, tile.height // 2 - tdy), text, font=font,
                              fill=(255, 255, 255, int(255 * opacity)), anchor="mm")

    diag = int((w * w + h * h) ** 0.5) + tile.width
    pattern = Image.new("RGBA", (diag, diag), (0, 0, 0, 0))
    step_y = tile.height
    for row, y in enumerate(range(0, diag, step_y)):
        offset = (row % 2) * (tile.width // 2)
        for x in range(-tile.width, diag, tile.width):
            pattern.paste(tile, (x + offset, y), tile)

    pattern = pattern.rotate(angle, resample=Image.BICUBIC, expand=True)
    left = (pattern.width - w) // 2
    top = (pattern.height - h) // 2
    overlay = Image.alpha_composite(overlay, pattern.crop((left, top, left + w, top + h)))

    # --- подпись в правом нижнем углу ---
    d = ImageDraw.Draw(overlay)
    sig = f"{SHOP_NAME} • фотолавка"
    sig_font = _load_font(max(16, min(w, h) // 26))
    sw, sh, sdx, sdy = _text_size(sig, sig_font)
    pad = max(10, min(w, h) // 45)
    x0, y0 = w - sw - 2 * pad - sdx, h - sh - 2 * pad - sdy
    d.rounded_rectangle(
        [x0 + sdx - pad, y0 + sdy - pad, x0 + sdx + sw + pad, y0 + sdy + sh + pad],
        radius=pad, fill=(0, 0, 0, 105),
    )
    d.text((x0, y0), sig, font=sig_font, fill=(255, 255, 255, 215))

    result = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    result.save(dst, "JPEG", quality=88)
