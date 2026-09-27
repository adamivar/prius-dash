"""A Kivy widget that understands the tkinter Canvas calls scene.py and shapes.py use, so the same drawing code
runs on Android.

Items live in fixed layers, bottom to top: base, spin (rotors), label (part text), anim (wire arrows), tip (the
info card). That's the order the tkinter app ends up with after its tag_raise calls, so tag_raise is a no-op here.
Coordinates come in tkinter style (y down, from the top) and are flipped for Kivy.
"""
import math

from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Ellipse, InstructionGroup, Line, Mesh, Rectangle
from kivy.graphics.tesselator import TYPE_POLYGONS, WINDING_ODD, Tesselator
from kivy.metrics import sp
from kivy.uix.widget import Widget

LAYERS = ("base", "spin", "label", "anim", "tip")
FONT = "data/fonts/DejaVuSans.ttf"   # ships with Kivy; has the ° Ω µ − ▲ symbols the views use
_TEXTURES = {}


def rgba(colour, alpha=1.0):
    if not colour:
        return None
    return (int(colour[1:3], 16) / 255, int(colour[3:5], 16) / 255, int(colour[5:7], 16) / 255, alpha)


WIDTH_MATCH = 0.92   # DejaVu Sans runs ~8% wider than Segoe UI, which the layouts (and tools/check_layout.py) use


def font_px(font):
    """tkinter font tuple -> (pixel size, bold). Negative sizes are pixels, positive ones points."""
    size = font[1] if len(font) > 1 else 10
    bold = "bold" in font[2:]
    return (-size * WIDTH_MATCH if size < 0 else sp(size * 1.25)), bold


def _dashes(pts, on, off):
    """Split a polyline into dash segments."""
    out, draw, left = [], True, on
    cur = [pts[0]]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        seg = math.dist((ax, ay), (bx, by))
        pos = 0.0
        while seg - pos > 1e-6:
            step = min(left, seg - pos)
            pos += step
            t = pos / seg
            p = (ax + (bx - ax) * t, ay + (by - ay) * t)
            if draw:
                cur.append(p)
            left -= step
            if left <= 1e-6:
                if draw and len(cur) > 1:
                    out.append(cur)
                draw = not draw
                left = on if draw else off
                cur = [p]
    if draw and len(cur) > 1:
        out.append(cur)
    return out


def _text_texture(text, px, bold, colour, width, justify):
    key = (text, px, bold, colour, width, justify)
    tex = _TEXTURES.get(key)
    if tex is None:
        if len(_TEXTURES) > 1500:
            _TEXTURES.clear()
        lbl = CoreLabel(text=text, font_size=px, bold=bold, font_name=FONT, color=rgba(colour) or (1, 1, 1, 1),
                        text_size=(width, None) if width else (None, None), halign=justify or "left", valign="top")
        lbl.refresh()
        tex = _TEXTURES[key] = lbl.texture
    return tex


