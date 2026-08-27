# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# Converts the YAML skin dialect (skin.yml / *.ymlinc, see TVMagazineCockpit's
# skin/default for real examples) back into the plain XML xmlinc/enigma2
# understand. This is a hand-rolled parser for the specific subset of YAML
# that dialect actually uses - block mappings/sequences, flow lists ([a, b]),
# quoted/bare scalars, "|" block scalars, and standalone "#" comments - not a
# general-purpose YAML implementation, on purpose: it mirrors xmlinc.py's own
# hand-rolled XML handling rather than adding a third-party dependency that
# may not exist in the box's python (see SkinForge/README.md).
#
# Mapping (the inverse of what produced the .yml files):
#   - a mapping {tag: {attr: "val", ..., children: [...]}} becomes
#     <tag attr="val" ...>...children...</tag> (self-closed if no children
#     and no text).
#   - {tag: {..., text: "..."}} becomes <tag ...>text</tag>.
#   - a comment on a sequence item is emitted as <!-- comment --> immediately
#     before that item.
#   - SPECIAL CASE: a "convert" node holding a "cell" key (rather than plain
#     text/children) is a TemplatedMultiContent(Ex) template in the domain-
#     level schema documented in SkinForge/README.md and xml2yml.py's module
#     docstring - fromDomainCell() expands its text/icon/progress/raw fields
#     back into the {template, fonts, itemHeight, ...} shape described next,
#     which renderConvertTemplate()/pyCall() below turn into the actual
#     Python dict literal a <convert type="...">...</convert> block needs as
#     its text content. A "convert" node holding template/fonts/itemHeight/
#     selectionEnabled/scrollbarMode/itemWidth/orientation directly (the
#     older, low-level form - still what a "raw" domain field's own call/
#     kwargs use) is accepted the same way, without a "cell" wrapper.
#     Entries are {call: Name, args: [...]} and/or {call: Name, kwargs: {...}}
#     mappings, each rendered back to "Name(*args, **kwargs)" Python source.
#   - a plain <convert type="X">text</convert> (no "cell" or template keys)
#     is just an ordinary text-content element and goes through the normal
#     path.
#
# Scalar typing: a quoted YAML string ("...") and a plain/bare one both parse
# to a Python str - YAML discards the distinction, so it can't be used to
# decide code-vs-data. Instead, a few kwarg keys are hard-coded as "always
# raw source, never string-quoted" because they are the only ones that hold
# Python expressions rather than data in this domain: "call" (a callable
# name), "flags" (RT_*/BT_* constants, possibly OR'd), and "direction" (the
# GRADIENT_VERTICAL/GRADIENT_HORIZONTAL constants taken by the two
# LinearGradient entry types). Every other string value - including plain
# attributes and "text" - renders as a literal.
#
# Every factory in Components/MultiContent.py is supported the same generic
# way - {call: Name, args: [...]} / {call: Name, kwargs: {...}} renders to
# "Name(*args, **kwargs)" regardless of which one it names (Text, Pixmap,
# PixmapAlphaTest, PixmapAlphaBlend, Progress, ProgressPixmap, Rectangle,
# LinearGradient, LinearGradientAlphaBlend) - there's nothing type-specific
# to implement per entry. The one function that needs special support is
# MultiContentTemplateColor(n): unlike the entry types, it's never a
# top-level template item - it's used *nested inside* a color-ish kwarg
# value, e.g. color: {call: MultiContentTemplateColor, args: [24]}. See
# renderValue() below for where a value itself gets checked for "call".


import argparse
import re
import sys
from FileUtils import readFile, writeFile
from Version import VERSION


TEMPLATE_KEYS = (
    "template", "fonts", "itemHeight", "selectionEnabled",
    "scrollbarMode", "itemWidth", "orientation",
)
RAW_KWARG_KEYS = {"call", "flags", "direction"}
INDENT = "\t"
BARE_VAR_RE = re.compile(r"^\$\w+$")


class Commented:
    """Wraps a parsed sequence item together with a standalone comment line
    that preceded it in the source, if any."""

    def __init__(self, value, comment=None):
        self.value = value
        self.comment = comment


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

