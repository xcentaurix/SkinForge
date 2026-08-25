# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import os
import subprocess
import sys
import getopt
import xml.etree.ElementTree as ET
from Version import VERSION


def get_width(filename):
    print(f"get_width: {filename}")
    with open(filename, 'r', encoding='utf-8') as svg_file:
        tree = ET.parse(svg_file)
    root = tree.getroot()
    width = root.get('width')
    try:
        float(width)
    except Exception:
        width = 0
    print(f"get_width: {width}")
    return width


def scale_file(width, src, dst):
    subprocess.run(["rsvg-convert", "-f", "svg", "-w", str(width), src, "-o", dst], check=True)


def process_file(scale, src, dst):
    width = get_width(src)
    if width:
        width = int(float(scale) * float(width))
        scale_file(width, src, dst)
    else:
        print(f"process_file: no width in {src}")


def scale_svg(argv):
    print(f"svgscale {VERSION}")
    scale = ""
    src = ""
    dst = ""
    opts = []

    try:
        opts, _args = getopt.getopt(argv, "s:i:o:", ["scale=", "src=", "dst="])
    except getopt.GetoptError as e:
        print("Error: " + str(e))

    if len(opts) < 3:
        print('Usage: python svgscale.py -s <scale> -i <src> -o <dst>')
        sys.exit(2)

    for opt, arg in opts:
        if opt in {'-s', '--scale'}:
            scale = arg
        elif opt in {'-i', '--src'}:
            src = os.path.normpath(arg)
        elif opt in {'-o', '--dst'}:
            dst = os.path.normpath(arg)

    if not dst:
        dst = src

    print("scaling svg...")
    print('scale: ' + scale)
    print('src: ' + src)
    print('dst: ' + dst)

    process_file(scale, src, dst)

    print("svgscale done.")


if __name__ == "__main__":
    scale_svg(sys.argv[1:])
