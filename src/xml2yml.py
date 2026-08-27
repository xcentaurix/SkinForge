# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# The inverse of yml2xml.py: turns plain XML (skin.xml / *.xmlinc) into the
# YAML dialect (skin.yml / *.ymlinc) yml2xml.py reads. See that file and
# SkinForge/README.md for the schema itself; this file only needs to walk it
# in the other direction.
#
# Two different parsers are used, each for the right job:
#   - The outer XML container syntax (tags/attributes/comments/nesting) is a
#     small hand-rolled recursive-descent parser, same rationale as
#     yml2xml.py's hand-rolled YAML reader: no dependency beyond what ships
#     with Python, matching xmlinc.py's own approach to XML.
#   - The Python dict literal inside a <convert type="..."> template block
#     (see below) is parsed with the standard `ast` module. That content
#     really is Python source, and `ast` - part of the interpreter itself,
#     not a third-party package - is the correct tool for parsing Python,
#     the same way the hand-rolled reader is the correct tool for the small
#     YAML subset. Reimplementing a Python-expression parser by hand (for
#     operator precedence, unary minus, nested calls, ...) would just be a
#     worse copy of what `ast` already does. Needs Python 3.9+ (ast.unparse).
#
# This dialect assumes no mixed content: an element either holds only child
# elements (a container) or only text (a leaf), never both - true of every
# real skin.xml in this codebase, and the same assumption yml2xml.py's
# renderer makes on the way back.
#
# xmlinc's eval(formula) wrapper (e.g. position="0,eval($screen_height-48)")
# is compile-time plumbing, not part of the formula, so attribute values are
# unwrapped to just the formula on the way into YAML (see stripEval()).
# yml2xml.py's wrapEval() puts eval(...) back on the way to XML, using a
# heuristic since the YAML no longer carries an explicit marker for it.
#
# A <convert> block's template isn't rendered as a raw mirror of the Python
# call syntax - see toDomainCell()/parseConvertTemplate() below and
# SkinForge/README.md for the domain-level "cell"/"fields" schema this
# produces, hiding MultiContentEntry*/RT_*/font-index plumbing for the shapes
# actually seen in this codebase (falls back to a lossless "raw" field, same
# shape as before, for anything that doesn't match one of those shapes).


import argparse
import ast
import sys
from FileUtils import readFile, writeFile
from Version import VERSION


TEMPLATE_KEYS = (
    "template", "fonts", "itemHeight", "selectionEnabled",
    "scrollbarMode", "itemWidth", "orientation",
)
INDENT = "  "


class Commented:
    def __init__(self, value, comment=None):
        self.value = value
        self.comment = comment


class RawExpr(str):
    """A string that must render as bare YAML text (an identifier or Python
    expression), not a quoted YAML string - the reverse of the "raw" concept
    in yml2xml.py, here decided from the Python AST rather than a key name."""


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------

ENTITIES = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}


def xmlUnescape(text):
    for name, char in ENTITIES.items():
        text = text.replace(f"&{name};", char)
    return text


