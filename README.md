# SkinForge - An Enigma2 Skin Compiler & A step towards hierarchical skin design

## Introduction
An enigma2 skin is natively just a flat XML file: no includes, no macros, no relative positioning, no variables, no reuse. If you maintain more than one plugin and want a consistent look — or want to change a button style in one place instead of in every `skin.xml` that copy-pasted it — you're stuck hand-editing pixel coordinates in N files at once.

SkinForge doesn't change what enigma2 itself understands. Instead it lets you **author** skins in a richer, hierarchical dialect and **compiles** that down to the plain, flat XML enigma2 actually loads. The compiler, `xmlinc`, is the core of the project; the rest of the tools are support utilities around it (scaling, merging, pretty-printing, splitting).

## The compiler: `xmlinc`

`xmlinc` reads a skin source file that mixes ordinary enigma2 XML with a small set of extra constructs, resolves all of it, and writes out a single plain XML file with nothing left in it that enigma2 wouldn't understand natively.

### What it resolves

- **Hierarchical includes** — `<xmlinc file="name" .../>` pulls in `name.xmlinc` (or any file with an explicit extension) in place, recursively. Included files are searched in order next to the source file, in its parent directory, in a shared "common" directory, and in that common directory's parent — so a plugin can override a shared building block just by placing a same-named file closer to its own skin.
- **Parameters on includes, as `$vars`** — every extra attribute on an `<xmlinc>` tag becomes a `$name` variable visible inside the included file (`size=` additionally exposes `$width`/`$height`). This is what makes an include reusable rather than a copy-paste target:

  ```xml
  <!-- Example.xml -->
  <xmlinc file="test" source="title"/>
  ```
  ```xml
  <!-- test.xmlinc -->
  <widget ... source=$source .../>
  ```
  compiles to:
  ```xml
  <widget ... source="title" .../>
  ```
- **Relative positioning** — a `position="x,y"` attribute on an `<xmlinc>` tag is added to every widget position inside that include, recursively through nested includes. A shared `buttons.xmlinc` block of four pixmaps at `0,0` / `300,0` / `600,0` / `900,0` becomes a single reusable "button bar" you place anywhere just by choosing where to `<xmlinc>` it:

  ```xml
  <xmlinc file="buttons" position="100,200"/>
  ```
  places the first button at `100,200`, the second at `400,200`, and so on.
- **Global variables** — `<global name="x" value="y"/>` defines `$x`; `<screen size="w,h" .../>` implicitly defines `$screen_width`/`$screen_height` for the whole file. `$vars` don't need to be their own token — `picon$index` substitutes just the `$index` part, so variables can be embedded in literals.
- **Colors, checked at compile time** — any `...Color="name"` attribute is validated against colors declared via `<color name="x" value="y"/>` (normally collected from a shared `screenpart_colors.xmlinc`) plus a small built-in list of names the device's own base skin already defines (`black`, `white`, `background`, ...). An unknown color name — almost always a typo — fails loudly at compile time instead of silently rendering wrong on the box:
  ```
  ERROR: color hilite not defined
  ```
- **Formula evaluation** — `eval(...)` runs the enclosed expression as real arithmetic, so positions and sizes can be computed instead of hand-calculated: `eval(($width-100)/2)` centers a 100px-wide element. Division is automatically treated as integer (floor) division since pixel coordinates can't be fractional; if a formula still produces a float (e.g. from a scaling ratio) the result is rounded to the nearest pixel rather than truncated.
- **Font/size sanity check** — every widget with both a `font` and a `size` is checked against a minimum-line-height heuristic; a `size` too short for its `font` produces a warning identifying the screen, widget, font variable, and both values, catching text that would otherwise render clipped on the actual device:
  ```
  WARNING: screen=MyScreen screen_h=1080 widget=title font=$FB_medium size: 30 < font: 37.33333333333333
  ```
- **Verbatim passthrough** — an include named `applet_*` is inlined as raw text without any of the above processing, for embedding pre-rendered or foreign XML snippets unchanged.

### Usage

