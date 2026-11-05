"""Apply Hack 1337's line metrics to a stock Hack TTF before Nerd Font patching,
so the patcher sizes icons and Powerline separators to the 1337 cell height."""
import sys

from fontTools.ttLib import TTFont

from config import LINE_METRICS


def prepare(src: str, dst: str) -> None:
    font = TTFont(src)
    hhea, os2 = font["hhea"], font["OS/2"]
    hhea.ascent, hhea.descent, hhea.lineGap = LINE_METRICS["ascent"], LINE_METRICS["descent"], LINE_METRICS["lineGap"]
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = hhea.ascent, hhea.descent, hhea.lineGap
    font.save(dst)


if __name__ == "__main__":
    prepare(sys.argv[1], sys.argv[2])
