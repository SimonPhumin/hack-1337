"""Build Hack 1337 from pinned upstreams.

  stock Hack 3.003 TTF
    -> prepare.py      Hack 1337 line metrics
    -> font-patcher    Nerd Fonts (complete, single-width icons)
    -> native.py       ligature glyphs and rules from src/ligatures/recipes.py
    -> features.py     src/features/native.fea compiled together with the generated code
    -> finalize.py     names, metrics, monospace check
    -> export.py       ttf/ otf/ woff/ woff2/

Usage: build.py [STYLE ...]   (default: all styles)
"""
import shutil
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from fontTools.ttLib import TTFont

import export
import features
import native
from config import BUILD, CACHE, FAMILY, ROOT, STYLES
from fetch import UPSTREAMS, fetch
from finalize import finalize
from prepare import prepare

OUT_DIRS = {ext: ROOT / ext for ext in ("ttf", "otf", "woff", "woff2")}


def nerd_font_patch(src: Path, outdir: Path) -> Path:
    shutil.rmtree(outdir, ignore_errors=True)
    outdir.mkdir(parents=True)
    proc = subprocess.run(
        ["fontforge", "-quiet", "-script", str(CACHE / "nerd-fonts" / "font-patcher"),
         "--complete", "--mono", "--metrics", "HHEA", "--quiet", "--no-progressbars",
         "--outputdir", str(outdir), str(src)],
        capture_output=True, text=True,
    )
    (outdir / "font-patcher.log").write_text(proc.stdout + proc.stderr)
    if proc.returncode:
        raise RuntimeError(f"font-patcher failed for {src}, see {outdir / 'font-patcher.log'}")
    (patched,) = outdir.glob("*.ttf")
    return patched


def build_style(style: str) -> str:
    spec = STYLES[style]
    work = BUILD / "work" / style.replace(" ", "")
    work.mkdir(parents=True, exist_ok=True)
    stock = CACHE / "hack" / "ttf" / spec["hack"]

    prepared = work / "1-prepared.ttf"
    prepare(str(stock), str(prepared))
    patched = nerd_font_patch(prepared, work / "2-nerd-font")

    font = TTFont(patched)
    ligature_fea, _ = native.build(font)
    fea = features.apply(font, ligature_fea)
    (work / "features.fea").write_text(fea)

    os2 = TTFont(stock)["OS/2"]
    finalize(font, style, (os2.usWinAscent, os2.usWinDescent))

    filename = f"{FAMILY} {style}"
    ttf = OUT_DIRS["ttf"] / f"{filename}.ttf"
    font.save(ttf)
    export.to_otf(ttf, OUT_DIRS["otf"] / f"{filename}.otf")
    export.to_web(ttf, OUT_DIRS["woff"] / f"{filename}.woff", "woff")
    export.to_web(ttf, OUT_DIRS["woff2"] / f"{filename}.woff2", "woff2")
    return f"built {filename}"


def main(styles: list[str]) -> None:
    for name, spec in UPSTREAMS.items():
        fetch(name, spec)
    for d in OUT_DIRS.values():
        d.mkdir(exist_ok=True)
    with ProcessPoolExecutor() as pool:
        for line in pool.map(build_style, styles):
            print(line)


if __name__ == "__main__":
    wanted = sys.argv[1:] or list(STYLES)
    unknown = [s for s in wanted if s not in STYLES]
    if unknown:
        sys.exit(f"unknown style(s) {unknown}; choose from {list(STYLES)}")
    main(wanted)
