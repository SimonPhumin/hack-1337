# Building Hack 1337

## Quick start

```sh
brew install uv fontforge harfbuzz   # macOS; on Debian/Ubuntu: apt install fontforge python3-fontforge libharfbuzz-bin, plus uv
make fonts      # download pinned upstreams, build ttf/ otf/ woff/ woff2/   (~1 min)
make check      # verify ligatures, metrics, icon coverage; compare with the committed fonts
make previews   # re-render preview/*.png and docs/ligatures.md
```

Everything downloaded or generated goes into `build/` (git-ignored). Upstream versions and their
sha256 checksums are pinned in [`scripts/config.py`](../scripts/config.py).

## Pipeline

`scripts/build.py` runs these steps for each style, in parallel:

| Step | Script | What it does |
| --- | --- | --- |
| 1 | `prepare.py` | Takes stock **Hack 3.003** and applies the Hack 1337 line metrics (see below). |
| 2 | Nerd Fonts `font-patcher` (run by fontforge) | Adds every **Nerd Fonts 3.5.1** icon set as single-width glyphs (`--complete --mono --metrics HHEA`). Icons and Powerline separators are fitted to the 1337 cell height. |
| 3 | `ligaturize.py` | Copies the **JetBrains Mono 2.304** ligatures (details below). |
| 3b | `native.py` | Builds the native ligatures from `src/ligatures/recipes.py`. Each one replaces the JetBrains Mono glyph of the same name, or adds a new ligature with its own rules. |
| 4 | `features.py` | Compiles `src/features/native.fea` together with the generated ligature code. |
| 5 | `finalize.py` | Sets names, version and license strings, restores the Windows metrics, and checks that every glyph has the same advance width. |
| 6 | `export.py` | Writes `.otf` (CFF outlines), `.woff` and `.woff2` from the `.ttf`. |

