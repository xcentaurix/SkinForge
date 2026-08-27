# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import os
import sys
import getopt
import xml.etree.ElementTree as ET


def merge_files(src1, src2, dst):
    tree1 = ET.parse(src1)
    root1 = tree1.getroot()

    tree2 = ET.parse(src2)
    root2 = tree2.getroot()

    root1.extend(root2)

    tree1.write(dst)


def xmlmerge(argv):
    src1 = ""
    src2 = ""
    dst = ""
    opts = []

    try:
        opts, _args = getopt.getopt(argv, "i:j:o:", ["src1=", "src2=", "dst="])
    except getopt.GetoptError as e:
        print("Error: " + str(e))

    if len(opts) < 3:
        print('Usage: python xmlmerge.py -i <src1> -j <src2> -o <dst>')
        sys.exit(2)

    for opt, arg in opts:
        if opt in {'-i', '--src1'}:
            src1 = os.path.normpath(arg)
        elif opt in {'-j', '--src2'}:
            src2 = os.path.normpath(arg)
        elif opt in {'-o', '--dst'}:
            dst = os.path.normpath(arg)

    print("merging skins...")
    print('src1: ' + src1)
    print('src2: ' + src2)
    print('dst: ' + dst)

    merge_files(src1, src2, dst)

    print("xmlmerge done.")


if __name__ == "__main__":
    xmlmerge(sys.argv[1:])
