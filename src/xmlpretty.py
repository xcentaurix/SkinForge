# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0

import os
import sys
import getopt
import re
import xml.etree.ElementTree as ET
from xml.dom import minidom
from FileUtils import readFile, writeFile


def listDir(adir):
    alist = []
    try:
        for afile in os.listdir(adir):
            ext = os.path.splitext(afile)[1]
            if ext in {".xml", ".xmlinc"}:
                alist.append(afile)
    except OSError as e:
        print(f"failed: e: {e}")
    return alist


def add_root(lines):
    lines = ["<root>"] + lines + ["</root>"]
    return lines


def remove_root(ilines):
    olines = []
    for line in ilines:
        if line and not ("<root>" in line or "</root>" in line or "<?xml" in line):
            olines.append(line)
    # print("olines: %s" % olines)
    return olines


def process_file(src_file, dst_file):
    print(f"process_file: {src_file}")
    lines = readFile(src_file).splitlines()
    if os.path.splitext(src_file)[1] == ".xmlinc":
        lines = add_root(lines)
    xml_string = "\n".join(lines)
    tree = ET.ElementTree(ET.fromstring(xml_string))
    root = tree.getroot()
    try:
        xml_string = ET.tostring(root, encoding="unicode", method="xml")
        xml_string = minidom.parseString(
            xml_string.encode("utf-8")).toprettyxml(indent="\t")
        xml_string = re.sub(
            r'<(\w+)\s+([^>]*?)/?>',
            lambda m: reorder_attributes_alphabetically(m.group(0)),
            xml_string
        )
        xml_string = re.sub(
            r'\n([ \t]*)(<convert[^>]*type="TemplatedMultiContent"[^>]*>)(.*?)(</convert>)',
            lambda m: (
                "\n" + m.group(1) + m.group(2) + "\n" +
                format_multicontent(m.group(3), m.group(1)) + "\n" +
                m.group(1) + m.group(4)
            ),
            xml_string,
            flags=re.DOTALL
        )
    except Exception as e:
        print(f"failed to process {src_file}: {e}")
        return
    lines = [line for line in xml_string.splitlines() if line.split()]
    if os.path.splitext(src_file)[1] == ".xmlinc":
        lines = remove_root(lines)
    xml_string = "\n".join(lines)
    xml_string = xml_string.replace("&quot;", '"')
    xml_string += "\n"
    # print(xml_string)
    writeFile(dst_file, xml_string)


def process_files(src, dst):
    if os.path.isfile(src):
        process_file(src, dst)
    else:
        alist = listDir(src)
        for afile in alist:
            # print("afile: %s" % afile)
            if afile != "rcpositions.xml" and not afile.startswith("applet_"):
                process_file(os.path.join(src, afile),
                             os.path.join(dst, afile))


def xmlpretty(argv):
    src = ""
    dst = ""
    opts = []

    try:
        opts, _args = getopt.getopt(argv, "i:o:", ["src=", "dst="])
    except getopt.GetoptError as e:
        print("Error: " + str(e))

    if len(opts) < 2:
        print('Usage: python xmlpretty.py -i <src file/dir> -o <dst file/dir>')
        sys.exit(2)

    for opt, arg in opts:
        if opt in {'-i', '--src'}:
            src = os.path.normpath(arg)
        elif opt in {'-o', '--dst'}:
            dst = os.path.normpath(arg)

    print("prettifying...")
    print('src file/dir: ' + src)
    print('dst file/dir: ' + dst)

    process_files(src, dst)

    print("xmlpretty done.")


def format_multicontent(text, base_indent=""):
    i1 = base_indent + "\t"
    i2 = base_indent + "\t\t"
    text = text.strip()
    text = re.sub(r',\s*(MultiContent\w+)', f',\n{i2}\\1', text)
    text = re.sub(r'\{\s*"template":\s*\[\s*', f'{{\n{i1}"template": [\n{i2}', text)
    text = re.sub(r'\s*\],\s*"fonts"', f'\n{i1}],\n{i1}"fonts"', text)
    text = re.sub(r',\s*"itemHeight"', f',\n{i1}"itemHeight"', text)
    text = re.sub(r'\s*\}\s*$', f'\n{base_indent}}}', text)
    return base_indent + text


def reorder_attributes_alphabetically(element_tag):
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


if __name__ == "__main__":
    xmlpretty(sys.argv[1:])
