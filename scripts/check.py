"""Verify the built fonts.

For every style:
  - monospace advance widths, Hack 1337 line metrics, family name
  - every ligature JetBrains Mono has is formed too, and on the real-world code in
    tests/code-samples.txt ligatures form exactly where JetBrains Mono forms them (except for
    tests/accepted-differences.txt). JetBrains Mono is only a test reference; nothing from it is
    built into the fonts.
  - ss01 switches comparison ligatures off
  - Nerd Fonts coverage, and code points gained/lost compared to the committed fonts (git HEAD)
  - the .otf shapes exactly like the .ttf

Usage: check.py [--against REV]
"""
import argparse
import io
import itertools
import random
import subprocess
import sys

import uharfbuzz as hb
from fontTools.ttLib import TTFont

from config import CACHE, FAMILY, LINE_METRICS, ROOT, STYLES
from native import load_recipes

PUNCT = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
SAMPLE_ICONS = {0xE0B0: "powerline", 0xE5FA: "seti", 0xE700: "devicons", 0xEA60: "codicons",
                0xF07B: "font awesome", 0xF0001: "material design", 0xF300: "font logos", 0xF400: "octicons"}


class Shaper:
    def __init__(self, data: bytes):
        self.font = hb.Font(hb.Face(hb.Blob(data)))
        self.tt = TTFont(io.BytesIO(data))
        self.order = self.tt.getGlyphOrder()
        self.cmap = self.tt.getBestCmap()

    def __call__(self, text: str, features=None) -> list[str]:
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.font, buf, features or {})
        return [self.order[i.codepoint] for i in buf.glyph_infos]

    def ligature(self, text: str) -> str | None:
        """Name of the ligature glyph if `text` shapes to spacers + one .liga glyph."""
        out = self(text)
        if len(out) == len(text) and out[-1].endswith(".liga") and all(g in ("SPC", "LIG") for g in out[:-1]):
            return out[-1]
        return None


def ligature_set(shaper: Shaper) -> dict[str, str]:
    """All ligatures of a font, found by shaping punctuation sequences (shortest string per glyph)."""
    found: dict[str, str] = {}
    def visit(s):
        g = shaper.ligature(s)
        if g and g not in found:
            found[g] = s
        return g
    for n in (2, 3):
        for t in itertools.product(PUNCT, repeat=n):
            visit("".join(t))
    chars = sorted({c for s in found.values() for c in s})
    for t in itertools.product(chars, repeat=4):
        visit("".join(t))
    for s in list(found.values()):
        for c in chars:
            visit(s + c) if len(s) == 4 else None
    return found


def _ligs(shaper, text):
    """[(index of last char, ligature glyph)] for every ligature formed in `text`."""
    return [(i, g) for i, g in enumerate(shaper(text)) if g.endswith(".liga")]


def samples() -> list[str]:
    lines = (ROOT / "tests" / "code-samples.txt").read_text().splitlines()
    return [l for l in lines if l and not l.startswith(("# ", "## "))]


def accepted() -> set[str]:
    lines = (ROOT / "tests" / "accepted-differences.txt").read_text().splitlines()
    return {l.split("\t")[0] for l in lines if l and not l.startswith("# ")}


def sample_diffs(jbm, new):
    """Samples where the two fonts form different ligatures (and the difference isn't accepted)."""
    ok = accepted()
    out = []
    for line in samples():
        a, b = set(_ligs(jbm, line)), set(_ligs(new, line))
        if a != b and line not in ok:
            out.append((line, sorted(g for _, g in b - a), sorted(g for _, g in a - b)))
    return out


def committed(path: str, rev: str) -> bytes | None:
    try:
        return subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True, check=True).stdout
    except subprocess.CalledProcessError:
        return None


def ranges(cps: list[int]) -> str:
    out, cps = [], sorted(cps)
    for _, grp in itertools.groupby(enumerate(cps), lambda p: p[1] - p[0]):
        grp = [c for _, c in grp]
        out.append(f"U+{grp[0]:04X}" + (f"–U+{grp[-1]:04X}" if len(grp) > 1 else ""))
    return ", ".join(out)


