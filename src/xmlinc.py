# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import argparse
import math
import os
import re
import sys
from FileUtils import readFile, writeFile
from Pos import Pos


# Base color names defined by the device's own GUI skin (e.g. MetrixHD's
# skin_base.xml) that are available to every plugin skin without being
# declared in screenpart_colors.xmlinc. Kept intentionally small - only
# names actually verified to exist there, so a real typo or a color that
# was never defined anywhere still gets flagged.
KNOWN_BASE_COLORS = {
    "black", "white", "red", "green", "blue", "yellow",
    "grey", "gray", "darkgrey", "darkgray", "orange",
    "transparent", "foreground", "background",
}


class XMLInclude():
    def __init__(self, srcdir, dstdir, cmndir):
        self.srcdir = srcdir
        self.dstdir = dstdir
        self.cmndir = cmndir
        self.sep1 = (
            " ", '"', "{", "[", "(", ",", ";", ":", "=", "}", "]", ")")
        self.sep2 = ("+", "-", "*", "/", "%")
        self.globals = {}
        self.layouts = []
        self.colors = {}
        self.current_screen = "?"
        self.last_font_var = None

    def clean(self, i):
        o = i.replace("\n", " ").replace("\t", " ")
        o = o.replace(" = ", "=")
        o = o.replace("; ", ";")
        o = " ".join(o.split())
        o = o.replace("><", ">Â§<")
        o = o.replace("> <", ">Â§<")
        o = o.split("Â§")
        return o

    def split(self, s, sep):
        o = []
        b = ""
        e = ""

        # print("split: s: %s" % s)
        if s.startswith("</"):
            s = s[2:]
            b = "</"
        elif s.startswith("<"):
            s = s[1:]
            b = "<"
        if s.endswith("/>"):
            s = s[:-2]
            e = "/>"
        elif s.endswith(">"):
            s = s[:-1]
            e = ">"

        pattern = f"({'|'.join(re.escape(c) for c in sep)})"
        r = re.split(pattern, s)
        r = [item for item in r if item != '']

        if b:
            o.append(b)
        o += r
        if e:
            o.append(e)
        # print("split: o: %s" % o)
        return o

    def updatePositions(self, words, pos):
        for i, word in enumerate(words):
            if 0 < i < len(words) - 1 and words[i - 1] != '"' and words[i + 1] == "=":
                if word == "position" and words[i + 2] == '"':
                    pos2 = Pos(words[i + 3], words[i + 5])
                    # print("updatePositions: pos2: (%s,%s)" % (pos2.x, pos2.y))
                    new_pos = pos + pos2
                    # print("updatePositions: new_pos: (%s,%s)" % (new_pos.x, new_pos.y))
                    words[i + 3] = str(new_pos.x)
                    words[i + 5] = str(new_pos.y)
        return words

    def parseColors(self, colors_inc):
        print(f"parseColors: colors_inc: {colors_inc}")
        if os.path.exists(colors_inc):
            ilines = self.clean(readFile(colors_inc))
            for iline in ilines:
                # print("parseColors: iline: %s" % iline)
                iline_words = self.split(iline, self.sep1)
                if iline_words[1] == "color":
                    tags = self.parseTags(iline_words)
                    # print("parseColors: tags: %s" % tags)
                    if "name" in tags and "value" in tags:
                        self.colors["$" + tags["name"]] = tags["value"]
        # print("parseColors: self.colors: %s" % self.colors)

    def evaluateFormulas(self, words):
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

                # Debug: Print what we're evaluating
                # print("DEBUG: evaluating formula: %s" % formula)

                formula = re.sub(r'(?<!/)/(?!/)', '//', formula)
                eval_result = eval(formula)  # pylint: disable=eval-used
                if isinstance(eval_result, float):
                    if eval_result >= 0:
                        result = int(math.floor(eval_result + 0.5))
                    else:
                        result = int(math.ceil(eval_result - 0.5))
                else:
                    result = int(eval_result)

                # print("DEBUG: final result: %s" % result)
                output.append(str(result))
            else:
                output.append(words[i])
                i += 1
        # print("output: %s" % output)
        return output

    def checkFonts(self, tags):
        for tag in tags:
            if tag == "font" and "size" in tags:
                font_parts = tags["font"].split(";")
                if len(font_parts) > 1:
                    font_size = font_parts[1]
                    try:
                        size_height = tags["size"].split(",")[1]
                        if float(size_height) < float(font_size) * 4.0 / 3.0:
                            widget = tags.get("name") or tags.get("source") or "?"
                            fontvar = self.last_font_var or "(literal)"
                            screen_h = self.globals.get("$screen_height", "?")
                            print(f"WARNING: screen={self.current_screen} screen_h={screen_h} widget={widget} font={fontvar} size: {size_height} < font: {float(font_size) * 4.0 / 3.0}")
                    except Exception:
                        pass

    def parseTags(self, words):
        tags = {}
        for i, word in enumerate(words):
            if word == "xmlinc":
                tags[word] = words[words.index("file") + 3]
            elif word in {"screen", "layout", "global"}:
                tags[word] = words[-1]
            elif word == "=":
                if words[i + 1] == '"':
                    # print("words 1: %s" % words)
                    if words[i - 1] in {"size"}:
                        if words[i + 3] == ",":
                            tags[words[i - 1]] = f"{words[i + 2]},{words[i + 4]}"
                        else:
                            tags[words[i - 1]] = f"{words[i + 2]}"
                    elif words[i - 1] in {"font"}:
                        if words[i + 3] == ";":
                            tags[words[i - 1]] = f"{words[i + 2]};{words[i + 4]}"
                    elif words[i - 1] in {"position"}:
                        if words[i + 2] != "fill":
                            tags[words[i - 1]] = f"{words[i + 2]},{words[i + 4]}"
                    elif words[i - 1] in {"value"}:
                        j = i + 2
                        parts = []
                        while words[j] != '"':
                            parts.append(words[j])
                            j += 1
                        tags[words[i - 1]] = "".join(parts)
                    elif words[i - 1].endswith("Color"):
                        if not words[i + 2].startswith("#") and words[i + 2] != "(":
                            color = words[i + 2]
                            if "$" + color not in self.colors and color not in self.colors and color not in KNOWN_BASE_COLORS:
                                print(f"ERROR: color {color} not defined")
                        tags[words[i - 1]] = words[i + 2]
                    else:
                        tags[words[i - 1]] = words[i + 2]
                else:
                    tags[words[i - 1]] = words[i + 1]
        # print("parseTags: words: %s" % words)
        # print("parseTags: tags: %s" % tags)
        return tags

    def parseGlobals(self, tags):
        if "global" in tags:
            self.globals["$" + tags["name"]] = tags["value"]
        elif "screen" in tags:
            # print("parseGlobals: tags: %s" % tags)
            self.current_screen = tags.get("name", "?")
            if "size" in tags:
                size = tags["size"].split(",")
                self.globals["$screen_width"] = size[0]
                self.globals["$screen_height"] = size[1]
        elif tags and "layout" in tags and tags["layout"] == ">":
            # print(">>> adding layout: %s" % tags["name"])
            self.layouts.append(tags["name"])
        elif "xmlinc" in tags:
            for tag in tags:
                # print("parseGlobals: %s - %s -> %s" % (tags["xmlinc"], tag, tags[tag]))
                if tag == "size":
                    size = tags[tag].split(",")
                    self.globals["$width"] = size[0]
                    self.globals["$height"] = size[1]
                else:
                    self.globals["$" + tag] = tags[tag]
        # print("parseTags: tags: %s" % tags)
        # print("parseTags: globals: %s" % self.globals)

    def getIncFilePath(self, inc_filename):
        if not os.path.splitext(inc_filename)[1]:
            inc_filename += ".xmlinc"
        print(f"inc_filename: {inc_filename}")

        inc_file = os.path.join(self.srcdir, inc_filename)
        print(f"inc_file 1: {inc_file}")

        if not os.path.exists(inc_file):
            inc_file = os.path.join(os.path.dirname(self.srcdir), inc_filename)
            print(f"inc_file 2: {inc_file}")

            if not os.path.exists(inc_file):
                inc_file = os.path.join(self.cmndir, inc_filename)
                print(f"inc_file 3: {inc_file}")

                if not os.path.exists(inc_file):
                    inc_file = os.path.join(os.path.dirname(self.cmndir), inc_filename)
                    print(f"inc_file 4: {inc_file}")

                    if not os.path.exists(inc_file):
                        print(f"ERROR: inc file: {inc_file} not found.")

        return inc_file, False

    def resolveVar(self, var):
        if var in self.colors:
            return self.colors[var]
        if var in self.globals:
            value = self.globals[var]
            if var.startswith(("$FR_", "$FB_")):
                self.last_font_var = var
            return value
        try:
            return str(int(var.strip("$")))
        except Exception:
            print(f"ERROR: global {var} not found.")
            return var

    def resolveGlobals(self, words):
        owords = []
        for word in words:
            if "$" in word:
                # $vars aren't always their own token - e.g. "picon$index" has no
                # separator between the literal prefix and the variable, so it
                # survives tokenization as a single word. Substitute every $name
                # occurrence within the word rather than requiring the whole word
                # to be one.
                word = re.sub(r"\$\w+", lambda m: self.resolveVar(m.group(0)), word)
            owords.append(word)
        oline = "".join(owords)
        # print("+++ oline: %s" % oline)
        return oline

    def processApplet(self, level, olines, afile):
        print(f"==> processApplet:  >{level}, {afile})")
        olines.extend(readFile(afile).splitlines())

    def processFile(self, level, olines, afile, pos, do_delete):
        print(f"==> processFile: >{level}, ({pos.x},{pos.y}), {afile}, do_delete: {do_delete}")
        if level == 0 and not os.path.isfile(afile):
            afile, do_delete = self.getIncFilePath(afile)
        if level == 1:
            print("")

        ilines = self.clean(readFile(afile))
        for iline in ilines:
            # print("processFile: iline: %s" % iline)
            self.last_font_var = None
            iline_words = self.split(iline, self.sep1 + self.sep2)
            if "$" in iline:
                iline = self.resolveGlobals(iline_words)
            iline_words = self.split(iline, self.sep1)
            if "eval" in iline_words:
                iline_words = self.evaluateFormulas(iline_words)
            tags = self.parseTags(iline_words)
            if "Summary" not in afile:
                self.checkFonts(tags)
            self.parseGlobals(tags)
            if "layout" in tags:
                # print("tags: %s" % tags)
                if "layout" in tags and tags["layout"] == "/>":
                    # print(">>>> tags: %s, layouts: %s" % (tags["name"], self.layouts))
                    if level == 1:
                        print("")
                    if not tags["name"] in self.layouts:
                        print(f"==> processFile: >{level}, ERROR: layout {tags['name']} not defined")
                    print(f"==> processFile: >{level}, >>> including layout {tags['name']}")
            if "xmlinc" in tags:
                inc_filename = tags["xmlinc"]
                # print("processFile: inc_filename: %s" % inc_filename)
                pos2 = pos
                if "position" in tags:
                    # print("processFile: tags.position: %s" % tags["position"])
                    pos2 = pos + Pos(tags["position"])
                    # print("processFile: pos2: (%s,%s)" % (pos2.x, pos2.y))
                inc_file, next_delete = self.getIncFilePath(inc_filename)
                self.parseColors(inc_file)
                if os.path.basename(inc_file).startswith("applet_"):
                    self.processApplet(level + 1, olines, inc_file)
                else:
                    self.processFile(level + 1, olines,
                                     inc_file, pos2, next_delete)
                # print("-----> processFile: continue with: " + afile)
            elif "global" in tags:
                pass
            else:
                # print("processFile: globals: %s" % self.globals)
                if "position" in iline_words:
                    iline_words = self.updatePositions(iline_words, pos)
                iline = "".join(iline_words)
                olines.append(iline)

        if do_delete:
            os.remove(afile)

        # print("<===== processFile: >%s" + (level, afile))


