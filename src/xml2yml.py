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


import argparse
import ast
import sys
from FileUtils import readFile, writeFile
from Version import VERSION


TEMPLATE_KEYS = ("template", "fonts", "itemHeight", "selectionEnabled",
                  "scrollbarMode", "itemWidth", "orientation")
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
# YAML rendering
# ---------------------------------------------------------------------------

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


def renderAttrs(attrs, indent, lines):
    prefix = INDENT * indent
    for k, v in attrs.items():
        lines.append(f'{prefix}{k}: "{v}"')


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
            renderConvertBody(template, body_indent, lines)
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
