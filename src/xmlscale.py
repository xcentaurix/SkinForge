# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import os
import sys
import re
import getopt
import xml.etree.ElementTree as ET
# import xml.dom.minidom as minidom
from fractions import Fraction
from FileUtils import readFile, writeFile
from Version import VERSION

ending_values = ["Width", "Height", "Font", "Offset", "Margin", "HPos"]
key_values = ["xres", "yres", "lineSpacing", "value", "textX", "textY", "pixmapX", "pixmapY", "separation", "rcheight",
              "rcheighthalf", "font", "position", "size", "size2", "offset", "margin", "cornerDia", "selectionDia", "width", "cornerRadius"]
sep1 = (" ", '"', "{", "[", "(", ",", ";", ":", "=", "}", "]", ")")
sep2 = ("+", "-", "*", "/", "%")


def split(s, sep):
    # print("split: s: %s" % s)
    pattern = f"({'|'.join(re.escape(c) for c in sep)})"
    o = re.split(pattern, s)
    o = [item for item in o if item != '']
    # print("split: o: %s" % o)
    return o


def scaleFormula(scale, value):
    # print("scaleFormula: %s" % value)
    words = split(value, sep1 + sep2)
    formula = ""
    for word in words:
        try:
            value = scaleValue(scale, int(word))
        except Exception:  # as e:
            # print("exception: %s" % e)
            value = word
        formula += value
    # print("formula: %s" % formula)
    return formula


def scaleValue(scale, value):
    # print("scaleValue: %s, %s" % (scale, value))
    if value in {'(', ','}:
        raise ValueError(f"invalid value: {value}")
    if isinstance(value, str):
        if value.startswith("eval("):
            value = scaleFormula(scale, value)
    try:
        if int(value) > 1:
            # Add 0.5 and truncate to get "round half up" behavior
            scaled_value = int(value) * scale
            value = int(scaled_value +
                        0.5) if scaled_value >= 0 else int(scaled_value - 0.5)
    except Exception:  # as e:
        # print("exception: %s" % e)
        pass
    # print("scaleValue result: %s" % value)
    return str(value)


class Template():
    def __init__(self):
        self.sep = ("{", "[", "(", ",", ":", "=", "}", "]", ")")

    def clean(self, i):
        o = i.replace("\n", " ").replace("\t", " ")
        o = " ".join(o.split())
        return o

    def parse(self, scale, i):
        # print("parse: %s" % i)
        o = []
        n = 0
        while n < len(i):
            k = i[n].strip()
            if k in {"pos", "size"}:
                o.append(f"{k}=({scaleValue(scale, i[n + 3])},{scaleValue(scale, i[n + 5])})")
                n += 7
            elif k in {"gFont"}:
                o.append(f"{k}({scaleValue(scale, i[n + 2])},{scaleValue(scale, i[n + 4])})")
                n += 6
            elif k in {'"itemHeight"', '"itemWidth"'}:
                o.append(f"{k}:{scaleValue(scale, i[n + 2])}")
                n += 3
            elif k in {":"}:
                if i[n + 1] == "(":
                    snum = i[n + 2]
                    try:
                        int(snum)
                        o.append(f"{k}({scaleValue(scale, i[n + 2])}")
                        n += 3
                    except Exception:
                        o.append(k)
                        n += 1
                else:
                    o.append(k)
                    n += 1
            else:
                o.append(k)
                n += 1
        return o

    def split(self, s, sep):
        # print("split: s: %s" % s)
        pattern = f"({'|'.join(re.escape(c) for c in sep)})"
        # print("pattern: %s" % pattern)
        r = re.split(pattern, s)
        r = [item for item in r if item != '']
        # print("split: r: %s" % r)
        return r

    def joinFormulas(self, words):
        # print("eval: words: %s" % words)
        output = []
        i = 0
        while i < len(words):
            if words[i] == "eval":
                formula = ""
                i += 1
                level = 0
                while level > 0 or not formula:
                    if words[i] in {"(", ")"}:
                        level += 1 if words[i] == "(" else -1
                    formula += words[i]
                    i += 1
                # result = int(eval(formula))
                # output.append(str(result))
                output.append("eval" + formula)
            else:
                output.append(words[i])
                i += 1
        # print("output: %s" % output)
        return output

    def scaleTemplate(self, scale, i):
        # print("scaleTemplate: %s: %s" % (scale, i))
        result = self.clean(i)
        # print("clean:\n%s" % result)
        result = self.split(result, self.sep)
        # print("split:\n%s" % result)
        result = self.joinFormulas(result)
        # print("joinFormulas:\n%s" % result)
        result = self.parse(scale, result)
        # print("parse:\n%s" % result)
        result = "".join(result)
        # print("join:\n%s" % result)
        return result


