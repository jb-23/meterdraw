#!/usr/bin/env python3

# ############################################################################ #
#  Copyright (c) 2021, Jason Bamford  www.bamfordresearch.com                  #
#  All rights reserved.                                                        #
#                                                                              #
#  This source code is licensed under the Modified BSD License found           #
#  in the LICENSE.md file in the root directory of this source tree.           #
# ############################################################################ #

# Meterdraw v0.85 ************************************************************ #

import sys
import argparse
import math
import re

from font import getfont

from writepng import encode_png


version = 0.85

u_description = f"""Meterdraw v{version}

Meterdraw creates scale cards for analog meter movements.
"""

u_epilogue = "See README.md for more information."

def main():
    argp = argparse.ArgumentParser(
        description=u_description, epilog=u_epilogue,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    argroup = argp.add_mutually_exclusive_group(required=True)
    argroup.add_argument("-f", dest="source_filename", metavar="designfile", help="file to read design instructions from")
    argroup.add_argument("-x", dest="script", metavar="instructions", help="string to process as design instructions")
    argp.add_argument("out_filename", metavar="outputfile", help="filename for output image (should end .png)")

    args = argp.parse_args()

    if args.script is None:
        try:
            with open(args.source_filename, 'r') as f:
                args.script = f.read()
        except:
            print("Error reading file")
            sys.exit()

    c = Canvas()

    a, success = parse(args.script, c)

    print(a)

    if success:
        try:
            print(f"Saving to {args.out_filename}")
            c.save(args.out_filename)
        except:
            print("Error writing file")
            sys.exit()


def parse(string, plate):
    tokens = tokeniser(string)
    r = parser(tokens, plate.units)
    if type(r) is not tuple:
        c = CommandInterpreter(plate)
        r = c.docommands(r)
    if type(r) is tuple:
        error = f"{r[0]} on line {r[1]} at\n"
        error += " " * r[3] + "\\/\n"
        error += string[r[2]:r[2]+r[3]+r[4]]
        return error, False
    return r, True

def tokeniser(string):
    spec = [
        ("comment", r"#([^\012-\015])*"),
        ("number", r"-?(\d+(\.\d+)?|\.\d+)"),
        ("word", r"[^\01-\040\d\.`]+"),
        ("percent", r"%"),
        ("string", r"`([^`\01-\010\012-\037]|`[a-zA-Z`\.\-~=])*`"),
        ("newline", r"\015\012|[\012-\015]"),
        ("space", r"[\01-\011\016-\040]+"),
        ("other", r"."),
    ]
    rx = "|".join(f"(?P<{s[0]}>{s[1]})" for s in spec)
    tokens = [(m.lastgroup, m.group(), m.start(), m.end()) for m in re.finditer(rx, string)]
    r = []
    line, col, linestart = 1, 0, 0
    for t in tokens:
        type = t[0]
        length = t[3] - t[2]
        if type not in ("space", "newline", "comment"):
            r.append((type, t[1], line, linestart, col, length))
        elif type == "newline":
            line += 1
            col, linestart = 0, t[3]
            continue
        col += length
    return r

def string_escape(string):
    q = ""
    esc = False
    for c in string:
        if esc:
            if c == '`': q += c
            elif c == 'n': q += chr(10)  # newline
            elif c == 'u': q += chr(128) # micro
            elif c == 'R': q += chr(129) # omega
            elif c == '-': q += chr(130) # hyphen
            elif c == '.': q += chr(131) # interpunct
            elif c == '~': q += chr(132) # AC
            elif c == '=': q += chr(133) # DC
            else: q += '`' + c
            esc = False
            continue
        if c == '`':
            esc = True
            continue
        q += c
    return q

def parser(tokens, units):
    def get_arg():
        if not len(tokens): return False, False
        t = tokens[0]
        if t[0] == "number":
            number, unit = float(t[1]), units[0]
            tokens.pop(0)
            if len(tokens):
                u = tokens[0]
                if u[0] in ("word", "percent"):
                    ux = u[1].lower()
                    if ux in units:
                        unit = ux
                        tokens.pop(0)
            return number, unit
        elif t[0] == "string":
            tokens.pop(0)
            return t[1], "string"
        return False, False
    c = []
    while len(tokens):
        # get word
        w = tokens.pop(0)
        if w[0] != "word": return (f"syntax error", w[2], w[3], w[4], w[5])
        word = w[1].lower()
        args = [(word, w[2], w[3], w[4], w[5])]
        while True:
            arg, unit = get_arg()
            if arg is False: break
            args.append((arg, unit))
        c.append(tuple(args))
    return c


class CommandInterpreter():
    def __init__(self, plate):
        self.plate = plate
        self.is_setup = False
        #
        self.command = None
        #
        self.plate_width = False
        self.plate_height = False
        self.plate_resolution = False
        self.plate_box = False
        #
        self.stroke = 0
        self.pivot_x, self.pivot_y = False, False
        self.center_x, self.center_y = False, False
        self.span, self.offset = 0, 0
        self.angles = []
        self.monospace = False
        self.align = "c"
        self.size = 0

    def docommands(self, commands):
        print(" ", end="")
        p = 0
        for i, c in enumerate(commands):
            try:
                self.docommand(c)
                q = int((i+1) * 78 / len(commands))
                if p < q:
                    print("." * (q - p), end="", flush=True)
                    p = q
            except CommandException as e:
                print()
                return e, self.command[0][1], self.command[0][2], self.command[0][3], self.command[0][4]
        print()
        return "success"

    def docommand(self, c):
        self.command = c
        word = c[0][0]

        if word == "card-size":
            if self.is_setup or self.plate_width: self.exception("cannot reset plate size")
            self.countargs(2)
            self.plate_width = c[1]
            self.plate_height = c[2]
            return

        elif word == "resolution":
            if self.is_setup or self.plate_resolution: self.exception("cannot reset plate resolution")
            self.countargs(1)
            self.plate_resolution = c[1]
            return

        elif word == "card-border":
            if self.is_setup or self.plate_box: self.exception("cannot reset plate box")
            self.countargs(1)
            self.plate_box = c[1]
            return

        # set up canvas before executing drawing commands
        if not self.is_setup:
            self.call_setup()
            self.is_setup = True

        if word == "width":
            self.countargs(1)
            self.stroke = self.u(c[1])

        elif word == "color" or word == "colour":
            pass

        elif word == "pivot":
            self.countargs(2)
            self.pivot_x, self.pivot_y = self.u(c[1]), self.u(c[2], vertical=True)
            if self.center_x is False: self.center_x = self.pivot_x
            if self.center_y is False: self.center_y = self.pivot_y

        elif word == "center" or word == "centre":
            self.countargs(2)
            self.center_x, self.center_y = self.u(c[1]), self.u(c[2], vertical=True)

        elif word == "span":
            self.countargs(1)
            self.span = self.o(c[1])

        elif word == "offset":
            self.countargs(1)
            self.offset = self.o(c[1])

        elif word == "line":
            self.countargs(4)
            self.plate.line(self.u(c[1]), self.u(c[2], vertical=True),
                self.u(c[3]), self.u(c[4], vertical=True),
                self.stroke)

        elif word == "arc":
            self.countargs(1,2,3,5)
            radius = self.u(c[1])
            span = self.o(c[2]) if len(c) > 2 else self.span
            offset = self.o(c[3]) if len(c) > 3 else self.offset
            self.plate.arc(self.center_x, self.center_y, radius, span, offset,
                self.stroke, ends=0)

        elif word == "monospaced" or word == "monospace": self.monospace = True
        elif word == "proportional": self.monospace = False
        elif word == "align-left": self.align = "l"
        elif word == "align-center" or word == "align-centre": self.align = "c"
        elif word == "align-right": self.align = "r"

        elif word == "size":
            self.countargs(1)
            self.size = self.u(c[1], vertical=True)

        elif word == "text":
            self.minimumargs(3)
            x = self.u(c[1])
            y = self.u(c[2], vertical=True)
            rotation = 0
            text = ""
            for i in range(3, len(c)):
                text += self.s(c[i])
            self.plate.plotstring(text, x, y, size=self.size, rotate=rotation,
                mono=self.monospace, align=self.align)

        elif word == "mark":
            self.minimumargs(2)
            inner = self.u(c[1])
            outer = self.u(c[2])
            set_angles = False
            for i in range(3, len(c)):
                if not set_angles:
                    self.angles = []
                    set_angles = True
                self.angles.append(self.o(c[i]))
            if not self.angles: self.exception("no angles given for marks")
            px = self.pivot_x if self.pivot_x is not False else self.center_x
            py = self.pivot_y if self.pivot_y is not False else self.center_y
            self.plate.manualticks(px, py, self.center_x, self.center_y,
                inner, outer, self.span, self.offset,
                self.angles, self.stroke)

        elif word == "label":
            self.minimumargs(2)
            radius = self.u(c[1])
            set_angles = False
            labels = []
            for i in range(2, len(c)):
                if c[i][1] == "string":
                    labels.append(self.s(c[i]))
                else:
                    if not set_angles:
                        self.angles = []
                        set_angles = True
                    self.angles.append(self.o(c[i]))
            if not labels: self.exception("label requires text string(s)")
            if not self.angles: self.exception("no angles given for labels")
            px = self.pivot_x if self.pivot_x is not False else self.center_x
            py = self.pivot_y if self.pivot_y is not False else self.center_y
            self.plate.manualcal(px, py, self.center_x, self.center_y,
                radius, self.span, self.offset,
                self.angles, labels, self.size)

        else:
            self.exception(f"unknown command {word}")

    def call_setup(self):
        r = self.plate_resolution[0] if self.plate_resolution else 300
        ru = self.plate_resolution[1] if self.plate_resolution else "dpi"
        w = self.plate_width[0] if self.plate_width else 10
        wu = self.plate_width[1] if self.plate_width else "cm"
        h = self.plate_height[0] if self.plate_height else 5
        hu = self.plate_height[1] if self.plate_height else "cm"
        b = self.plate_box[0] if self.plate_box else 0
        bu = self.plate_box[1] if self.plate_box else "pt"
        self.plate.setup(resolution=r, resolution_units=ru,
            width=w, width_units=wu, height=h, height_units=hu,
            box=b, box_units=bu)
        self.stroke = self.plate.topixels(1, "pt")
        self.size = self.plate.topixels(12, "pt")

    def countargs(self, *argc):
        if len(self.command) - 1 not in argc:
            raise CommandException(f"wrong number of arguments")

    def minimumargs(self, argc):
        if len(self.command) - 1 < argc:
            raise CommandException(f"too few arguments")

    def exception(self, msg):
        raise CommandException(msg)

    def s(self, c): # string
        if c[1] == "string":
            return string_escape(c[0][1:-1])
        return str(c[0])

    def o(self, c): # units for angles
        if type(c[0]) is float or type(c[0]) is int:
            return c[0]
        raise CommandException(f"argument should not be a string")

    def u(self, c, vertical=False): # unit conversion **************************
        try:
            return self.plate.topixels(c[0], c[1], vertical)
        except:
            raise CommandException(f"argument error")


class Canvas():
    def __init__(self):
        self.resolution = 1
        self.feather = 1.5
        self.planes = False

    def setup(self, resolution=300, resolution_units="dpi",
            width=10, width_units="cm", height=5, height_units="cm",
            box=0, box_units="pt"):
        bleed = 1
        bleed_units = "in"
        self.resolution = self.topixels(resolution, resolution_units)
        self.bleed_box = self.topixels(box, box_units)
        self.bleed_size = int(self.topixels(bleed, bleed_units) + 0.5)
        self.width = int(self.topixels(width, width_units) + 0.5)
        self.height = int(self.topixels(height, height_units) + 0.5)
        self.max_x = self.width + self.bleed_size
        self.max_y = self.height + self.bleed_size
        w, h = self.width + self.bleed_size * 2, self.height + self.bleed_size * 2
        self.actual_width = w
        size = w * h
        self.setup_planes(size, (255,255,255))
        #
        self.stroke = 10
        #
        self.setup_bleed()

    def setup_planes(self, size, x):
        self.planes = (bytearray(size), bytearray(size), bytearray(size))
        for i in range(0, len(self.planes[0])):
            self.planes[0][i], self.planes[1][i], self.planes[2][i] = x

    units =     ("mm", "cm", "in", "inch", "pt",  "pc",  "dpi", "dpcm",   "%")
    unit_values = (1.0, 10,  25.4,  25.4,  0.352778, 4.23333, 1/25.4, 1/10, 1.0)

    def save(self, filename):
        if not self.planes: return
        card = self.finalise()
        encode_png(filename, self.planes, self.actual_width,
            card, dpi=self.resolution*25.4)

    def setup_bleed(self):
        gap = self.topixels(3, "mm")
        w = self.topixels(1, "pt")
        x = self.topixels(12, "pt")
        self.line(-self.bleed_size, 0, 0 - gap, 0, w)
        self.line(self.width + gap, 0, self.max_x, 0, w)
        self.line(-self.bleed_size, self.height, 0 - gap, self.height, w)
        self.line(self.width + gap, self.height, self.max_x, self.height, w)
        self.line(0, -self.bleed_size, 0, 0 - gap, w)
        self.line(self.width, -self.bleed_size, self.width, 0 - gap, w)
        self.line(0, self.height + gap, 0, self.max_y-x, w)
        self.line(self.width, self.height + gap, self.width, self.max_y-x, w)
        if self.bleed_box:
            ww = self.bleed_box
            self.line(-ww,-ww/2-self.feather, self.width+ww, -ww/2-self.feather, ww)
            self.line(-ww,self.height+ww/2+self.feather, self.width+ww, self.height+ww/2+self.feather, ww)
            self.line(-ww/2-self.feather, -ww, -ww/2-self.feather, self.height+ww, ww)
            self.line(self.width+ww/2+self.feather, -ww, self.width+ww/2+self.feather, self.height+ww, ww)

    def finalise(self):
        ms = self.topixels(5.5, "pt")
        mm = "\103\162\145\141\164\145\144\040\167\151\164\150\040"
        mm += "\115\145\164\145\162\144\162\141\167\040"
        mm += "\166\060\056\070\065\040"
        mm += "\167"*3 + "\056\142\141\155\146\157\162\144\162\145\163\145\141"
        mm += "\162\143\150\056\143\157\155"
        m = mm
        if self.actual_width < ms * 46: m = m[-39:]
        if self.actual_width < ms * 34: m = m[-23:]
        self.plotstring(m, self.width*3/6, self.max_y-ms/2, size=ms, align="c")
        return mm

    def topixels(self, x, units, vertical=False):
        if units not in self.units:
            raise CommandException(f"Unit {units} not found.")
        if units == "%":
            if vertical: return x * self.height / 100
            return x * self.width / 100
        i = self.units.index(units)
        return x * self.unit_values[i] * self.resolution

    def plotstring(self, string, x, y, size=25, rotate=0.0, mono=False, weight=1.0, width=1.0, align="l"):
        rr = rotate * math.pi / 180
        font = getfont(mono, weight, width)
        s = 0.07 / 2
        sep = 0.15
        letters, width = self.plottext(string, s, sep, size, rotate, font)
        if align=="c":
            x -= math.cos(rr) * width / 2
            y -= math.sin(rr) * width / 2
        if align=="r":
            x -= math.cos(rr) * width
            y -= math.sin(rr) * width
        for l in letters:
            self.plottx(l[0], x+l[1], y+l[2], l[3], l[4]*180/math.pi, flip=True, default_end=0, default_mode=1)

    @staticmethod
    def plottext(string, stroke, sep, size, rotate, font):
        font, offs4 = font
        rr = rotate * math.pi / 180
        r = []
        xc1, xc2, xc3 = 0, 0, 0  # x cursors
        for c in string:
            # get character design for glyph
            data = font[(ord(c) - 32) % len(font)]
            letterform = data[1:]
            # move x position, including width of new glyph
            if xc1 or xc2 or xc3: xc1, xc2, xc3 = xc1 + sep, xc2 + sep, xc3 + sep
            if type(data[0]) is tuple:
                ca1, ca2, ca3, cb1, cb2, cb3 = data[0]
                ca1 += stroke
                ca2 += stroke
                ca3 += stroke
                cb1 += stroke
                cb2 += stroke
                cb3 += stroke
            else:
                ca1, ca2, ca3 = data[0]/2, data[0]/2, data[0]/2
                cb1, cb2, cb3 = data[0]/2, data[0]/2, data[0]/2
            xc1, xc2, xc3 = xc1 + ca1, xc2 + ca2, xc3 + ca3
            x_cursor = max(xc1, xc2, xc3)
            xc1, xc2, xc3 = x_cursor + cb1, x_cursor + cb2, x_cursor + cb3
            # x cursor is in glyph-sized coordinates
            o = 0 if c != '4' else offs4
            xx, yy = Canvas.translate(x_cursor+o, 0, 0, 0, size, rr)
            # add character to return array
            r.append((letterform, xx, yy, size, rr))
        return r, max(xc1, xc2, xc3) * size

    def plottx(self, xlist, tx, ty, scale, rotate, flip=False, default_end=False, default_mode=False):
        # each member of x should be
        # line (1, x, y, x, y, width)
        # arc  (0, x, y, radius, span, offset, width)
        #print(f"Translate {tx} {ty} {scale}")
        rr = rotate * math.pi / 180
        for m in xlist:
            if m[0] == 0: # arc
                x, y = self.translate(m[1], m[2], tx, ty, scale, rr, flip)
                rot = m[5]
                if flip:
                    rot = 90 + (90 - rot)
                    if rot > 180: rot -= 360
                self.arc(x, y, m[3] * scale, m[4], rot + rotate, m[6] * scale, default_end, default_mode)
                continue
            if m[0] == 1: # line
                x, y = self.translate(m[1], m[2], tx, ty, scale, rr, flip)
                xx, yy = self.translate(m[3], m[4], tx, ty, scale, rr, flip)
                ends = m[6] if len(m) > 6 else default_end
                self.line(x, y, xx, yy, m[5] * scale, ends, default_mode)
                pass

    @staticmethod
    def translate(x, y, tx, ty, scale, rotate, flip=False):
        if flip:
            y = -y
        r, p = Canvas.topolar(x, y)
        r *= scale
        p += rotate
        xx, yy = Canvas.tocarte(r, p)
        xx += tx
        yy += ty
        return xx, yy

    @staticmethod
    def topolar(x, y):
        r = math.sqrt(x ** 2 + y ** 2)
        p = math.atan(x / -y) if y else ((math.pi / 2) if x > 0 else (-math.pi / 2))
        if y > 0: p += math.pi
        if p > math.pi: p -= math.pi * 2
        return r, p

    @staticmethod
    def tocarte(r, p):
        x = r * math.sin(p)
        y = -r * math.cos(p)
        return x, y

    def manualticks(self, cx, cy, rx, ry, inner, outer, span, offset, percents, w):
        angles = self.percentangles(span, percents)
        inners = self.genlinearticks(cx, cy, rx, ry, inner, angles, offset)
        outers = self.genlinearticks(cx, cy, rx, ry, outer, angles, offset)
        if inners is False or outers is False:
            raise CommandException("arc radius less than distance between pivot and arc center")
        for i in range(0, len(inners)):
            self.line(inners[i][0], inners[i][1], outers[i][0], outers[i][1], w)

    def manualcal(self, cx, cy, rx, ry, radius, span, offset, percents, labels, size):
        angles = self.percentangles(span, percents)
        inners = self.genlinearticks(cx, cy, rx, ry, radius, angles, offset)
        if inners is False:
            raise CommandException("arc radius less than distance between pivot and arc center")
        for i in range(0, len(inners)):
            if i >= len(labels): break
            ii = inners[i]
            dx = ii[0] - rx
            dy = ry - ii[1]
            angle = math.atan(dx / dy) if dy else ((math.pi / 2) if dx > 0 else (-math.pi / 2))
            if dy < 0: angle += math.pi
            angle = angle * 180 / math.pi
            self.plotstring(labels[i], ii[0], ii[1], size=size, rotate=angle, align="c")

    @staticmethod
    def genlinearticks(cx, cy, rx, ry, radius, angles, offset):
        dpivots = math.sqrt((rx - cx) ** 2 + (ry - cy) ** 2)
        if radius < dpivots:
            return False
        offset = offset * math.pi / 180
        r = []
        for aa in angles:
            a = aa + offset
            if dpivots < 1:
                ii = radius
            else:
                ii = Canvas.math_thing(a, cx, cy, rx, ry, radius)
            ax = cx + math.sin(a) * ii
            ay = cy - math.cos(a) * ii
            r.append((ax, ay, a))
        return r

    @staticmethod
    def math_thing(top_angle, cx, cy, rx, ry, b_radius):
        dx = rx - cx
        dy = ry - cy
        a = math.sqrt(dx ** 2 + dy ** 2)
        # angle of arc center from pointer center point
        pivot2angle = math.atan(dx / dy) if dy else ((math.pi / 2) if dx > 0 else (-math.pi / 2))
        if dy < 0: pivot2angle += math.pi
        beta = math.pi + top_angle + pivot2angle
        if beta > math.pi: beta -= math.pi * 2
        if math.isclose(beta, math.pi) or math.isclose(beta, -math.pi):
            return b_radius - a
        if math.isclose(beta, 0):
            return b_radius + a
        alpha = math.asin(math.sin(beta) / b_radius * a)
        gamma = math.pi - beta - alpha
        c = b_radius / math.sin(beta) * math.sin(gamma)
        if c > 10000: c = 10
        return c

    @staticmethod
    def percentangles(span, percents):
        span = span * math.pi / 180
        halfspan = span / 2
        r = []
        for p in percents:
            r.append(span * p / 100 - halfspan)
        return r

    def arc(self, cx, cy, radius, span, offset, width, ends=False, mode=False):
        length, blockfn, plotfn = self.arc_functions(cx, cy, radius, span, offset)
        self.blockandplot(width, length, ends, mode, blockfn, plotfn)

    def arc_functions(self, x, y, radius, span, offset):
        span = span * math.pi / 180
        offset = offset * math.pi / 180
        circ = 2 * math.pi * radius
        length = circ * span / (2 * math.pi)
        start = offset - span / 2
        revpoint1 = offset - math.pi
        revpoint2 = offset + math.pi
        def blockfn(h):
            nonlocal start, span, length, x, y, radius
            a = start + span * h / length
            return x + radius * math.sin(a), y - radius * math.cos(a)
        def plotfn(px, py):
            nonlocal x, y
            dx = px - x
            dy = y - py
            h = math.sqrt((dx) ** 2 + (dy) ** 2)
            across = h - radius
            ang = math.atan(dx / dy) if dy else ((math.pi / 2) if dx > 0 else (-math.pi / 2))
            if dy < 0: ang += math.pi
            if ang < revpoint1: ang += math.pi * 2
            if ang > revpoint2: ang -= math.pi * 2
            along = (ang - start) * circ / (2 * math.pi)
            return along, across
        return length, blockfn, plotfn

    def line(self, x, y, xx, yy, width, ends=False, mode=False):
        length, blockfn, plotfn = self.line_functions(x, y, xx, yy)
        self.blockandplot(width, length, ends, mode, blockfn, plotfn)

    def line_functions(self, x, y, xx, yy):
        dx, dy = xx - x, yy - y
        xrr, yrr = x - dy, y + dx
        length = math.sqrt(dx ** 2 + dy ** 2)
        def blockfn(h):
            nonlocal x, y, dx, dy, length
            if not length: return 0, 0
            return x + dx * h / length, y + dy * h / length
        def plotfn(px, py):
            nonlocal x, y, xx, yy, xrr, yrr, length
            across = abs((x * yy) + (xx * py) + (px * y) - (xx * y) - (px * yy) - (x * py)) / length
            along = -((x * yrr) + (xrr * py) + (px * y) - (xrr * y) - (px * yrr) - (x * py)) / length
            return along, across
        return length, blockfn, plotfn

    def blockandplot(self, width, length, ends, mode, blockfn, plotfn):
        if not length: return
        if ends is False: ends = 1
        pixels = self.blockshape(width, length, blockfn)
        self.plotshape(width, length, ends, mode, pixels, plotfn)

    def blockshape(self, width, length, function):
        box = int(width/2 + 1) + 2  # size of pixel block
        box2 = int(box * 0.7)
        steps = int(length / box2) + 1
        pixels = set()
        for i in range(-1, steps+1):
            px, py = function(i * box2)
            for by in range (-box, box+1):
                for bx in range(-box, box+1):
                    t = (int(px) + bx, int(py) + by)
                    if t[0] < -self.bleed_size or t[1] < -self.bleed_size: continue
                    if t[0] >= self.max_x or t[1] >= self.max_y: continue
                    pixels.add( t )   # set.add() automatically ignores duplicates
        return pixels

    # ends 0 = round beyond end, 1 = round to end, 2 = square
    def plotshape(self, width, length, ends, mode, pixels, function):
        width = (width - self.feather) / 2
        halflength = length / 2
        if ends == 0: endstart = 0
        if ends == 1: endstart = width
        if ends == 2: endstart = 0
        for p in pixels:
            along, across = function(p[0], p[1])
            if along > halflength: along = halflength - (along - halflength)
            cw = width
            if along >= endstart:
                h = abs(across)
            else:
                if ends < 2:
                    h = math.sqrt(across ** 2 + (along - endstart) ** 2)
                else:
                    w = abs(across) - width
                    if w < 0: w = 0
                    h = abs(along - endstart) + w
                    cw = 0
            c = (self.feather - (h - cw)) / self.feather
            if c < 0.0: c = 0
            if c > 1.0: c = 1.0
            v = 255 - int(255 * c)
            if c > 0.0:
                self.putpixel(p[0], p[1], (v, v, v), mode)
            #else:
            #    self.putpixel(p[0], p[1], (0, 0, 255))

    def putpixel(self, cx, y, value, mode=False):
        cx += self.bleed_size
        y += self.bleed_size
        if mode is False: mode = 0
        try:
            i = y * self.actual_width + cx
            xx = self.planes[0][i], self.planes[1][i], self.planes[2][i]
            x = [0,0,0]
            if mode == 0:
                x[0] = int(xx[0] * value[0] / 255)
                x[1] = int(xx[1] * value[1] / 255)
                x[2] = int(xx[2] * value[2] / 255)
            else:
                x[0] = min(xx[0], value[0])
                x[1] = min(xx[1], value[1])
                x[2] = min(xx[2], value[2])
            if x[0] < 0: x[0] = 0
            if x[1] < 0: x[1] = 0
            if x[2] < 0: x[2] = 0
            self.planes[0][i], self.planes[1][i], self.planes[2][i] = x
        except:
            pass


class CommandException(Exception):
    pass


if __name__ == "__main__":
    main()