class YamlParser():
    def __init__(self, text):
        self.entries = []
        for raw in text.split("\n"):
            stripped = raw.rstrip()
            if not stripped.strip():
                continue
            if "\t" in stripped[:len(stripped) - len(stripped.lstrip(" \t"))]:
                print("ERROR: tab used for indentation - YAML indentation must be spaces")
            indent = len(stripped) - len(stripped.lstrip(" "))
            content = stripped.strip()
            is_comment = content.startswith("#")
            self.entries.append((indent, content[1:].strip() if is_comment else content, is_comment))
        self.pos = 0

    def peek(self):
        return self.entries[self.pos] if self.pos < len(self.entries) else None

    def parseDocument(self):
        return self.parseBlock(0)

    def parseBlock(self, indent):
        i = self.pos
        while i < len(self.entries) and self.entries[i][2]:  # skip leading comments
            i += 1
        first = self.entries[i] if i < len(self.entries) else None
        if first is None or first[0] < indent:
            return None
        if first[1].startswith("- "):
            return self.parseSequence(indent)
        return self.parseMapping(indent)

    def parseSequence(self, indent):
        result = []
        pending_comment = None
        while True:
            e = self.peek()
            if e is None or e[0] != indent:
                break
            _, content, is_comment = e
            if is_comment:
                pending_comment = content
                self.pos += 1
                continue
            if not content.startswith("- "):
                break
            self.pos += 1
            value = self.parseSequenceItem(content[2:], indent + 2)
            result.append(Commented(value, pending_comment))
            pending_comment = None
        return result

    def parseSequenceItem(self, first_line, item_indent):
        if not first_line:
            return self.parseBlock(item_indent)
        if ":" not in first_line:
            return self.parseScalar(first_line)
        node = {}
        self.parseInlineKey(node, first_line, item_indent)
        while True:
            e = self.peek()
            if e is None or e[0] != item_indent or e[1].startswith("- "):
                break
            if e[2]:
                self.pos += 1  # skip stray comments between an item's own keys
                continue
            self.pos += 1
            self.parseInlineKey(node, e[1], item_indent)
        return node

    def parseMapping(self, indent):
        node = {}
        while True:
            e = self.peek()
            if e is None or e[0] != indent:
                break
            _, content, is_comment = e
            if is_comment:
                self.pos += 1  # standalone comments before/between keys aren't tracked
                continue
            if content.startswith("- "):
                break
            self.pos += 1
            self.parseInlineKey(node, content, indent)
        return node

    def parseInlineKey(self, node, line, indent):
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest == "|":
            node[key] = self.parseBlockScalar(indent + 2)
        elif rest == "":
            node[key] = self.parseBlock(indent + 2)
        else:
            node[key] = self.parseScalar(rest)

    def parseBlockScalar(self, indent):
        lines = []
        while True:
            e = self.peek()
            if e is None or e[0] < indent:
                break
            self.pos += 1
            lines.append(e[1])
        return "\n".join(lines)

    def parseScalar(self, text):
        if text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        if text.startswith("[") and text.endswith("]"):
            return [self.parseScalar(item) for item in splitFlowItems(text[1:-1])]
        if text.startswith("{") and text.endswith("}"):
            result = {}
            for item in splitFlowItems(text[1:-1]):
                k, _, v = item.partition(":")
                result[k.strip()] = self.parseScalar(v.strip())
            return result
        low = text.lower()
        if low == "true":
            return True
        if low == "false":
            return False
        try:
            return int(text, 16) if low.startswith("0x") else int(text)
        except ValueError:
            pass
        try:
            return float(text)
        except ValueError:
            pass
        return text  # bare scalar - stays a plain str, see module docstring


def splitFlowItems(inner):
    inner = inner.strip()
    if not inner:
        return []
    items = []
    depth = 0
    in_quote = False
    current = ""
    for ch in inner:
        if ch == '"':
            in_quote = not in_quote
            current += ch
        elif ch in "[{" and not in_quote:
            depth += 1
            current += ch
        elif ch in "]}" and not in_quote:
            depth -= 1
            current += ch
        elif ch == "," and depth == 0 and not in_quote:
            items.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        items.append(current.strip())
    return items


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def xmlEscape(value):
    text = str(value)
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def wrapEval(value):
    """Inverse of xml2yml.py's stripEval(): re-wrap a formula segment in
    eval(...) for xmlinc to evaluate at compile time. Splits on "," since
    every real eval() usage in this codebase wraps exactly one comma-segment
    of a position/size pair (e.g. "0,eval($screen_height-48)"), never a
    partial segment. A segment is wrapped only if it references a $var AND
    is more than just that bare reference - a plain "$FR_big" (substitution,
    no eval needed) and TemplatedMultiContentEx's "e"/"c" grid math (no $ at
    all, evaluated separately inside <convert> blocks) both pass through
    untouched."""
    if not isinstance(value, str) or "$" not in value:
        return value
    segments = value.split(",")
    wrapped = [seg if BARE_VAR_RE.match(seg.strip()) or "$" not in seg else f"eval({seg})"
               for seg in segments]
    return ",".join(wrapped)


