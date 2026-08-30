# SkinForge - Next generation Enigma2 skin design with YAML language and compiler

## Introduction
An enigma2 skin is natively just a flat XML file: no includes, no macros, no relative positioning, no variables, no reuse. If you maintain more than one plugin and want a consistent look — or want to change a button style in one place instead of in every `skin.xml` that copy-pasted it — you're stuck hand-editing pixel coordinates in N files at once.

SkinForge doesn't change what enigma2 itself understands — it compiles a richer source down to the plain, flat XML enigma2 actually loads. There are two ways to author that source:

1. **YAML** — the primary, recommended way to write a skin: a readable YAML dialect (`skin.yml` / `*.ymlinc`) that losslessly round-trips to/from XML+, compiled end-to-end with `ymlcompile`.
2. **XML+** — the original hierarchical XML dialect (includes, variables, relative positioning, compile-time color/formula checking), kept for backward compatibility and for plugins that already have XML+ source, compiled end-to-end with `xmlcompile`.

Both share the same compiler and the same `Common` directory of reusable building blocks (buttons, title bars, colors, ...) — YAML source is simply converted to XML+ first, then compiled the same way. Pick whichever fits how a given plugin is currently authored; neither is deprecated, and there's no need to migrate an existing XML+ skin just to use SkinForge.

## Quick start

For a plugin whose skin source is written in YAML:
```
ymlcompile <domain>
```
For a plugin whose skin source is written in XML+:
```
xmlcompile <domain>
```
`<domain>` is a plugin name (resolved the same way `getdomain` resolves it elsewhere in this toolset) or `.` for the current directory. Either command, run from anywhere:

- walks every skin variant under `$HOME/git/dev/<domain>/src/skin/*` (`default`, `SimpleTenEighty`, `MetrixHD`, ...),
- (`ymlcompile` only) converts any `*.yml`/`*.ymlinc`/`*.noymlinc` source that changed — in both the plugin's own tree and the shared `Common` tree — to XML+ via `yml2xmldomain`/`xml2ymldomain` and reformats it via `xmlprettydomain`,
- compiles the result with `xmlinc` against `$HOME/git/dev/Common`, and
- reformats the compiled output with `xmlpretty`,

writing the final, flat XML enigma2 loads to `$HOME/git/rel/<domain>/src/skin/<variant>/skin.xml`. Only variants that already have a `skin.xml` checked into the destination tree are compiled, and (for `ymlcompile`) only ones whose source actually changed get reconverted — both commands are safe to run repeatedly as part of a normal build.

`yml2xmldomain`, `xml2ymldomain`, and `xmlprettydomain` are the per-domain building blocks `ymlcompile` itself calls — each takes `<domain-or-.> [skin]` (`skin` defaults to `default`) and processes just that one variant's files. Use them directly when you want to convert or reformat a single variant without running a full compile.

## Authoring in YAML

Skin sources are written as YAML — a `skin.yml` (a full document) or a `*.ymlinc` (an include fragment, the YAML equivalent of `.xmlinc`) — and converted to and from plain XML+ by `yml2xml`/`xml2yml` (the single-file tools `ymlcompile` drives via `yml2xmldomain`/`xml2ymldomain`).

### Usage

```
yml2xml <source .yml/.ymlinc file> <destination .xml/.xmlinc file>   # YAML -> XML+, feed the result to xmlinc
xml2yml <source .xml/.xmlinc file> <destination .yml/.ymlinc file>   # XML+ -> YAML, the reverse
```

### Mapping