def check_style(style: str, rev: str) -> list[str]:
    errors = []
    name = f"{FAMILY} {style}"
    ttf_data = (ROOT / "ttf" / f"{name}.ttf").read_bytes()
    new = Shaper(ttf_data)
    tt = new.tt

    widths = {w for w, _ in tt["hmtx"].metrics.values()}
    if len(widths) != 1:
        errors.append(f"advance widths {sorted(widths)}")
    if (tt["hhea"].ascent, tt["hhea"].descent) != (LINE_METRICS["ascent"], LINE_METRICS["descent"]):
        errors.append("hhea metrics")
    if tt["name"].getDebugName(1) != FAMILY or tt["name"].getDebugName(2) != style:
        errors.append("family/style name")

    jbm = Shaper((CACHE / "jetbrains-mono" / "fonts" / "ttf" / STYLES[style]["jbm"]).read_bytes())
    expected = ligature_set(jbm)
    missing = [s for s in expected.values() if not new.ligature(s)]
    if missing:
        errors.append(f"missing ligatures: {' '.join(missing)}")

    recipes = load_recipes()
    jbm_names = set(jbm.order)
    native_only = [seq for seq, r in recipes.items() if r.glyph_name not in jbm_names]
    for seq in native_only:
        if new.ligature(seq) is None and not new(seq)[-1].endswith(".liga"):
            errors.append(f"native ligature {seq!r} does not apply")

    # JetBrains Mono is the reference for *when* ligatures form, on real-world code samples.
    for line, ours, theirs in sample_diffs(jbm, new):
        errors.append(f"ligatures differ from JetBrains Mono in {line!r}: ours {ours}, JetBrains Mono {theirs} "
                      "(fix the rules or add the line to tests/accepted-differences.txt)")

    for s in ("<=", ">=", "==", "!=", "===", "!=="):
        if any(g.endswith(".liga") for g in new(s, {"ss01": True})):
            errors.append(f"ss01 does not disable {s}")

    for cp, label in SAMPLE_ICONS.items():
        if cp not in new.cmap:
            errors.append(f"missing {label} (U+{cp:04X})")

    otf = Shaper((ROOT / "otf" / f"{name}.otf").read_bytes())
    for s in ["a->b", "x == y", "<!-- -->", "|||>", "abc", "\U000f0001"]:
        if otf(s) != new(s):
            errors.append(f"otf shapes {s!r} differently")

    liga_glyphs = [g for g in tt.getGlyphOrder() if g.endswith(".liga")]
    native_names = {r.glyph_name for r in recipes.values()}
    native_count = sum(g in native_names for g in liga_glyphs)
    if native_count != len(liga_glyphs):
        errors.append(f"ligature glyphs still from JetBrains Mono: {sorted(set(liga_glyphs) - native_names)}")
    report = [f"## {name}", f"- glyphs: {len(tt.getGlyphOrder())}, code points: {len(new.cmap)}",
              f"- ligatures: {len(expected) + len(native_only)} (JetBrains Mono's {len(expected)} + "
              f"{' '.join(native_only)}); behaviour matches JetBrains Mono on {len(samples())} code samples",
              f"- native ligature glyphs: {native_count}/{len(liga_glyphs)}"]
    old_data = committed(f"ttf/{name}.ttf", rev)
    if old_data:
        old = Shaper(old_data)
        lost = sorted(set(old.cmap) - set(new.cmap))
        gained = sorted(set(new.cmap) - set(old.cmap))
        report.append(f"- vs {rev}: +{len(gained)} / -{len(lost)} code points")
        if lost:
            report.append(f"  - no longer present: {ranges(lost)}")
    report += [f"- ERROR: {e}" for e in errors] or ["- OK"]
    print("\n".join(report), flush=True)
    return errors


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--against", default="HEAD", help="git revision of the fonts to compare with")
    ap.add_argument("styles", nargs="*", default=list(STYLES))
    a = ap.parse_args()
    failures = sum(len(check_style(s, a.against)) for s in a.styles)
    sys.exit(1 if failures else 0)