```
xmlinc <source-file> <destination-file> <destination-dir> <common-dir>
```
- `source-file` — the hierarchical skin source (e.g. `skin.xml`, or a screen's own `.xml`)
- `destination-file` — where the fully-resolved, flat XML is written
- `destination-dir` — the directory `xmlinc` treats as the plugin's own skin directory when searching for includes
- `common-dir` — a shared directory of reusable `.xmlinc` building blocks (buttons, title bars, colors, ...) used across plugins

Run it as a build step before packaging a plugin — the checked-in skin source stays hierarchical and reusable; the file enigma2 actually loads at runtime is the compiled, flat output.

## Authoring in YAML (experimental)

Skin sources can optionally be written as YAML instead of XML — a `skin.yml` (a full document) or a `*.ymlinc` (an include fragment, the YAML equivalent of `.xmlinc`) — and converted to and from plain XML. This is new and still evolving; XML via `xmlinc` remains the primary, supported way to author skins.

### Usage

```
yml2xml <source .yml/.ymlinc file> <destination .xml/.xmlinc file>   # YAML -> XML, feed the result to xmlinc
xml2yml <source .xml/.xmlinc file> <destination .yml/.ymlinc file>   # XML -> YAML, the reverse
```

### Mapping

- An element `<tag attr="val">...children...</tag>` becomes `{tag: {attr: "val", ..., children: [...]}}`.
- A standalone `<!-- comment -->` before a child element becomes a standalone `# comment` right before the matching list item (and back).

### The `<convert>` template special case

A `<convert type="...">` block holding a `TemplatedMultiContent`/`TemplatedMultiContentEx` template is a Python dict literal, not markup — `RT_*`/`BT_*` flag algebra, `MultiContentEntry*` call names, and numeric font indices. Rather than mirroring that syntax 1:1, it's translated into a domain-level `cell:` describing what's actually shown in each row:

```yaml
cell:
  itemHeight: 150
  border: {width: 1, color: 0x595959, font: "Regular;20", flags: RT_VALIGN_CENTER}
  fields:
    - text:
        rect: [5, 5, 55, 25]        # merges pos=/size= into [x, y, w, h]
        font: "Regular;20"          # resolved from the fonts index, same font="..." syntax every other widget uses
        flags: RT_HALIGN_LEFT | RT_VALIGN_CENTER
        value: 0                    # renamed from text= - still the raw tuple index, see note below
    - icon:
        rect: [0, 5, 35, 35]
        flags: BT_SCALE
        value: 23                   # renamed from png=
    - progress:
        rect: [90, 5, 90, 14]
        value: -22                  # renamed from percent=
        foreColor: "#bababa"
```

- **Three field kinds cover every real template in this codebase**: `text` (from `MultiContentEntryText`), `icon` (from `MultiContentEntryPixmapAlphaBlend`), `progress` (from `MultiContentEntryProgress`) — each only when the call has exactly the plain kwarg set observed in practice. Anything else (`Rectangle`, `LinearGradient*`, `Pixmap`/`PixmapAlphaTest`, `ProgressPixmap`, or a `Text`/`Icon`/`Progress` call with an unusual extra kwarg like `cornerRadius`) falls back to a `raw` field carrying the untouched `{call, args?, kwargs?}` shape described below — never lossy, it just doesn't get the readability upgrade.
- **The empty-text border trick is recognized and hidden**: a `MultiContentEntryText(text="", border_width=..., border_color=...)` spanning the cell (the common way to draw a cell's frame) is pulled out of `fields:` entirely into `cell.border` and `cell.width`.
- **`MultiContentTemplateColor(n)` still nests inside a color-ish key** exactly as before: `color: {call: MultiContentTemplateColor, args: [24]}`.
- **Not in scope**: resolving `value: 0` to a semantic name (`value: startHM`) — that needs a per-plugin tuple-index mapping (e.g. a screen's own `Index.py`) this tool has no generic way to discover, so `value:` stays the raw index/literal, same information as `text=`/`png=`/`percent=` always held.

A `raw` field (or an older, low-level `.ymlinc` written before this schema existed) uses the same generic representation for any `MultiContentEntry*`/`gFont` call:

```yaml
- raw:
    call: MultiContentEntryRectangle
    kwargs:
      pos: [0, 0]
      size: [50, 50]
      backgroundColor: 0x123456
```

- **Every entry factory is covered the same generic way** — `Text`, `Pixmap`, `PixmapAlphaTest`, `PixmapAlphaBlend`, `Progress`, `ProgressPixmap`, `Rectangle`, `LinearGradient`, `LinearGradientAlphaBlend` (the complete list in `Components/MultiContent.py`) — the `call` name is just emitted as-is.
- **`TemplatedMultiContentEx`'s `e`/`c` grid variables work in `pos=`/`size=` arithmetic** (and inside a domain field's `rect:`): `pos: [e - 350, 15]`.
- **Kwarg values are quoted strings by default** (real Python string literals) — *except* `flags`, `call`, and `direction`, the three keys that hold code (`RT_*`/`BT_*`/`GRADIENT_*` constants, a callable name) rather than data. This is decided by key name, not by how the value was written: YAML's own parser can't tell a quoted string from a bare one apart once parsed, so quoting style alone can't carry the distinction through a round trip.

See `TVMagazineCockpit/src/skin/default/screenpart_EventCell.ymlinc` and `MovieCockpit/src/skin/default/skin.xml`'s `TemplatedMultiContentEx` block for worked examples of the full domain schema (icon/text/progress mix, nested colors, `e`-arithmetic).

### Implementation notes

- `yml2xml` hand-rolls a parser for the specific subset of YAML this dialect uses (block mappings/sequences, flow lists, quoted/bare scalars, `|` block scalars, standalone comments) rather than using a full YAML implementation — deliberately, to avoid a third-party dependency that may not be installed in the box's Python.
- `xml2yml` hand-rolls its XML-reading side for the same reason, but parses the Python dict literal inside a `<convert>` block with the standard-library `ast` module instead of hand-rolling a Python-expression parser — that content really is Python source, and `ast` (part of the interpreter itself, not a pip package) is the right tool for it. Requires Python 3.9+ (`ast.unparse`).

## Other tools

Everything below operates on already-flat XML (or SVG) and doesn't involve the `xmlinc` include/variable/formula language.

| Tool | Usage | Purpose |
|---|---|---|
| `xmlscale` | `xmlscale <scaling factor> <source file> [destination file]` | Scale every position/size in an XML file by a factor (defaults to overwriting the source) |
| `xmlmerge` | `xmlmerge <source file 1> <source file 2> <destination file>` | Merge two XML files into one |
| `xmlpretty` | `xmlpretty [source file/dir] [destination file/dir]` | Check an XML file for well-formedness and reformat it; defaults to the current directory for both source and destination |
| `xmlsplit` | `xmlsplit <input file>` | Split a combined XML file back into its parts |
| `svgscale` | `svgscale <scaling factor> <svg file> <destination file>` | Scale a single SVG (PC only — `librsvg2-bin` isn't available on the box) |
| `svgscaledir` | `svgscaledir <scaling factor> <directory>` | Scale every SVG under a directory, recursively |

## Installation
No package available yet, just clone the repo:
```
git clone git@github.com:xcentaurix/SkinForge.git
```

## Status
This project is work in progress.


## Limitations
- Tested on OpenViX and OpenATV with DM900.