class XmlParser():
    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.n = len(text)

    def skipSpace(self):
        while self.pos < self.n and self.text[self.pos].isspace():
            self.pos += 1

    def parseDocument(self):
        self.skipSpace()
        if self.text.startswith("<?", self.pos):
            self.pos = self.text.index("?>", self.pos) + 2
        self.skipSpace()
        while self.text.startswith("<!--", self.pos):
            self.skipComment()
            self.skipSpace()
        return self.parseElement()

    def skipComment(self):
        self.pos = self.text.index("-->", self.pos) + 3

    def parseName(self):
        start = self.pos
        while self.pos < self.n and (self.text[self.pos].isalnum() or self.text[self.pos] in "_:.-"):
            self.pos += 1
        return self.text[start:self.pos]

    def parseAttrValue(self):
        quote = self.text[self.pos]
        self.pos += 1
        end = self.text.index(quote, self.pos)
        value = self.text[self.pos:end]
        self.pos = end + 1
        return xmlUnescape(value)

    def parseElement(self):
        assert self.text[self.pos] == "<"
        self.pos += 1
        tag = self.parseName()
        attrs = {}
        while True:
            self.skipSpace()
            if self.text.startswith("/>", self.pos):
                self.pos += 2
                return tag, attrs, None, None
            if self.text[self.pos] == ">":
                self.pos += 1
                break
            name = self.parseName()
            self.skipSpace()
            assert self.text[self.pos] == "="
            self.pos += 1
            self.skipSpace()
            attrs[name] = self.parseAttrValue()

        children, text = self.parseContent()
        end_tag = self.parseName()
        assert end_tag == tag, f"mismatched close tag: <{tag}> ... </{end_tag}>"
        self.skipSpace()
        assert self.text[self.pos] == ">"
        self.pos += 1
        return tag, attrs, children, text

    def parseContent(self):
        children = []
        pending_comment = None
        text_parts = []
        while True:
            if self.text.startswith("</", self.pos):
                self.pos += 2
                break
            if self.text.startswith("<!--", self.pos):
                start = self.pos + 4
                end = self.text.index("-->", start)
                pending_comment = self.text[start:end].strip()
                self.pos = end + 3
                continue
            if self.text[self.pos] == "<":
                node = self.parseElement()
                children.append(Commented(node, pending_comment))
                pending_comment = None
                continue
            next_lt = self.text.index("<", self.pos)
            text_parts.append(self.text[self.pos:next_lt])
            self.pos = next_lt

        if children:
            return children, None
        text = xmlUnescape("".join(text_parts).strip())
        return None, (text if text else None)


# ---------------------------------------------------------------------------
# Python-template parsing (the <convert> special case), via `ast`
# ---------------------------------------------------------------------------

def exprToValue(node):
    if isinstance(node, ast.Call):
        result = {"call": node.func.id}
        if node.args:
            result["args"] = [exprToValue(a) for a in node.args]
        if node.keywords:
            result["kwargs"] = {kw.arg: exprToValue(kw.value) for kw in node.keywords}
        return result
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
        return -node.operand.value
    if isinstance(node, (ast.Tuple, ast.List)):
        return [exprToValue(e) for e in node.elts]
    if isinstance(node, ast.Name):
        return RawExpr(node.id)
    return RawExpr(ast.unparse(node))  # e.g. flags OR-chains, "e - 485" grid math


def parseConvertTemplate(text):
    """Returns a dict body (fonts/template/itemHeight/...) if `text` is a
    TemplatedMultiContent(Ex) dict literal, else None (plain text convert)."""
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return None
    if not isinstance(tree.body, ast.Dict):
        return None
    top = {}
    for key_node, value_node in zip(tree.body.keys, tree.body.values):
        if not isinstance(key_node, ast.Constant) or key_node.value not in TEMPLATE_KEYS:
            return None  # not our template shape - leave as plain text
        top[key_node.value] = exprToValue(value_node)
    if "template" not in top:
        return None
    return top


# ---------------------------------------------------------------------------
# Domain-level cell schema: hides MultiContentEntry*/RT_*/font-index plumbing
# for the shapes actually seen in this codebase (see SkinForge/README.md).
# Anything that doesn't match one of these exact shapes falls back to a "raw"
# field carrying the untouched {call, args?, kwargs?} - never lossy, just not
# upgraded. Resolving a tuple-index (value: 0) to a semantic name (startHM)
# is explicitly out of scope: that needs a per-plugin mapping (e.g.
# TVMagazineCockpit/Index.py's `idx` dict) this tool has no way to discover.
# ---------------------------------------------------------------------------

