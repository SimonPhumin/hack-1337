# Changelog

## 2.0.0

- Reproducible build from pinned upstreams (`make fonts`), documented in `docs/BUILDING.md`.
- Ligatures: switched from Fira Code 3.1 (124) to JetBrains Mono 2.304 (150), copied by our own
  fontTools script. New: `&&` `&&&` `&=` `|->` `|=>` `<-|` `<==>` `<=|` `/**` `//=` `;;;` `???`
  `{{` `}}` `{{--` `--}}` `{!!` `!!}` `{!--` `<#--` `<:<` `<<~` `#:` `:<` `:?` `:?>` `=:` `>:` `>]`
  `@_` `[<` `||-`. Removed (Fira-only): `www` `**` `%%` `.-` `~=` `..=`.
- Native ligatures: all 154 ligature glyphs are drawn from Hack's own strokes
  (`src/ligatures/recipes.py`), so they match Hack's weight in every style. JetBrains Mono now only
  supplies the substitution rules; Fira Code's `~=` and `..=` are back.
- New stylistic set `ss01`: plain comparison operators.
- Nerd Fonts 2.1 → 3.5.1: +9,000 icons (Material Design, Codicons, newer Font Awesome,
  Devicons, Octicons, Seti, Font Logos). The old Material Design range `U+F500–U+FD46` was removed
  upstream; those icons now live at `U+F0001+`.
- Powerline separators are fitted to the Hack 1337 cell by the Nerd Fonts patcher instead of being
  hand-drawn.
- Same tight line metrics as 1.x (1556/−492, no line gap).

## 1.0.0 (2021)

- Hack Nerd Font Mono (Nerd Fonts 2.1) + Fira Code 3.1 ligatures (Ligaturizer), with tighter line
  metrics.
