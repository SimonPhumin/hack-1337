"""Write the web (WOFF/WOFF2) and CFF-flavoured OpenType (.otf) versions of a finished TTF."""
import sys
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.qu2cuPen import Qu2CuPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont


def to_otf(ttf_path: Path, otf_path: Path) -> None:
    font = TTFont(ttf_path)
    glyphs, hmtx = font.getGlyphSet(), font["hmtx"]
    charstrings, metrics = {}, {}
    for name in font.getGlyphOrder():
        width = hmtx[name][0]
        rec = DecomposingRecordingPen(glyphs)
        glyphs[name].draw(rec)
        pen = T2CharStringPen(width, None)
        # TrueType contours run clockwise, CFF counter-clockwise.
        rec.replay(Qu2CuPen(pen, max_err=1.0, reverse_direction=True))
        charstrings[name] = pen.getCharString()
        bp = BoundsPen(None)
        rec.replay(bp)
        metrics[name] = (width, round(bp.bounds[0]) if bp.bounds else 0)

    for table in ("glyf", "loca", "cvt ", "fpgm", "prep", "gasp", "hdmx", "LTSH", "VDMX", "TTFA"):
        if table in font:
            del font[table]
    fb = FontBuilder(font=font)
    fb.isTTF = False
    ps_name = font["name"].getDebugName(6)
    fb.setupCFF(ps_name, {"FullName": font["name"].getDebugName(4), "FamilyName": font["name"].getDebugName(1),
                          "Weight": font["name"].getDebugName(2), "isFixedPitch": True}, charstrings, {})
    fb.setupHorizontalMetrics(metrics)
    fb.setupMaxp()
    font["post"].formatType = 3.0
    font.save(otf_path)


def to_web(ttf_path: Path, out_path: Path, flavor: str) -> None:
    font = TTFont(ttf_path)
    font.flavor = flavor
    font.save(out_path)


if __name__ == "__main__":
    src = Path(sys.argv[1])
    to_otf(src, src.with_suffix(".otf"))