TEXT_REQUIRED_KWARGS = {"pos", "size", "font", "flags", "text"}
TEXT_ALLOWED_KWARGS = TEXT_REQUIRED_KWARGS | {"color", "color_sel"}
ICON_REQUIRED_KWARGS = {"pos", "size", "png", "flags"}
PROGRESS_REQUIRED_KWARGS = {"pos", "size", "percent"}
PROGRESS_ALLOWED_KWARGS = PROGRESS_REQUIRED_KWARGS | {
    "borderWidth", "foreColor", "foreColorSelected", "backColor"}
BORDER_TEXT_KWARGS = {"pos", "size", "font", "flags", "text", "border_width", "border_color"}


def resolveFontIndex(fonts, index):
    family, size = fonts[index]["args"]
    return f"{family};{size}"


def mergeRect(kwargs):
    pos, size = kwargs["pos"], kwargs["size"]
    return [pos[0], pos[1], size[0], size[1]]


def toDomainField(entry, fonts):
    """Returns (kind, field) for one template entry - kind is text/icon/
    progress when the call matches one of those exact known shapes, else
    "raw" (field is then the original {call, args?, kwargs?} untouched)."""
    call = entry["call"]
    kwargs = entry.get("kwargs", {})
    keys = set(kwargs.keys())
    has_args = "args" in entry

    if (not has_args and call == "MultiContentEntryText"
            and TEXT_REQUIRED_KWARGS <= keys <= TEXT_ALLOWED_KWARGS):
        field = {
            "rect": mergeRect(kwargs), "font": resolveFontIndex(fonts, kwargs["font"]),
            "flags": kwargs["flags"], "value": kwargs["text"],
        }
        for k in ("color", "color_sel"):
            if k in kwargs:
                field[k] = kwargs[k]
        return "text", field

    if (not has_args and call == "MultiContentEntryPixmapAlphaBlend"
            and keys == ICON_REQUIRED_KWARGS):
        return "icon", {"rect": mergeRect(kwargs), "flags": kwargs["flags"], "value": kwargs["png"]}

    if (not has_args and call == "MultiContentEntryProgress"
            and PROGRESS_REQUIRED_KWARGS <= keys <= PROGRESS_ALLOWED_KWARGS):
        field = {"rect": mergeRect(kwargs), "value": kwargs["percent"]}
        for k in ("borderWidth", "foreColor", "foreColorSelected", "backColor"):
            if k in kwargs:
                field[k] = kwargs[k]
        return "progress", field

    return "raw", entry


def detectBorder(entries, fonts):
    """If entries[0] is the empty-text border-box trick (a full MultiContent
    Text entry whose only purpose is drawing a border, since text=""  never
    renders anything), pulls it out as (border_dict, width, remaining). Match
    must be exact - anything that deviates stays a normal field instead of
    being force-fit, so this can never lose information."""
    if not entries:
        return None, None, entries
    first = entries[0]
    kwargs = first.get("kwargs", {})
    if (first["call"] != "MultiContentEntryText" or "args" in first
            or set(kwargs.keys()) != BORDER_TEXT_KWARGS
            or kwargs.get("text") != ""
            or list(kwargs.get("pos", [])) != [0, 0]):
        return None, None, entries
    border = {
        "width": kwargs["border_width"],
        "color": kwargs["border_color"],
        "font": resolveFontIndex(fonts, kwargs["font"]),
        "flags": kwargs["flags"],
    }
    return border, kwargs["size"][0], entries[1:]


def toDomainCell(body):
    fonts = body.get("fonts", [])
    entries = body["template"]

    cell = {}
    if "itemHeight" in body:
        cell["itemHeight"] = body["itemHeight"]
    for key in ("itemWidth", "selectionEnabled", "scrollbarMode", "orientation"):
        if key in body:
            cell[key] = body[key]

    border, width, entries = detectBorder(entries, fonts)
    if border is not None:
        cell["width"] = width
        cell["border"] = border

    cell["fields"] = [
        {kind: field} for kind, field in (toDomainField(entry, fonts) for entry in entries)
    ]
    return cell