def renderAttrs(attrs):
    return "".join(f' {k}="{xmlEscape(wrapEval(v))}"' for k, v in attrs.items())


def pyVal(value, raw=False):
    if isinstance(value, dict) and "call" in value:
        return pyCall(value)  # nested call as a value, e.g. MultiContentTemplateColor(24)
    if isinstance(value, list):
        # pos=/size= tuples: every MultiContentEntry* factory takes numeric
        # pairs here, so a string element is always a TemplatedMultiContentEx
        # "e"/"c" expression (e.g. "e - 485"), never literal string data -
        # always raw, unlike a bare kwarg value where raw is key-dependent.
        return "(" + ", ".join(pyVal(v, raw=True) for v in value) + ")"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, str):
        return value if raw else repr(value)
    return repr(value)


def pyCall(node):
    parts = [pyVal(a) for a in node.get("args", [])]
    parts += [f"{k}={pyVal(v, raw=(k in RAW_KWARG_KEYS))}"
              for k, v in node.get("kwargs", {}).items()]
    return f"{node['call']}({', '.join(parts)})"


def unwrap(item):
    return item.value if isinstance(item, Commented) else item


def renderConvertTemplate(body):
    template_lines = ["["]
    for entry in body.get("template", []):
        template_lines.append("    " + pyCall(unwrap(entry)) + ",")
    template_lines.append("]")

    pairs = ['"template": ' + "\n".join(template_lines)]
    if "fonts" in body:
        fonts = ", ".join(pyCall(unwrap(f)) for f in body["fonts"])
        pairs.append(f'"fonts": [{fonts}]')
    for key in ("itemHeight", "itemWidth"):
        if key in body:
            pairs.append(f'"{key}": {body[key]}')
    for key in ("selectionEnabled", "scrollbarMode", "orientation"):
        if key in body:
            pairs.append(f'"{key}": {pyVal(body[key])}')

    return "{" + ",\n".join(pairs) + "}"


# ---------------------------------------------------------------------------
# Domain-level "cell" schema (the inverse of xml2yml.py's toDomainCell()) -
# see that file's module docstring for the schema itself. Reconstructs the
# same {template, fonts, itemHeight, ...} intermediate shape renderConvert
# Template()/pyCall() above already know how to turn into Python source, so
# nothing downstream of fromDomainCell() needs to change for this schema.
# ---------------------------------------------------------------------------

def unwrapField(item):
    (kind, field), = unwrap(item).items()
    return kind, field


def rectToPosSize(rect):
    return [rect[0], rect[1]], [rect[2], rect[3]]


def internFonts(cell):
    """Collects the distinct font strings used (border's font, then each
    text field's, in order), assigning each a stable first-use index -
    unused fonts from the original source (never referenced by any field)
    are dropped, since domain form has no slot to remember a declared-but-
    unused font and it can't affect rendering either way."""
    order = []
    index = {}

    def register(font_str):
        if font_str not in index:
            index[font_str] = len(order)
            order.append(font_str)
        return index[font_str]

    if "border" in cell and "font" in cell["border"]:
        register(cell["border"]["font"])
    for item in cell.get("fields", []):
        kind, field = unwrapField(item)
        if kind == "text" and "font" in field:
            register(field["font"])

    fonts = []
    for font_str in order:
        family, size = font_str.split(";")
        fonts.append({"call": "gFont", "args": [family, int(size)]})
    return fonts, index


