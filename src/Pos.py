# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0s


def toInt(s):
    try:
        i = int(s)
    except Exception:
        i = s
    return i


def addMix(v1, v2):
    v1 = toInt(v1)
    v2 = toInt(v2)
    if isinstance(v1, str):
        r = v1
    elif isinstance(v2, str):
        r = v2
    else:
        r = v1 + v2
    return r


class Pos():
    def __init__(self, x, y=0):
        if isinstance(x, str):
            # print("Pos: __init__: x: %s" % x)
            if "," in x:
                pos_string = x.split(",")
                x = pos_string[0]
                y = pos_string[1]
        self.x = toInt(x)
        self.y = toInt(y)

    def __add__(self, other):
        new_x = addMix(self.x, other.x)
        new_y = addMix(self.y, other.y)
        return Pos(new_x, new_y)