# ---------------------------------------------------------------------------
# YAML rendering
# ---------------------------------------------------------------------------

def stripEval(value):
    """Replace every eval(<formula>) in an attribute value with just
    <formula> - xmlinc's eval() wrapper is compile-time plumbing, not part
    of the formula itself, so it doesn't need to clutter the YAML. Scans by
    matching parens (not a regex) so a formula containing its own parens,
    e.g. eval(($width-100)/2), still unwraps correctly. yml2xml.py's
    wrapEval() puts the eval(...) back on the way to XML."""
    out = []
    i = 0
    n = len(value)
    while i < n:
        if value.startswith("eval(", i):
            depth = 1
            j = i + 5
            while j < n and depth > 0:
                if value[j] == "(":
                    depth += 1
                elif value[j] == ")":
                    depth -= 1
                j += 1
            out.append(value[i + 5:j - 1])
            i = j
        else:
            out.append(value[i])
            i += 1
    return "".join(out)


def yamlScalar(value):
    if isinstance(value, RawExpr):
        return str(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return str(value)


def renderFlow(value):
    if isinstance(value, list):
        return "[" + ", ".join(renderFlow(v) for v in value) + "]"
    if isinstance(value, dict) and "call" in value:
        return renderCallFlow(value)
    return yamlScalar(value)


def renderCallFlow(node):
    parts = [f"call: {node['call']}"]
    if "args" in node:
        parts.append(f"args: {renderFlow(node['args'])}")
    if "kwargs" in node:
        kw = ", ".join(f"{k}: {renderFlow(v)}" for k, v in node["kwargs"].items())
        parts.append(f"kwargs: {{{kw}}}")
    return "{" + ", ".join(parts) + "}"


def renderCallBlock(node, indent, lines):
    prefix = INDENT * indent
    lines.append(f"{prefix}- call: {node['call']}")
    if "args" in node:
        lines.append(f"{prefix}{INDENT}args: {renderFlow(node['args'])}")
    if "kwargs" in node:
        lines.append(f"{prefix}{INDENT}kwargs:")
        for k, v in node["kwargs"].items():
            lines.append(f"{prefix}{INDENT}{INDENT}{k}: {renderKwargValue(k, v)}")


def renderKwargValue(key, value):
    # Cosmetic only: a *Color*/*colour* kwarg holding a non-negative int came
    # from a hex literal in every real template in this codebase (colors are
    # never meaningfully decimal) - render it back as hex for readability,
    # even though Python's int has no memory of which base it was written in.
    if (isinstance(value, int) and not isinstance(value, bool)
            and value >= 0 and "color" in key.lower()):
        return f"0x{value:06x}"
    if isinstance(value, list):
        return renderFlow(value)
    if isinstance(value, dict) and "call" in value:
        return renderCallFlow(value)
    return yamlScalar(value)


def renderConvertBody(body, indent, lines):
    prefix = INDENT * indent
    lines.append(f"{prefix}template:")
    for entry in body["template"]:
        renderCallBlock(entry, indent + 1, lines)
    if "fonts" in body:
        lines.append(f"{prefix}fonts:")
        for font in body["fonts"]:
            renderCallBlock(font, indent + 1, lines)
    for key in ("itemHeight", "itemWidth", "selectionEnabled", "scrollbarMode", "orientation"):
        if key in body:
            lines.append(f"{prefix}{key}: {yamlScalar(body[key])}")


def renderDomainField(kind, field, indent, lines):
    prefix = INDENT * indent
    if kind == "raw":
        # field is an untouched {call, args?, kwargs?} - same shape/rendering
        # renderCallBlock() uses, just without its own leading "- call:" line
        # since the fields-list loop below already emitted the dash+kind line.
        lines.append(f"{prefix}call: {field['call']}")
        if "args" in field:
            lines.append(f"{prefix}args: {renderFlow(field['args'])}")
        if "kwargs" in field:
            lines.append(f"{prefix}kwargs:")
            for k, v in field["kwargs"].items():
                lines.append(f"{prefix}{INDENT}{k}: {renderKwargValue(k, v)}")
        return
    for key, value in field.items():
        lines.append(f"{prefix}{key}: {renderKwargValue(key, value)}")


def renderDomainCell(cell, indent, lines):
    prefix = INDENT * indent
    for key in ("itemHeight", "itemWidth", "width", "selectionEnabled", "scrollbarMode", "orientation"):
        if key in cell:
            lines.append(f"{prefix}{key}: {renderKwargValue(key, cell[key])}")
    if "border" in cell:
        lines.append(f"{prefix}border:")
        for key, value in cell["border"].items():
            lines.append(f"{prefix}{INDENT}{key}: {renderKwargValue(key, value)}")
    lines.append(f"{prefix}fields:")
    dash_indent = indent + 1
    for item in cell["fields"]:
        (kind, field), = item.items()
        lines.append(f"{INDENT * dash_indent}- {kind}:")
        renderDomainField(kind, field, dash_indent + 2, lines)


def renderAttrs(attrs, indent, lines):
    prefix = INDENT * indent
    for k, v in attrs.items():
        lines.append(f'{prefix}{k}: "{stripEval(v)}"')


def renderBody(tag, attrs, children, text, body_indent, lines):
    """Renders an element's body (everything after its own "tag:" or
    "- tag:" line, which the caller already emitted) at `body_indent` units.

    A child list item is always a single-key wrapper {tag: {...}} (see
    module docstring), so its OWN nested content sits two units past the
    dash, not one: the dash's "- " prefix is exactly one INDENT-width wide,
    so "tag:" already reads as one unit deeper than the dash itself, and
    that key's own value-mapping is one further unit past that. Contrast
    renderCallBlock() below, where "call"/"args"/"kwargs" are sibling keys
    of the SAME mapping (call's value is inline) and so sit one unit past
    the dash, not two - verified against real files both ways rather than
    derived from first principles alone.
    """
    if tag == "convert" and text:
        template = parseConvertTemplate(text)
        if template is not None:
            lines.append(f'{INDENT * body_indent}type: "{attrs.get("type", "")}"')
            lines.append(f"{INDENT * body_indent}cell:")
            renderDomainCell(toDomainCell(template), body_indent + 1, lines)
            return

    renderAttrs(attrs, body_indent, lines)
    if text is not None:
        lines.append(f'{INDENT * body_indent}text: "{text}"')
    elif children:
        lines.append(f"{INDENT * body_indent}children:")
        dash_indent = body_indent + 1
        for item in children:
            if item.comment:
                lines.append(f"{INDENT * dash_indent}# {item.comment}")
            child_tag, child_attrs, child_children, child_text = item.value
            lines.append(f"{INDENT * dash_indent}- {child_tag}:")
            renderBody(child_tag, child_attrs, child_children, child_text, dash_indent + 2, lines)


def xml2yml(text):
    tag, attrs, children, text_content = XmlParser(text).parseDocument()
    lines = [f"{tag}:"]
    renderBody(tag, attrs, children, text_content, 1, lines)
    return "\n".join(lines) + "\n"


def parseArgs(argv):
    parser = argparse.ArgumentParser(prog="xml2yml.py")
    parser.add_argument("-i", dest="srcinfile", required=True, help="source .xml/.xmlinc file")
    parser.add_argument("-o", dest="srcoutfile", required=True, help="destination .yml/.ymlinc file")
    return parser.parse_args(argv)


def main(argv):
    print(f"xml2yml {VERSION}")
    args = parseArgs(argv)
    print("src in file: " + args.srcinfile)
    print("src out file: " + args.srcoutfile)

    output = xml2yml(readFile(args.srcinfile))
    writeFile(args.srcoutfile, output)

    print("xml2yml done.")


if __name__ == "__main__":
    main(sys.argv[1:])
