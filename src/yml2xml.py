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
#   - SPECIAL CASE: a "convert" node holding template/fonts/itemHeight/
#     selectionEnabled/scrollbarMode/itemWidth/orientation (rather than plain
#     text/children) is a TemplatedMultiContent(Ex) template. Its entries are
#     {call: Name, args: [...]} and/or {call: Name, kwargs: {...}} mappings,
#     each rendered back to "Name(*args, **kwargs)" Python source, and the
#     whole thing reassembled into the {"template": [...], "fonts": [...],
#     ...} dict literal a <convert type="...">...</convert> block needs as
#     its text content.
#   - a plain <convert type="X">text</convert> (no template keys) is just an
#     ordinary text-content element and goes through the normal path.
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
import sys
from FileUtils import readFile, writeFile
from Version import VERSION


TEMPLATE_KEYS = ("template", "fonts", "itemHeight", "selectionEnabled",
                  "scrollbarMode", "itemWidth", "orientation")
RAW_KWARG_KEYS = {"call", "flags", "direction"}
INDENT = "\t"


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
            eindent, content, is_comment = e
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
            eindent, content, is_comment = e
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


def renderAttrs(attrs):
    return "".join(f' {k}="{xmlEscape(v)}"' for k, v in attrs.items())


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


def renderNode(tag, body, level, lines):
    body = body or {}
    prefix = INDENT * level

    if tag == "convert" and any(k in body for k in TEMPLATE_KEYS):
        attr_str = renderAttrs({"type": body.get("type", "")})
        lines.append(f"{prefix}<convert{attr_str}>")
        for line in renderConvertTemplate(body).split("\n"):
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
    (tag, body), = root.items()
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
