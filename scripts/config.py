"""Pinned upstream inputs and per-style settings for the Hack 1337 build."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
CACHE = BUILD / "cache"
FAMILY = "Hack 1337"
VERSION = "2.000"

UPSTREAMS = {
    "hack": {
        "version": "3.003",
        "url": "https://github.com/source-foundry/Hack/releases/download/v3.003/Hack-v3.003-ttf.zip",
        "sha256": "0c2604631b1f055041c68a0e09ae4801acab6c5072ba2db6a822f53c3f8290ac",
    },
    "jetbrains-mono": {
        "version": "2.304",
        "url": "https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip",
        "sha256": "6f6376c6ed2960ea8a963cd7387ec9d76e3f629125bc33d1fdcd7eb7012f7bbf",
    },
    "nerd-fonts": {
        "version": "3.5.1",
        "url": "https://github.com/ryanoasis/nerd-fonts/releases/download/v3.5.1/FontPatcher.zip",
        "sha256": "42bcb32145499a35732274c7fc48deb434ad0d2e0e118f98527c1479c6fa251a",
    },
}

# Hack style -> JetBrains Mono instance whose stroke weight matches once scaled to Hack's grid
# (hyphen thickness: Hack Regular 164 = JBM Regular 164; Hack Bold 291 ~ JBM ExtraBold 287).
STYLES = {
    "Regular":    {"hack": "Hack-Regular.ttf",    "jbm": "JetBrainsMono-Regular.ttf"},
    "Italic":     {"hack": "Hack-Italic.ttf",     "jbm": "JetBrainsMono-Italic.ttf"},
    "Bold":       {"hack": "Hack-Bold.ttf",       "jbm": "JetBrainsMono-ExtraBold.ttf"},
    "Bold Italic": {"hack": "Hack-BoldItalic.ttf", "jbm": "JetBrainsMono-ExtraBoldItalic.ttf"},
}

# Hack 1337 line metrics: tighter than stock Hack on macOS/Linux (hhea + typo = 1.0 em, no line gap).
# Windows (usWin*) keeps Hack's original values.
LINE_METRICS = {"ascent": 1556, "descent": -492, "lineGap": 0}