The build scripts only use [fontTools](https://github.com/fonttools/fonttools) and the official
Nerd Fonts patcher. No third-party ligaturizer code is involved, so the scripts can be MIT
licensed.

### How the ligatures are copied (`scripts/ligaturize.py`)

JetBrains Mono implements ligatures in its `calt` feature as chains of contextual rules. For
`->`, the `-` is replaced by an empty spacer glyph (`SPC`) and the `>` by a one-cell glyph
(`hyphen_greater.liga`) whose drawing extends left over the spacer. The script:

1. Walks every `calt` lookup of JetBrains Mono (and the lookups they call) and rewrites them as
   OpenType feature code. Characters are mapped to Hack's glyph for the same code point.
   Substitutions that would bring in JetBrains Mono letterforms (`colon.case`, `germandbls.calt`)
   are dropped, so Hack keeps its own characters.
2. Copies the 153 ligature and spacer glyphs. Each one is scaled from JetBrains Mono's 600/1000
   grid to Hack's 1233/2048 grid, shifted so JetBrains Mono's math axis (the centre of `-` and
   `=`) sits on Hack's, and re-slanted from 9° to 11° for italics.
3. Matches stroke weights. Scaled to Hack's size, JetBrains Mono **Regular** has exactly Hack
   Regular's 164-unit hyphen. Hack **Bold** (291) is closest to JetBrains Mono **ExtraBold** (287).
   The mapping is in `STYLES` in `config.py`.

The generated feature code for each style is kept at `build/work/<Style>/features.fea`.
`make check` confirms that every JetBrains Mono ligature is reproduced. It also shapes 20,000
random strings with both fonts to confirm the ligatures behave the same, including the cases
where JetBrains Mono deliberately leaves characters alone (e.g. `<-1`).

### Native ligatures (`src/ligatures/recipes.py`)

The goal is to replace every JetBrains Mono ligature glyph with one drawn from Hack's own strokes.
Each recipe is a small Python function that gets a `Kit` for the style being built and returns
the outline, drawn across the ligature's cells:

```python
@ligature("==")
def _(k):
    return _bars(k, "=", 2)          # Hack's '=' bars, stretched across two cells
```

- **Parts and measurements** come from the style's own glyphs: `k.glyph("=")`, `k.bands("≡")`
  (the bars' heights), `k.stroke` (thickness of `-`), `k.bar_width` (thickness of `|`),
  `k.axis` (centre of `= < >`). One recipe therefore gives the right weight in Regular and Bold.
- **Boolean operations** (skia-pathops) merge overlapping parts into clean outlines.
- **Tightened sequences** (`TIGHT`): Hack's glyphs moved closer (`## :: {{ <$> ?:` …), never so
  close that they collide in Bold; `*`, `:` and `.` can be centred on the math axis.
- **Arrows** come from one parametric builder: a shaft (`-` or `=`) plus an end piece on each
  side (`head`, `head2`, `tail`, `tail2`, `bar`, `bar2`) and a shaft (`-`, `=` or `~`, a sine wave
  with the height and weight of Hack's `~`). The `ARROWS` table maps every arrow sequence to
  its spec, e.g. `">->": ("-", "tail", "head")`. Heads are drawn by `_head()`: a mitred chevron
  with Hack's stroke, as tall as Hack's `>` but steeper (`HEAD_ANGLE`). Hack's own `>` is too flat
  to work as an arrowhead.
- **Italics:** Hack Italic keeps most operators upright (`= < > | . ~ ≤ ≥ ≠ ≡`), so recipes use
  the italic glyphs as they are. Only the arrow shafts get slanted ends, matching the italic `-`.
- A recipe whose glyph name JetBrains Mono doesn't have (e.g. `~=`, `..=`) becomes a new
  ligature. `native.py` writes its substitution rules, which run before the JetBrains Mono rules.

`make check` reports progress ("native ligature glyphs: 154/154"). `make previews` renders the result.
When every glyph is native, the remaining step is to replace the JetBrains Mono-derived rules
with rules generated from our own sequence list, and then drop JetBrains Mono.

### Native features (`src/features/`)

`native.fea` holds Hack 1337's own OpenType code. Its lookups are placed *before* the JetBrains
Mono ones, so they can switch ligatures off. Two conveniences:

- `$u003C` in `native.fea` stands for "the glyph for U+003C in this font". The Nerd Fonts patcher
  renames glyphs, so don't hard-code names.
- `glyphs.json` declares extra glyphs as aliases of existing characters (e.g. `less.ss01` looks
  like `<`). The ligature rules don't match aliases, which is how `ss01` keeps comparison
  operators plain.

To add a ligature drawn from Hack's own glyphs, add the glyph (for example as a composite of
existing glyphs in `features.py`) and a rule in `native.fea`. Rules in `native.fea` run first.

### Line metrics

Hack 1337 has a tighter line height than stock Hack. In `hhea` and `OS/2` typo, ascent/descent
are 1556/−492 with no line gap, which is exactly 1 em. macOS and most Linux apps use these
values. `usWinAscent`/`usWinDescent` keep Hack's 1901/483, so Windows spacing is unchanged and
accents are never clipped. Change `LINE_METRICS` in `config.py` to adjust.

## Updating upstreams

Bump the version, URL and sha256 in `scripts/config.py`, then run `make fonts check`. To get a
checksum, run `shasum -a 256` on the downloaded zip. If JetBrains Mono adds ligatures,
`ligaturize.py` picks them up automatically. `make check` reports any rule it couldn't translate.

## History: how 1.x was made

Hack 1337 1.x (2021) was made by hand, with no build scripts:

1. Started from **Hack Nerd Font Mono** as released by Nerd Fonts **2.1**.
2. Added Fira Code **3.1** ligatures (124) with [Ligaturizer](https://github.com/ToxicFrog/Ligaturizer).
3. Set the `hhea`/typo metrics to 1556/−492 (line gap 0), and redrew the
   Powerline glyphs `U+E0A0–E0A2` and `U+E0B0–E0B3` to fit that line height with a little
   overlap, so powerlevel10k segments show no seams.

2.0 rebuilds the same idea from scratch. It keeps the line metrics. It drops the hand-drawn
Powerline glyphs, because Nerd Fonts 3 fits them to the cell itself. It replaces Fira Code 3.1
with JetBrains Mono 2.304, which gains 32 ligatures (e.g. `&&` `|->` `<==>` `/**` `;;;` `{{` `}}`)
and loses 6 Fira-only ones (`www` `**` `%%` `.-` `~=` `..=`).