def parseArgs(argv):
    parser = argparse.ArgumentParser(prog="xmlinc.py")
    parser.add_argument("-i", dest="srcinfile", required=True, help="source file")
    parser.add_argument("-o", dest="srcoutfile", required=True, help="destination file")
    parser.add_argument("-d", dest="dstdir", required=True, help="destination dir")
    parser.add_argument("-c", dest="cmndir", required=True, help="common dir")
    return parser.parse_args(argv)


def xmlinc(argv):
    args = parseArgs(argv)
    srcinfile = os.path.normpath(args.srcinfile)
    srcoutfile = os.path.normpath(args.srcoutfile)
    dstdir = os.path.normpath(args.dstdir)
    cmndir = os.path.normpath(args.cmndir)

    print("processing xml...")
    print("src in file: " + srcinfile)
    srcdir = os.path.dirname(srcinfile)
    srcfn = os.path.basename(srcinfile)
    print("src in file name: " + srcfn)
    print("src out file: " + srcoutfile)
    print("src dir: " + srcdir)
    print("dst dir: " + dstdir)
    print("cmn dir: " + cmndir)

    olines = []
    XMLInclude(srcdir, dstdir, cmndir).processFile(
        0, olines, srcfn, Pos(0, 0), False)
    output = "\n".join(olines) + "\n"
    writeFile(srcoutfile, output)

    print("xmlinc done.")


if __name__ == "__main__":
    xmlinc(sys.argv[1:])
