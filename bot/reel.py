"""広報部（動画担当）：スライド画像からリール用の縦動画（1080x1920, 9:16）を作る。

Instagramはフォロワー外への表示をリール中心にしているため、フォロワー0の段階の集客に使う。
- 各スライド（1080x1350）を縦長キャンバスの中央に置き、上に見出しを入れる（下はInstagramの表示に隠れるので空ける）
- 1枚あたり約3.5秒、短いフェードでつなぐ
- 音声は無音トラック（Instagramの楽曲はAPIでは付けられない。付けたい場合はアプリで後から）
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from .slides import BG, MUTED, PINK, font

RW, RH = 1080, 1920
SEC_PER_SLIDE = 3.5
FADE = 0.4


def _frame(slide: Path, top: str, bottom: str) -> Image.Image:
    im = Image.new("RGB", (RW, RH), BG)
    s = Image.open(slide).convert("RGB")
    y = (RH - s.height) // 2
    im.paste(s, (0, y))
    d = ImageDraw.Draw(im)
    for text, ty, f, fill in ((top, y - 150, font("black", 54), PINK), (bottom, y + s.height + 90, font("bold", 40), MUTED)):
        if text:
            d.text(((RW - d.textlength(text, font=f)) / 2, ty), text, font=f, fill=fill)
    return im


def make_reel(slides: list[Path], out_dir: Path, top: str, bottom: str = "") -> tuple[Path, Path]:
    """reel.mp4 と cover.jpg を out_dir に作って返す。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    mp4, cover = out_dir / "reel.mp4", out_dir / "cover.jpg"
    with tempfile.TemporaryDirectory() as tmp:
        frames = []
        for i, sp in enumerate(slides):
            p = Path(tmp) / f"{i:02d}.png"
            _frame(sp, top, bottom).save(p)
            frames.append(p)
        Image.open(frames[0]).convert("RGB").save(cover, "JPEG", quality=90)
        n = len(frames)
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        for p in frames:
            cmd += ["-loop", "1", "-t", f"{SEC_PER_SLIDE + FADE}", "-i", str(p)]
        cmd += ["-f", "lavfi", "-t", f"{n * SEC_PER_SLIDE + FADE}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        # スライドを順にクロスフェードでつなぐ
        chain, last = [], "[0:v]"
        for i in range(1, n):
            out = f"[v{i}]"
            chain.append(f"{last}[{i}:v]xfade=transition=fade:duration={FADE}:offset={i * SEC_PER_SLIDE}{out}")
            last = out
        vf = ";".join(chain) + (";" if chain else "") + f"{last}format=yuv420p,fps=30[vout]"
        cmd += ["-filter_complex", vf, "-map", "[vout]", "-map", f"{n}:a",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-profile:v", "high",
                "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(mp4)]
        subprocess.run(cmd, check=True)
    return mp4, cover