- An element `<tag attr="val">...children...</tag>` becomes `{tag: {attr: "val", ..., children: [...]}}`.
- A standalone `<!-- comment -->` before a child element becomes a standalone `# comment` right before the matching list item (and back).
- A document with more than one top-level element — a real possibility for a `.xmlinc`/`.noxmlinc` *fragment* (spliced into a parent by literal text substitution, so it isn't required to have a single root the way a real XML document is) — becomes a top-level `- tag: {...}` dash list instead of the usual single `tag: {...}` mapping, the same shape a `children:` list already uses:
  ```yaml
  - eLabel: {backgroundColor: "separator", position: "0,e-56", size: "e,2"}
  - eLabel: {backgroundColor: "barBG", position: "0,e-55", size: "e,55"}
  ```
  A single-root document (by far the common case) keeps the plain `tag: {...}` form unchanged.

### The `<convert>` template special case

A `<convert type="...">` block holding a `TemplatedMultiContent`/`TemplatedMultiContentEx` template is a Python dict literal, not markup — `RT_*`/`BT_*` flag algebra, `MultiContentEntry*` call names, and numeric font indices. Rather than mirroring that syntax 1:1, it's translated into a domain-level `cell:` describing what's actually shown in each row:

```yaml
cell:
  itemHeight: 150
  fonts:
    - "Regular;32"
    - "Regular;20"
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

- **Three field kinds cover every real template in this codebase**: `text` (from `MultiContentEntryText`), `icon` (from `MultiContentEntryPixmapAlphaBlend`, or `MultiContentEntryPixmapAlphaTest` — marked with a `variant: "AlphaTest"` key, omitted for the far more common Blend case), `progress` (from `MultiContentEntryProgress`) — each only when the call has exactly the plain kwarg set observed in practice. Anything else (`Rectangle`, `LinearGradient*`, `ProgressPixmap`, or a call with an unusual extra kwarg like `cornerRadius`) falls back to a `raw` field carrying the untouched `{call, args?, kwargs?}` shape described below — never lossy, it just doesn't get the readability upgrade. A `text` field's `font:` is itself optional — some plugins omit `font=` and let enigma2 default it, and that's preserved as an absent key rather than forced to a guessed value.
- **The empty-text border trick is recognized and hidden**: a `MultiContentEntryText(text="", border_width=..., border_color=...)` spanning the cell (the common way to draw a cell's frame) is pulled out of `fields:` entirely into `cell.border` and `cell.width`.
- **`cell.fonts` is the source template's `"fonts"` list, kept verbatim, same order, same positions** — not deduplicated or renumbered, and never dropped, even for an entry no `font=N` anywhere in the template currently points to. `font=N` is a positional reference something outside this one `<convert>` block may rely on, so round-tripping must never renumber or delete a slot just because nothing here currently uses it. A plain two-arg `gFont(family, size)` entry renders as the same `"Family;Size"` string every `font:` reference elsewhere uses (as above); anything else (e.g. `parseFont(...)`) falls back to the verbose `{call, args}` form, still inside `fonts:`.
- **`cell.vars` covers `TemplatedMultiContentEx`'s local-variable feature** — some plugins declare a `"var": (name := expr, ...)` tuple of walrus-bound values ahead of `"template"` and reference them throughout its `pos=`/`size=` expressions (grid math shared across several rows/columns, computed once). Preserved as an ordered list of the exact binding text, since order matters (a later binding can reference an earlier one by name) and the right-hand side is an arbitrary Python expression, not typed data:
  ```yaml
  cell:
    vars:
      - "ih := 70"
      - "hspace := 10"
      - "x1 := hspace//2+thumb_w+hspace"
    fields:
      - icon:
          rect: [hspace//2, (ih-thumb_h)//2, thumb_w, thumb_h]   # rect: freely mixes var names, literals, and grid math
          ...
  ```

- **`MultiContentTemplateColor(n)` still nests inside a color-ish key** exactly as before: `color: {call: MultiContentTemplateColor, args: [24]}`.
- **Not in scope**: resolving `value: 0` to a semantic name (`value: startHM`) — that needs a per-plugin tuple-index mapping (e.g. a screen's own `Index.py`) this tool has no generic way to discover, so `value:` stays the raw index/literal, same information as `text=`/`png=`/`percent=` always held.

- **Every entry factory is covered the same generic way** — `Text`, `Pixmap`, `PixmapAlphaTest`, `PixmapAlphaBlend`, `Progress`, `ProgressPixmap`, `Rectangle`, `LinearGradient`, `LinearGradientAlphaBlend` (the complete list in `Components/MultiContent.py`) — the `call` name is just emitted as-is.
- **`TemplatedMultiContentEx`'s `e`/`c` grid variables work in `pos=`/`size=` arithmetic** (and inside a domain field's `rect:`): `pos: [e - 350, 15]`.
- **Kwarg values are quoted strings by default** (real Python string literals) — *except* `flags`, `call`, and `direction`, the three keys that hold code (`RT_*`/`BT_*`/`GRADIENT_*` constants, a callable name) rather than data. This is decided by key name, not by how the value was written: YAML's own parser can't tell a quoted string from a bare one apart once parsed, so quoting style alone can't carry the distinction through a round trip.

### Formatting conventions

`yml2xml`, `xml2yml`, and `xmlpretty` all independently enforce the same conventions on a `<convert>` block's Python-source body, so a file generated by one and reformatted by another never disagrees with itself:

- `pos=(x,y)`/`size=(w,h)` tuples, `gFont(family,size)` calls, and `flags` OR-chains (`A|B`) stay **tight** — no space after the comma or around `|` — even though every other comma (between kwargs, between list items) does get a space. This matches how these are overwhelmingly hand-written across the real plugins in this codebase.
- Strings always use `"`, never `'`.
- `"key": value` object pairs (`itemHeight`, `fonts`, ...) always have a space after the colon.
- A raw-preserved convert body (one `parseConvertTemplate` doesn't recognize the shape of, e.g. a plugin-specific type with extra top-level keys) still gets its outer indentation normalized — the opening `{`/closing `}` line up with the `<convert>` tag itself, one level deeper for its own keys — without touching a single character of content it doesn't understand.

## Backward compatibility: the XML+ compiler (`xmlinc`)

`xmlinc` reads a skin source file that mixes ordinary enigma2 XML with a small set of extra constructs, resolves all of it, and writes out a single plain XML file with nothing left in it that enigma2 wouldn't understand natively. This is the original SkinForge authoring language; `xmlcompile` drives it end-to-end for a plugin whose source is written directly in XML+ rather than YAML.

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

`xmlcompile`/`ymlcompile` call this per skin variant as part of a full build; run it directly only when working on a single file in isolation.

## Other tools

Everything below operates on already-flat XML (or SVG) and doesn't involve the `xmlinc` include/variable/formula language.

| Tool | Usage | Purpose |
|---|---|---|
| `xmlscale` | `xmlscale <scaling factor> <source file> [destination file]` | Scale every position/size in an XML file by a factor (defaults to overwriting the source) |
| `xmlmerge` | `xmlmerge <source file 1> <source file 2> <destination file>` | Merge two XML files into one |
| `xmlpretty` | `xmlpretty [source file/dir] [destination file/dir]` | Check an XML file for well-formedness and reformat it, including plugin-specific normalization of a `<convert>` block's Python-source body (see [Formatting conventions](#formatting-conventions)); defaults to the current directory for both source and destination |
| `xmlsplit` | `xmlsplit <input file>` | Split a combined XML file into its screen parts |
| `svgscale` | `svgscale <scaling factor> <svg file> <destination file>` | Scale a single SVG (PC only — `librsvg2-bin` isn't available on the box) |
| `svgscaledir` | `svgscaledir <scaling factor> <directory>` | Scale every SVG under a directory, recursively |

## Installation
No package available yet, just clone the repo:
```
git clone git@github.com:xcentaurix/SkinForge.git
```


## Limitations
- Tested on OpenViX and OpenATV with DM900.
