"""Native Hack 1337 features: build the alias glyphs from src/features/glyphs.json and compile
src/features/native.fea together with the generated JetBrains Mono ligature code."""
import json
import re
from pathlib import Path

from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from config import ROOT
from otl import add_features

FEATURES = ROOT / "src" / "features"


def add_alias_glyphs(font: TTFont, aliases: dict[str, str]) -> None:
    cmap, glyf, hmtx = font.getBestCmap(), font["glyf"], font["hmtx"]
    order = font.getGlyphOrder()
    for name, char in aliases.items():
        if name.startswith("_") or name in glyf.glyphs:
            continue
        base = cmap[ord(char)]
        pen = TTGlyphPen(glyf.glyphs)
        pen.addComponent(base, (1, 0, 0, 1, 0, 0))
        glyph = pen.glyph()
        glyph.components[0].flags |= 0x0200  # USE_MY_METRICS: take advance/hinting metrics from the base
        glyf.glyphs[name] = glyph
        hmtx.metrics[name] = hmtx.metrics[base]
        order.append(name)
    font.setGlyphOrder(order)
    glyf.glyphOrder = order


def resolve(fea: str, font: TTFont) -> str:
    cmap = font.getBestCmap()
    return re.sub(r"\$u([0-9A-Fa-f]{4,6})", lambda m: "\\" + cmap[int(m.group(1), 16)], fea)


def native_fea(font: TTFont) -> str:
    add_alias_glyphs(font, json.loads((FEATURES / "glyphs.json").read_text()))
    return resolve((FEATURES / "native.fea").read_text(), font)


def apply(font: TTFont, generated_fea: str) -> str:
    """Compile native + generated features into `font`. Returns the combined feature code."""
    fea = native_fea(font) + "\n" + generated_fea
    add_features(font, fea)
    return fea
