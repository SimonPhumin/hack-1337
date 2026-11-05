"""Name, metric and sanity fixes applied after patching and adding the ligatures."""
from fontTools.ttLib import TTFont

from config import FAMILY, LINE_METRICS, UPSTREAMS, VERSION

REPO_URL = "https://github.com/SimonPhumin/hack-1337"

COPYRIGHT = (
    "Copyright (c) 2018 Source Foundry Authors / Copyright (c) 2003 by Bitstream, Inc. All Rights Reserved.\n"
    "Programming ligatures drawn from Hack's own strokes for Hack 1337.\n"
    "Nerd Fonts glyphs by Ryan L McIntyre and the Nerd Fonts contributors.\n"
    "Hack 1337 by Simon Phumin Schweikert."
)

LICENSE = (
    "Hack is Copyright 2018 Source Foundry Authors and licensed under the MIT License; "
    "Bitstream Vera and DejaVu portions are under their respective licenses "
    "(https://github.com/source-foundry/Hack/blob/master/LICENSE.md).\n\n"
    "Nerd Fonts glyphs are licensed by their respective authors "
    "(https://github.com/ryanoasis/nerd-fonts/blob/master/LICENSE)."
)


def finalize(font: TTFont, style: str, win_metrics: tuple[int, int]) -> None:
    ps_family = FAMILY.replace(" ", "")
    ps_name = f"{ps_family}-{style.replace(' ', '')}"
    versions = ", ".join(f"{v['name']} {v['version']}" for v in UPSTREAMS.values() if not v.get("test_only"))

    name = font["name"]
    name.names = [r for r in name.names if r.platformID == 3 and r.nameID not in (16, 17, 21, 22, 25)]
    for name_id, value in {
        0: COPYRIGHT,
        1: FAMILY,
        2: style,
        3: f"{VERSION};{ps_name}",
        4: f"{FAMILY} {style}",
        5: f"Version {VERSION}; {versions}",
        6: ps_name,
        11: REPO_URL,
        13: LICENSE,
        14: f"{REPO_URL}#license",
    }.items():
        name.setName(value, name_id, 3, 1, 0x409)

    font["head"].fontRevision = float(VERSION)

    # Line spacing: the Nerd Font patcher unifies hhea/typo/win and sets USE_TYPO_METRICS.
    # Keep Hack 1337's behaviour instead: tight hhea/typo, Hack's original usWin* values
    # (which Windows uses for both spacing and clipping, so accents are never cut off).
    hhea, os2 = font["hhea"], font["OS/2"]
    hhea.ascent, hhea.descent, hhea.lineGap = LINE_METRICS["ascent"], LINE_METRICS["descent"], LINE_METRICS["lineGap"]
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = hhea.ascent, hhea.descent, hhea.lineGap
    os2.usWinAscent, os2.usWinDescent = win_metrics
    os2.fsSelection &= ~(1 << 7)

    for table in ("FFTM", "PfEd", "DSIG"):
        if table in font:
            del font[table]

    widths = {w for w, _ in font["hmtx"].metrics.values()}
    if len(widths) != 1 or not font["post"].isFixedPitch:
        raise SystemExit(f"{ps_name}: not monospaced (advance widths {sorted(widths)})")