def fromDomainField(kind, field, font_index):
    if kind == "raw":
        return field  # untouched {call, args?, kwargs?}

    pos, size = rectToPosSize(field["rect"])

    if kind == "text":
        kwargs = {"pos": pos, "size": size, "font": font_index[field["font"]],
                  "flags": field["flags"], "text": field["value"]}
        for k in ("color", "color_sel"):
            if k in field:
                kwargs[k] = field[k]
        return {"call": "MultiContentEntryText", "kwargs": kwargs}

    if kind == "icon":
        return {"call": "MultiContentEntryPixmapAlphaBlend",
                "kwargs": {"pos": pos, "size": size, "png": field["value"], "flags": field["flags"]}}

    if kind == "progress":
        kwargs = {"pos": pos, "size": size, "percent": field["value"]}
        for k in ("borderWidth", "foreColor", "foreColorSelected", "backColor"):
            if k in field:
                kwargs[k] = field[k]
        return {"call": "MultiContentEntryProgress", "kwargs": kwargs}

    raise ValueError(f"unknown domain field kind: {kind}")


def fromDomainCell(cell):
    fonts, font_index = internFonts(cell)

    template = []
    if "border" in cell:
        b = cell["border"]
        template.append({"call": "MultiContentEntryText", "kwargs": {
            "pos": [0, 0], "size": [cell.get("width", 0), cell.get("itemHeight", 0)],
            "font": font_index[b["font"]], "flags": b["flags"], "text": "",
            "border_width": b["width"], "border_color": b["color"],
        }})

    for item in cell.get("fields", []):
        kind, field = unwrapField(item)
        template.append(fromDomainField(kind, field, font_index))

    body = {"template": template}
    if fonts:
        body["fonts"] = fonts
    for key in ("itemHeight", "itemWidth", "selectionEnabled", "scrollbarMode", "orientation"):
        if key in cell:
            body[key] = cell[key]
    return body


def renderNode(tag, body, level, lines):
    body = body or {}
    prefix = INDENT * level

    if tag == "convert" and ("cell" in body or any(k in body for k in TEMPLATE_KEYS)):
        attr_str = renderAttrs({"type": body.get("type", "")})
        lines.append(f"{prefix}<convert{attr_str}>")
        template_body = fromDomainCell(body["cell"]) if "cell" in body else body
        for line in renderConvertTemplate(template_body).split("\n"):
            lines.append(f"{prefix}{INDENT}{line}" if line else "")
        lines.append(f"{prefix}</convert>")
        return

    children = body.get("children")
    text = body.get("text")
    attrs = {k: v for k, v in body.items() if k not in ("children", "text")}
    attr_str = renderAttrs(attrs)

    if children:
        lines.append(f"{prefix}<{tag}{attr_str}>")
        for item in children:
            if isinstance(item, Commented) and item.comment:
                lines.append(f"{prefix}{INDENT}<!-- {item.comment} -->")
            (child_tag, child_body), = unwrap(item).items()
            renderNode(child_tag, child_body, level + 1, lines)
        lines.append(f"{prefix}</{tag}>")
    elif text is not None:
        lines.append(f"{prefix}<{tag}{attr_str}>{xmlEscape(text)}</{tag}>")
    else:
        lines.append(f"{prefix}<{tag}{attr_str}/>")


def yml2xml(text, is_full_document):
    root = YamlParser(text).parseDocument()
    root_items = list(root.items())
    assert len(root_items) == 1, "document root must have exactly one top-level key"
    tag, body = root_items[0]
    lines = []
    if is_full_document:
        lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    renderNode(tag, body, 0, lines)
    return "\n".join(lines) + "\n"


def parseArgs(argv):
    parser = argparse.ArgumentParser(prog="yml2xml.py")
    parser.add_argument("-i", dest="srcinfile", required=True, help="source .yml/.ymlinc file")
    parser.add_argument("-o", dest="srcoutfile", required=True, help="destination .xml/.xmlinc file")
    return parser.parse_args(argv)


def main(argv):
    print(f"yml2xml {VERSION}")
    args = parseArgs(argv)
    print("src in file: " + args.srcinfile)
    print("src out file: " + args.srcoutfile)

    is_full_document = args.srcinfile.endswith(".yml")
    output = yml2xml(readFile(args.srcinfile), is_full_document)
    writeFile(args.srcoutfile, output)

    print("yml2xml done.")


if __name__ == "__main__":
    main(sys.argv[1:])
