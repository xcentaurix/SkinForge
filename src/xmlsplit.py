# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import sys
import getopt
import xml.etree.ElementTree as ET
from xml.dom import minidom
from FileUtils import readFile, writeFile


def pretty_file(src_file, dst_file):
    print(f"src_file: {src_file}")
    print(f"dst_file: {dst_file}")

    tree = ET.parse(src_file)
    root = tree.getroot()
    xml_string = ET.tostring(root, encoding="utf-8", method="xml")
    xml_string = minidom.parseString(xml_string).toprettyxml(indent="\t")
    lines = [line for line in xml_string.splitlines() if line.split()]
    xml_string = "\n".join(lines)
    xml_string = xml_string.replace("&quot;", '"')
    # print(xml_string)
    writeFile(dst_file, xml_string)


def save_element_to_file(element, filename):
    filename += ".xmlinc"
    tree = ET.ElementTree(element)
    tree.write(filename)
    pretty_file(filename, filename)
    xmlinc = readFile(filename).splitlines()
    del xmlinc[0]
    xmlinc2 = "\n".join(xmlinc)
    writeFile(filename, xmlinc2)


def xmlsplit(src):
    xml_string = readFile(src)
    tree = ET.ElementTree(ET.fromstring(xml_string))
    root = tree.getroot()
    skinlines = ["<skin>"]
    for node in root:
        print(node.tag)
        if node.tag == "components":
            skinlines.append("<components>")
            for comp in node:
                filename = comp.tag + "_" + comp.attrib["type"]
                save_element_to_file(comp, filename)
                skinlines.append(f'<xmlinc name="{filename}"/>')
            skinlines.append("</components>")
        elif node.tag == "layouts":
            skinlines.append("<layouts>")
            for comp in node:
                filename = comp.tag + "_" + comp.attrib["name"]
                save_element_to_file(comp, filename)
                skinlines.append(f'<xmlinc name="{filename}"/>')
            skinlines.append("</layouts>")
        elif node.tag in {"windowstyle", "windowstylescrollbar"}:
            filename = node.tag + "_" + node.attrib["id"]
            save_element_to_file(node, filename)
            skinlines.append(f'<xmlinc name="{filename}"/>')
        else:
            if "name" in node.attrib:
                filename = node.tag + "_" + node.attrib["name"]
            else:
                filename = node.tag
            save_element_to_file(node, filename)
            skinlines.append(f'<xmlinc name="{filename}"/>')
    skinlines.append("</skin>")
    skin = "\n".join(skinlines)
    writeFile("skin_split.xml", skin)
    pretty_file("skin_split.xml", "skin_split.xml")


def main(argv):
    src = ""
    opts = []

    # print("argv: " + str(argv))
    try:
        opts, _args = getopt.getopt(argv, "s:", [])
        # print("opts: " + str(opts))
    except getopt.GetoptError as e:
        print("Error: " + str(e))

    if len(opts) < 1:
        print("python xmlsplit.py -s <src file>")
        sys.exit(2)

    for opt, arg in opts:
        if opt == "-i":
            src = arg

    print("src: " + src)

    xmlsplit(src)


if __name__ == "__main__":
    main(sys.argv[1:])
    sys.exit()