class XML(Template):
    def __init__(self):
        Template.__init__(self)

    def scaleColumn(self, scale, _key, value):
        # print("key: %s, value: %s" % (key, value))
        out = value
        if "," in value:
            numbers = value.split(",")
            out = f"{scaleValue(scale, numbers[0])},{scaleValue(scale, numbers[1])},{numbers[2]},{numbers[3]},{scaleValue(scale, numbers[4])},{numbers[5]},{numbers[6]}"
        # print("scale_column: %s" % out)
        return out

    def scaleNumber(self, scale, key, value):
        # print("key: %s, value: %s" % (key, value))
        out = str(value)
        if key in key_values or any(key.endswith(end) for end in ending_values):
            if "," in value:
                numbers = value.split(",")
                out = f"{scaleValue(scale, numbers[0])},{scaleValue(scale, numbers[1])}"
            elif ";" in value:
                numbers = value.split(";")
                out = f"{numbers[0]};{scaleValue(scale, numbers[1])}"
            else:
                out = scaleValue(scale, value)
        # print("out: %s" % out)
        return str(out)

    def scalePointer(self, scale, pointer):
        # print("scale_pointer: %s, %s" % (scale, pointer))
        elems = pointer.split(":")
        pic = elems[0]
        dims = elems[1]
        dim = dims.split(",")
        pointer = f"{pic}:{scaleValue(scale, dim[0])},{scaleValue(scale, dim[1])}"
        # print(pointer)
        return pointer

    def addRoot(self, lines):
        lines = ["<root>"] + lines + ["</root>"]
        return lines

    def removeRoot(self, lines):
        olines = []
        for line in lines:
            if line and not ("<root>" in line or "</root>" in line or "<?xml" in line):
                olines.append(line)
        # print("olines: %s" % olines)
        return olines

    def processFile(self, scale, src, dst):
        # print("process_file: scale: %s, src: %s, dst: %s" % (scale, src, dst))
        lines = readFile(src).splitlines()
        if os.path.splitext(src)[1] == ".xmlinc":
            lines = self.addRoot(lines)
        xml_string = "\n".join(lines)
        tree = ET.ElementTree(ET.fromstring(xml_string))
        root = tree.getroot()
        for node in tree.iter():
            for elem in node:  # .iter():
                # print(node.tag, elem.tag)
                if node.tag == "widget" and elem.tag == "convert" and elem.attrib["type"] == "TemplatedMultiContent":
                    if elem.text:
                        elem.text = self.scaleTemplate(scale, elem.text)
                else:
                    for key in elem.attrib:
                        # print("--- ", key, elem.attrib[key])
                        if key.startswith("column"):
                            elem.attrib[key] = self.scaleColumn(
                                scale, key, elem.attrib[key])
                        elif key == "pointer":
                            # print(elem.attrib[key])
                            elem.attrib[key] = self.scalePointer(
                                scale, elem.attrib[key])
                        elif key in {"backgroundPixmap", "selectionPixmap"}:
                            # value = elem.attrib[key]
                            pass
                        else:
                            elem.attrib[key] = self.scaleNumber(
                                scale, key, elem.attrib[key])

        xml_string = ET.tostring(root, encoding="unicode", method="xml")

        # Reorder all XML element attributes alphabetically for consistent output

        xml_string = re.sub(
            r'<(\w+)\s+([^>]*?)/?>',
            lambda m: self._reorder_attributes_alphabetically(m.group(0)),
            xml_string
        )

        # print("xml_string: %s" % xml_string)
        xml_string = xml_string.replace(" />", "/>")
        # xml_string = minidom.parseString(xml_string).toprettyxml(indent="\t")
        lines = [line for line in xml_string.splitlines() if line.split()]
        # print(lines)
        if os.path.splitext(src)[1] == ".xmlinc":
            lines = self.removeRoot(lines)
        # print(lines)
        xml_string = "\n".join(lines)
        xml_string = xml_string.replace("&quot;", '"') + "\n"
        # print(xml_string)
        writeFile(dst, xml_string)

    def _reorder_attributes_alphabetically(self, element_tag):
        """Reorder all element attributes alphabetically for consistent output"""

        # Handle both self-closing tags and opening tags
        self_closing = element_tag.endswith('/>')

        # Extract tag name and attributes
        if self_closing:
            tag_match = re.match(r'<(\w+)\s+([^>]*?)/>', element_tag)
        else:
            tag_match = re.match(r'<(\w+)\s+([^>]*?)>', element_tag)

        if not tag_match:
            return element_tag

        tag_name = tag_match.group(1)
        attrs_string = tag_match.group(2) if tag_match.group(2) else ""

        # Extract all attributes
        attrs = {}
        attr_pattern = r'(\w+)="([^"]*)"'

        for match in re.finditer(attr_pattern, attrs_string):
            attr_name, attr_value = match.groups()
            attrs[attr_name] = attr_value

        # Build the reordered tag with alphabetically sorted attributes
        result = f'<{tag_name}'

        for attr in sorted(attrs.keys()):
            result += f' {attr}="{attrs[attr]}"'

        # Preserve self-closing format
        if self_closing:
            result += '/>'
        else:
            result += '>'

        return result


def scaleSkin(argv):
    print(f"xmlscale {VERSION}")
    scale = ""
    src = ""
    dst = ""
    opts = []

    try:
        opts, _args = getopt.getopt(argv, "s:i:o:", [])
    except getopt.GetoptError as e:
        print(f"Error: {e}")
        sys.exit(2)

    if len(opts) < 3:
        print('Usage: python xmlscale.py -s <scale> -i <src> -o <dst>')
        sys.exit(2)

    for opt, arg in opts:
        if opt == "-s":
            scale = arg
        elif opt == "-i":
            src = os.path.normpath(arg)
        elif opt == "-o":
            dst = os.path.normpath(arg)

    if not dst:
        dst = src

    print("processing skin...")
    scale = float(Fraction(scale))
    print('scale: ' + str(scale))
    print('src: ' + src)
    print('dst: ' + dst)

    if os.path.splitext(src)[1] == ".tpl":
        writeFile(dst, Template().scaleTemplate(scale, readFile(src)))
    else:
        XML().processFile(scale, src, dst)

    print("xmlscale done.")


if __name__ == "__main__":
    scaleSkin(sys.argv[1:])