class KivyCanvas(Widget):
    def __init__(self, on_tap=None, **kw):
        super().__init__(**kw)
        self.on_tap = on_tap
        self.items = {}
        self.order = {layer: [] for layer in LAYERS}
        self.next_id = 1
        self.groups = {layer: InstructionGroup() for layer in LAYERS}
        self.dirty = set(LAYERS)
        for layer in LAYERS:
            self.canvas.add(self.groups[layer])
        self._trigger = Clock.create_trigger(self._render, -1)
        self.bind(pos=self._all_dirty, size=self._all_dirty)

    # ---------- tkinter-style API ----------
    def winfo_width(self):
        return int(self.width)

    def winfo_height(self):
        return int(self.height)

    def _add(self, kind, coords, opts):
        tags = opts.pop("tags", ())
        tags = {tags} if isinstance(tags, str) else set(tags)
        layer = next((t for t in ("tip", "anim", "spin", "label") if t in tags), "base")
        iid = self.next_id
        self.next_id += 1
        self.items[iid] = dict(kind=kind, coords=list(coords), opts=opts, tags=tags, layer=layer)
        self.order[layer].append(iid)
        self.dirty.add(layer)
        self._trigger()
        return iid

    @staticmethod
    def _flat(coords):
        if len(coords) == 1 and isinstance(coords[0], (list, tuple)):
            coords = coords[0]
        return [float(v) for v in coords]

    def create_line(self, *coords, **opts):
        return self._add("line", self._flat(coords), opts)

    def create_polygon(self, *coords, **opts):
        return self._add("polygon", self._flat(coords), opts)

    def create_rectangle(self, *coords, **opts):
        return self._add("rectangle", self._flat(coords), opts)

    def create_oval(self, *coords, **opts):
        return self._add("oval", self._flat(coords), opts)

    def create_text(self, x, y, **opts):
        iid = self._add("text", [x, y], opts)
        item = self.items[iid]
        px, bold = font_px(opts.get("font", ("", 10)))
        width = opts.get("width")
        item["tex"] = _text_texture(opts.get("text", ""), px, bold, opts.get("fill", "#ffffff"), width,
                                    opts.get("justify"))
        return iid

    def delete(self, tag):
        if tag == "all":
            self.items.clear()
            for layer in LAYERS:
                self.order[layer] = []
            self.dirty.update(LAYERS)
        else:
            gone = {i for i, it in self.items.items() if tag in it["tags"]}
            for i in gone:
                layer = self.items.pop(i)["layer"]
                self.order[layer].remove(i)
                self.dirty.add(layer)
        self._trigger()

    def tag_raise(self, *_):
        pass

    def tag_lower(self, item, below):
        it = self.items[item]
        order = self.order[it["layer"]]
        order.remove(item)
        order.insert(order.index(below) if below in order else 0, item)
        self.dirty.add(it["layer"])

    def _box(self, it):
        if it["kind"] == "text":
            x, y = it["coords"]
            w, h = it["tex"].size
            anchor = it["opts"].get("anchor", "center")
            anchor = "" if anchor == "center" else anchor     # compass letters only (n, se, w, ...)
            x0 = x if "w" in anchor else (x - w if "e" in anchor else x - w / 2)
            y0 = y if anchor.startswith("n") else (y - h if anchor.startswith("s") else y - h / 2)
            return x0, y0, x0 + w, y0 + h
        xs, ys = it["coords"][0::2], it["coords"][1::2]
        return min(xs), min(ys), max(xs), max(ys)

    def bbox(self, *ids):
        boxes = [self._box(self.items[i]) for i in ids if i in self.items]
        if not boxes:
            return None
        return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))

    def move(self, item, dx, dy):
        it = self.items[item]
        it["coords"] = [v + (dx if k % 2 == 0 else dy) for k, v in enumerate(it["coords"])]
        self.dirty.add(it["layer"])
        self._trigger()

    # ---------- rendering ----------
    def _all_dirty(self, *_):
        self.dirty.update(LAYERS)
        self._trigger()

    def _xy(self, pts):
        """tkinter (x, y-down) pairs -> Kivy flat list."""
        top = self.y + self.height
        out = []
        for i in range(0, len(pts) - 1, 2):
            out += [self.x + pts[i], top - pts[i + 1]]
        return out

    def _render(self, *_):
        for layer in LAYERS:
            if layer not in self.dirty:
                continue
            g = self.groups[layer]
            g.clear()
            for iid in self.order[layer]:
                self._draw(g, self.items[iid])
        self.dirty.clear()

    def _stroke(self, g, pts, colour, width, dash, close=False, cap="round"):
        if not colour or len(pts) < 4:
            return
        g.add(Color(*rgba(colour)))
        w = max(1.0, float(width or 1)) / 2 if float(width or 1) > 1 else 1.0
        if dash:
            pairs = [(pts[i], pts[i + 1]) for i in range(0, len(pts) - 1, 2)]
            if close:
                pairs.append(pairs[0])
            for seg in _dashes(pairs, *dash[:2]):
                g.add(Line(points=self._xy([v for p in seg for v in p]), width=w))
        else:
            g.add(Line(points=self._xy(pts), width=w, close=close, cap=cap, joint="round"))

    def _fill(self, g, pts, colour):
        if not colour or len(pts) < 6:
            return
        g.add(Color(*rgba(colour)))
        flat = self._xy(pts)
        if len(flat) <= 8:   # triangles / quads (arrows, bars): a simple fan
            verts = []
            for i in range(0, len(flat), 2):
                verts += [flat[i], flat[i + 1], 0, 0]
            g.add(Mesh(vertices=verts, indices=list(range(len(flat) // 2)), mode="triangle_fan"))
            return
        tess = Tesselator()
        tess.add_contour(flat)
        if tess.tesselate(WINDING_ODD, TYPE_POLYGONS):
            for vertices, indices in tess.meshes:
                g.add(Mesh(vertices=vertices, indices=indices, mode="triangle_fan"))

    def _draw(self, g, it):
        kind, c, o = it["kind"], it["coords"], it["opts"]
        if kind == "line":
            self._stroke(g, c, o.get("fill", "#000000"), o.get("width", 1), o.get("dash"),
                         cap="round" if o.get("capstyle") == "round" else "square")
        elif kind == "polygon":
            self._fill(g, c, o.get("fill", "#000000"))
            self._stroke(g, c, o.get("outline", ""), o.get("width", 1), o.get("dash"), close=True)
        elif kind == "rectangle":
            x0, y0, x1, y1 = min(c[0], c[2]), min(c[1], c[3]), max(c[0], c[2]), max(c[1], c[3])
            if o.get("fill"):
                g.add(Color(*rgba(o["fill"])))
                g.add(Rectangle(pos=(self.x + x0, self.y + self.height - y1), size=(x1 - x0, y1 - y0)))
            self._stroke(g, [x0, y0, x1, y0, x1, y1, x0, y1], o.get("outline", "#000000"), o.get("width", 1),
                         o.get("dash"), close=True, cap="square")
        elif kind == "oval":
            x0, y0, x1, y1 = min(c[0], c[2]), min(c[1], c[3]), max(c[0], c[2]), max(c[1], c[3])
            pos, size = (self.x + x0, self.y + self.height - y1), (x1 - x0, y1 - y0)
            if o.get("fill"):
                g.add(Color(*rgba(o["fill"])))
                g.add(Ellipse(pos=pos, size=size))
            if o.get("outline", "#000000"):
                w = float(o.get("width", 1))
                g.add(Color(*rgba(o.get("outline", "#000000"))))
                g.add(Line(ellipse=(*pos, *size), width=w / 2 if w > 1 else 1.0))
        elif kind == "text":
            x0, y0, x1, y1 = self._box(it)
            g.add(Color(1, 1, 1, 1))
            g.add(Rectangle(texture=it["tex"], pos=(self.x + x0, self.y + self.height - y1), size=it["tex"].size))

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and self.on_tap:
            self.on_tap(touch.x - self.x, self.y + self.height - touch.y)
            return True
        return super().on_touch_down(touch)
