"""간단한 앱 아이콘(assets/icon.ico) 생성."""

from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:
    raise SystemExit("pip install pillow  후 다시 실행하세요.") from exc


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "icon.ico"

    sizes = [16, 32, 48, 64, 128, 256]
    images = []
    for s in sizes:
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # 둥근 사각형 배경
        margin = max(1, s // 16)
        d.rounded_rectangle(
            [margin, margin, s - margin - 1, s - margin - 1],
            radius=max(2, s // 6),
            fill=(31, 106, 165, 255),
        )
        # 글자 L
        try:
            font = ImageFont.truetype("malgun.ttf", size=max(10, s // 2))
        except OSError:
            font = ImageFont.load_default()
        text = "L"
        bbox = d.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(
            ((s - tw) / 2, (s - th) / 2 - s * 0.05),
            text,
            fill=(255, 255, 255, 255),
            font=font,
        )
        images.append(img)

    images[0].save(
        out,
        format="ICO",
        sizes=[(im.width, im.height) for im in images],
        append_images=images[1:],
    )
    # PNG 미리보기
    images[-1].save(out_dir / "icon.png")
    print(f"작성: {out}")


if __name__ == "__main__":
    main()
