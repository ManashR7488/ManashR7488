#!/usr/bin/env python3
"""Build the five animated profile SVGs in ../assets from the vendored sources.

    python3 tools/build.py

Needs Python 3.10+, Pillow, fonttools and brotli (pyoxipng is optional and only
makes the embedded PNGs smaller). Every SVG it writes is self-contained: fonts
and photos are inlined as data: URIs, there is no JavaScript, no foreignObject
and nothing that triggers a network request.
"""
from __future__ import annotations

import base64
import html
import io
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from fontTools import subset as ftsubset
from fontTools.ttLib import TTFont
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
VENDOR = TOOLS / "vendor"
ASSETS = ROOT / "assets"

# ---------------------------------------------------------------- palette
NAVY = "#070b16"
SURF = "#0d1528"
SURF2 = "#121d36"
LINE = "#243152"
BLUE = "#247bff"
CRIMSON = "#ff354f"
INK = "#eef2fb"
MUTED = "#a9b4cc"
DIM = "#7684a3"

SNAP = json.loads((TOOLS / "data" / "github-snapshot.json").read_text())
ICONS = json.loads((VENDOR / "simple-icons.json").read_text())["icons"]
AS_OF = datetime.strptime(SNAP["retrieved"], "%Y-%m-%d").strftime("%d %b %Y")

# ---------------------------------------------------------------- fonts
FONT_FILES = {
    "d4": ("MR Bricolage", 400, "bricolage-grotesque-latin-400-normal.woff2"),
    "d5": ("MR Bricolage", 500, "bricolage-grotesque-latin-500-normal.woff2"),
    "d6": ("MR Bricolage", 600, "bricolage-grotesque-latin-600-normal.woff2"),
    "d8": ("MR Bricolage", 800, "bricolage-grotesque-latin-800-normal.woff2"),
    "m5": ("MR JetBrains", 500, "jetbrains-mono-latin-500-normal.woff2"),
    "m7": ("MR JetBrains", 700, "jetbrains-mono-latin-700-normal.woff2"),
}
LICENSE_TEXT = {
    "MR Bricolage": (ASSETS / "licenses" / "OFL-BricolageGrotesque.txt").read_text(),
    "MR JetBrains": (ASSETS / "licenses" / "OFL-JetBrainsMono.txt").read_text(),
}
REAL_NAME = {"MR Bricolage": "Bricolage Grotesque", "MR JetBrains": "JetBrains Mono"}


class Metrics:
    def __init__(self, path: Path):
        f = TTFont(path)
        self.cmap = f.getBestCmap()
        self.adv = f["hmtx"].metrics
        self.upm = f["head"].unitsPerEm

    def width(self, s: str, size: float, ls: float = 0.0) -> float:
        total = 0
        for ch in s:
            g = self.cmap.get(ord(ch))
            if g is None:
                raise SystemExit(f"font has no glyph for {ch!r} in {s!r}")
            total += self.adv[g][0]
        return total * size / self.upm + ls * len(s)


METRICS = {k: Metrics(VENDOR / "fonts" / v[2]) for k, v in FONT_FILES.items()}


def tw(s: str, font: str, size: float, ls: float = 0.0) -> float:
    return METRICS[font].width(s, size, ls)


def subset_woff2(path: Path, chars: set[str]) -> bytes:
    text = "".join(sorted(chars | {" "}))
    f = TTFont(path)
    cmap = f.getBestCmap()
    missing = [c for c in text if ord(c) not in cmap]
    if missing:
        raise SystemExit(f"{path.name} is missing glyphs {missing}")
    opts = ftsubset.Options()
    opts.flavor = "woff2"
    opts.name_IDs = ["*"]  # keep copyright + licence records (OFL requirement)
    opts.name_languages = ["*"]
    opts.name_legacy = True
    opts.notdef_outline = True
    opts.hinting = False
    opts.layout_features = ["kern", "liga", "ccmp", "locl", "mark", "mkmk"]
    sub = ftsubset.Subsetter(opts)
    sub.populate(text=text)
    sub.subset(f)
    f.flavor = "woff2"
    buf = io.BytesIO()
    f.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- helpers
def fmt(n: float) -> str:
    if isinstance(n, int):
        return str(n)
    s = f"{n:.2f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def png_uri(im: Image.Image) -> str:
    buf = io.BytesIO()
    im.save(buf, "PNG")
    data = buf.getvalue()
    try:
        import oxipng  # type: ignore

        data = oxipng.optimize_from_memory(data, level=4)
    except ImportError:
        pass
    return "data:image/png;base64," + b64(data)


def load_rgba(name: str) -> Image.Image:
    im = Image.open(TOOLS / "src" / name)
    im.load()
    return im.convert("RGBA")


def resize_rgba(im: Image.Image, w: int) -> Image.Image:
    h = round(im.height * w / im.width)
    # resample in premultiplied space so the cut-out edges keep their real alpha
    return im.convert("RGBa").resize((w, h), Image.LANCZOS).convert("RGBA")


def rel_lum(hexc: str) -> float:
    hexc = hexc.lstrip("#")
    rgb = [int(hexc[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted([rel_lum(a), rel_lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def brand_on_dark(slug: str, bg: str = SURF) -> str:
    """Brand colour when it reads on the dark chip, else monochrome off-white
    (Simple Icons allows monochrome use)."""
    hexc = "#" + ICONS[slug]["hex"]
    return hexc if contrast(hexc, bg) >= 2.4 else INK


def keytimes(times: list[float], dur: float) -> str:
    return ";".join(fmt(min(max(t / dur, 0), 1)) for t in times)


class Doc:
    def __init__(self, prefix: str, w: int, h: int, title: str, desc: str):
        self.p, self.w, self.h = prefix, w, h
        self.title, self.desc = title, desc
        self.chars: dict[str, set[str]] = defaultdict(set)
        self.defs: list[str] = []
        self.css: list[str] = []
        self.symbols: set[str] = set()
        self._n = 0

    # ids / classes are namespaced with the file prefix
    def i(self, name: str) -> str:
        return f"{self.p}-{name}"

    def url(self, name: str) -> str:
        return f"url(#{self.p}-{name})"

    def uid(self, stem: str) -> str:
        self._n += 1
        return f"{stem}{self._n}"

    def reg(self, font: str, s: str) -> None:
        self.chars[font].update(s)

    def text(self, x, y, s, font, size, fill=INK, anchor=None, ls=None, cls="", attrs="") -> str:
        self.reg(font, s)
        a = f' text-anchor="{anchor}"' if anchor else ""
        l = f' letter-spacing="{fmt(ls)}"' if ls else ""
        c = f"{self.p}-{font}" + (f" {cls}" if cls else "")
        return (
            f'<text x="{fmt(x)}" y="{fmt(y)}" class="{c}" font-size="{fmt(size)}" '
            f'fill="{fill}"{a}{l}{attrs}>{esc(s)}</text>'
        )

    def icon(self, slug: str, x, y, size, fill) -> str:
        self.symbols.add(slug)
        return (
            f'<use href="#{self.p}-i-{slug}" x="{fmt(x)}" y="{fmt(y)}" '
            f'width="{fmt(size)}" height="{fmt(size)}" fill="{fill}"/>'
        )

    # ------------------------------------------------------------ output
    def render(self, body: str) -> str:
        p = self.p
        fonts_css = []
        families_used = set()
        for font in sorted(self.chars):
            fam, wt, fn = FONT_FILES[font]
            families_used.add(fam)
            data = subset_woff2(VENDOR / "fonts" / fn, self.chars[font])
            fonts_css.append(
                f"@font-face{{font-family:'{fam}';font-style:normal;font-weight:{wt};"
                f"font-display:block;src:url(data:font/woff2;base64,{b64(data)}) format('woff2')}}"
            )
            stack = (
                "ui-sans-serif,system-ui,'Segoe UI',Roboto,sans-serif"
                if "Bricolage" in fam
                else "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
            )
            fonts_css.append(f".{p}-{font}{{font-family:'{fam}',{stack};font-weight:{wt}}}")
        base_css = f"""
text{{font-kerning:normal}}
@keyframes {p}-up{{from{{opacity:0;transform:translateY(26px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes {p}-left{{from{{opacity:0;transform:translateX(46px)}}to{{opacity:1;transform:translateX(0)}}}}
@keyframes {p}-fade{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes {p}-blink{{0%,49%{{opacity:1}}50%,100%{{opacity:0}}}}
.{p}-up{{animation:{p}-up .9s cubic-bezier(.16,1,.3,1) both}}
.{p}-left{{animation:{p}-left .9s cubic-bezier(.16,1,.3,1) both}}
.{p}-fade{{animation:{p}-fade .9s ease-out both}}
.{p}-static{{display:none}}
"""
        reduced = f"""
@media (prefers-reduced-motion:reduce){{
*{{animation:none!important}}
.{p}-motion{{display:none}}
.{p}-static{{display:inline}}
}}"""
        symbols = "".join(
            f'<symbol id="{p}-i-{s}" viewBox="0 0 24 24"><path d="{ICONS[s]["path"]}"/></symbol>'
            for s in sorted(self.symbols)
        )
        lic = "\n\n".join(
            f"Embedded font: {REAL_NAME[fam]} (subset, WOFF2).\n{LICENSE_TEXT[fam].strip()}"
            for fam in sorted(families_used)
        )
        icon_note = ""
        if self.symbols:
            icon_note = "Brand icons: " + ", ".join(
                f'{ICONS[s]["title"]} ({ICONS[s]["from"]}; source {ICONS[s]["source"]})'
                for s in sorted(self.symbols)
            ) + ". Simple Icons data is CC0-1.0; the marks remain trademarks of their owners."
        meta = esc(lic + ("\n\n" + icon_note if icon_note else ""))
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" fill="none" role="img" '
            f'aria-labelledby="{p}-title {p}-desc">\n'
            f'<title id="{p}-title">{esc(self.title)}</title>\n'
            f'<desc id="{p}-desc">{esc(self.desc)}</desc>\n'
            f"<metadata>{meta}</metadata>\n"
            f"<style>\n{chr(10).join(fonts_css)}\n{base_css}{''.join(self.css)}{reduced}\n</style>\n"
            f"<defs>{symbols}{''.join(self.defs)}</defs>\n"
            f"{body}\n</svg>\n"
        )


# ---------------------------------------------------------------- shared pieces
def frame_open(d: Doc, glows: list[tuple]) -> str:
    """Navy rounded card, soft colour glows and a subtle dot texture."""
    p, w, h = d.p, d.w, d.h
    d.defs.append(
        f'<clipPath id="{p}-card"><rect width="{w}" height="{h}" rx="28"/></clipPath>'
        f'<pattern id="{p}-dots" width="22" height="22" patternUnits="userSpaceOnUse">'
        f'<circle cx="11" cy="11" r="1.15" fill="#ffffff" fill-opacity=".075"/></pattern>'
        f'<linearGradient id="{p}-hair" x1="0" y1="0" x2="{w}" y2="{h}" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{BLUE}"/><stop offset=".5" stop-color="#ffffff" stop-opacity=".14"/>'
        f'<stop offset="1" stop-color="{CRIMSON}"/></linearGradient>'
        f'<radialGradient id="{p}-gB"><stop offset="0" stop-color="{BLUE}" stop-opacity=".30"/>'
        f'<stop offset="1" stop-color="{BLUE}" stop-opacity="0"/></radialGradient>'
        f'<radialGradient id="{p}-gR"><stop offset="0" stop-color="{CRIMSON}" stop-opacity=".22"/>'
        f'<stop offset="1" stop-color="{CRIMSON}" stop-opacity="0"/></radialGradient>'
        f'<linearGradient id="{p}-tile" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{BLUE}" stop-opacity=".55"/><stop offset=".5" stop-color="#ffffff" stop-opacity=".08"/>'
        f'<stop offset="1" stop-color="{CRIMSON}" stop-opacity=".55"/></linearGradient>'
    )
    g = "".join(
        f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="url(#{p}-g{c})"/>' for cx, cy, rx, ry, c in glows
    )
    return (
        f'<rect width="{w}" height="{h}" rx="28" fill="{NAVY}"/>'
        f'<g clip-path="url(#{p}-card)">{g}<rect width="{w}" height="{h}" fill="url(#{p}-dots)"/></g>'
    )


def frame_close(d: Doc) -> str:
    return (
        f'<rect x=".75" y=".75" width="{d.w - 1.5}" height="{d.h - 1.5}" rx="27.25" '
        f'stroke="url(#{d.p}-hair)" stroke-width="1.5" stroke-opacity=".9"/>'
    )


def panel(d: Doc, x, y, w, h, r=20, fill=SURF, op=0.92) -> str:
    """Rounded card with gradient hairline border."""
    return (
        f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" rx="{r}" fill="{fill}" fill-opacity="{op}"/>'
        f'<rect x="{fmt(x + .5)}" y="{fmt(y + .5)}" width="{fmt(w - 1)}" height="{fmt(h - 1)}" rx="{r - .5}" '
        f'stroke="url(#{d.p}-tile)" stroke-width="1"/>'
    )


def kicker(d: Doc, x, y, num: str, label: str) -> str:
    return (
        f'<rect x="{x}" y="{y - 10}" width="18" height="3" rx="1.5" fill="{CRIMSON}"/>'
        + d.text(x + 28, y, f"{num} — {label}", "m7", 14, BLUE, ls=2.2)
    )


def delay(s: float) -> str:
    return f' style="animation-delay:{fmt(s)}s"'


# small hand-drawn UI glyphs (not brand marks), 24x24 grid, stroked
GLYPHS = {
    "pin": '<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0C18.5 15.4 12 21 12 21z"/><circle cx="12" cy="10" r="2.4"/>',
    "bag": '<rect x="3.5" y="7.5" width="17" height="12" rx="2.5"/><path d="M8.5 7.5V6a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v1.5M3.5 13h17"/>',
    "spark": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.5 2.5M15.2 15.2l2.5 2.5M6.3 17.7l2.5-2.5M15.2 8.8l2.5-2.5"/><circle cx="12" cy="12" r="2.2"/>',
    "layers": '<path d="M12 3.5 3.5 8 12 12.5 20.5 8z"/><path d="M3.5 12 12 16.5 20.5 12M3.5 16 12 20.5 20.5 16"/>',
    "chip": '<rect x="6.5" y="6.5" width="11" height="11" rx="1.8"/><path d="M9.5 3v3.5M14.5 3v3.5M9.5 17.5V21M14.5 17.5V21M3 9.5h3.5M3 14.5h3.5M17.5 9.5H21M17.5 14.5H21"/><rect x="10" y="10" width="4" height="4" rx=".6"/>',
    "flow": '<rect x="3" y="4" width="7" height="5" rx="1.4"/><rect x="14" y="15" width="7" height="5" rx="1.4"/><path d="M6.5 9v4.5a2 2 0 0 0 2 2H14"/><path d="m12 13 2.2 2.5L12 18"/>',
    "repo": '<path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5z"/><path d="M5 19.5A1.5 1.5 0 0 0 6.5 21H19v-3M9 7h6"/>',
    "star": '<path d="m12 3.6 2.6 5.3 5.8.8-4.2 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.2-4.1 5.8-.8z"/>',
    "users": '<circle cx="9" cy="8.5" r="3.2"/><path d="M3.5 19.5a5.5 5.5 0 0 1 11 0"/><circle cx="17" cy="9.5" r="2.5"/><path d="M15.5 14.4a4.6 4.6 0 0 1 5 5.1"/>',
    "cal": '<rect x="3.5" y="5" width="17" height="15.5" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    "trophy": '<path d="M7.5 4h9v5a4.5 4.5 0 0 1-9 0z"/><path d="M7.5 6H4.5a3 3 0 0 0 3 4M16.5 6h3a3 3 0 0 1-3 4M12 13.5V17M8.5 20.5h7M9.5 17h5v3.5h-5z"/>',
    "arrow": '<path d="M5 12h13M13 6.5 18.5 12 13 17.5"/>',
}


def glyph(name: str, x, y, size, color, sw=1.8) -> str:
    s = size / 24
    return (
        f'<g transform="translate({fmt(x)} {fmt(y)}) scale({fmt(s)})" stroke="{color}" '
        f'stroke-width="{fmt(sw / s)}" stroke-linecap="round" stroke-linejoin="round" fill="none">'
        f"{GLYPHS[name]}</g>"
    )


def star_path(cx, cy, r) -> str:
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * 0.45
        pts.append(f"{fmt(cx + rr * math.cos(a))} {fmt(cy + rr * math.sin(a))}")
    return "M" + " L".join(pts) + "Z"


# ======================================================================= HERO
PITCH = "I turn data into decisions with AI workflows, web apps & IoT."
ROLES = ["Forward Deployed Engineer", "AI / ML Engineer", "Full-stack Developer", "IoT & Automation Builder"]
LOCATION = "Bargarh, Odisha, India"
ROLE_LINE = "AI/ML Forward Deployed Engineer"


def build_hero() -> str:
    d = Doc(
        "hero", 1000, 560,
        "Manash Ranjan — AI/ML Forward Deployed Full-stack Engineer",
        f"Animated intro card. Typed greeting 'Hi there, I'm', the name Manash Ranjan revealed line by line, "
        f"cycling roles ({', '.join(ROLES)}), the pitch '{PITCH}', location {LOCATION}, role {ROLE_LINE}, "
        "and Manash's portrait on the right.",
    )
    p = d.p
    W, H = d.w, d.h
    body = [frame_open(d, [(150, 40, 420, 260, "B"), (930, 560, 420, 300, "R"), (800, 250, 260, 260, "B")])]

    # ---------- portrait side
    cx, cy, R = 822, 250, 170
    circ = 2 * math.pi * R
    d.defs.append(
        f'<linearGradient id="{p}-ring" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BLUE}"/>'
        f'<stop offset="1" stop-color="{CRIMSON}"/></linearGradient>'
        f'<radialGradient id="{p}-disc" cx=".5" cy=".45" r=".55"><stop offset="0" stop-color="#16295a" stop-opacity=".95"/>'
        f'<stop offset=".7" stop-color="#0d1630" stop-opacity=".55"/><stop offset="1" stop-color="{NAVY}" stop-opacity="0"/></radialGradient>'
    )
    d.css.append(
        f"@keyframes {p}-draw{{from{{stroke-dashoffset:{fmt(circ)}}}to{{stroke-dashoffset:0}}}}"
        f".{p}-draw{{stroke-dasharray:{fmt(circ)};stroke-dashoffset:0;animation:{p}-draw 1.8s cubic-bezier(.65,0,.35,1) .5s both}}"
    )
    portrait = resize_rgba(load_rgba("id.png"), 600)
    img_w, img_h = 390, 520
    body.append(
        f'<g clip-path="url(#{p}-card)">'
        f'<circle cx="{cx}" cy="{cy}" r="{R - 6}" fill="url(#{p}-disc)"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{R + 26}" stroke="#ffffff" stroke-opacity=".08" stroke-dasharray="2 9"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{R}" stroke="url(#{p}-ring)" stroke-width="2" stroke-opacity=".85" '
        f'class="{p}-draw" transform="rotate(-90 {cx} {cy})"/>'
        # orbiting dot (SMIL, decorative)
        f'<g class="{p}-motion"><circle cx="{cx}" cy="{cy - R}" r="5" fill="{CRIMSON}">'
        f"</circle><circle cx=\"{cx}\" cy=\"{cy - R}\" r=\"10\" fill=\"{CRIMSON}\" fill-opacity=\".25\"/>"
        f'<animateTransform attributeName="transform" type="rotate" values="0 {cx} {cy};360 {cx} {cy}" '
        f'dur="16s" begin="0s" repeatCount="indefinite"/></g>'
        f'<g class="{p}-up"{delay(.25)}><image href="{png_uri(portrait)}" x="{W - img_w + 12}" y="{H - img_h}" '
        f'width="{img_w}" height="{img_h}" preserveAspectRatio="xMidYMax meet"/></g>'
        f"</g>"
    )

    # ---------- greeting (typed)
    x0 = 64
    gsize = 22
    greet = "> Hi there, I'm"
    adv = tw("M", "m5", gsize)
    n = len(greet)
    t0, step = 0.25, 0.07
    dur = t0 + n * step + 0.05
    widths = [0] + [k * adv for k in range(1, n + 1)]
    kt = [0] + [t0 + k * step for k in range(1, n + 1)]
    full = n * adv
    d.defs.append(
        f'<clipPath id="{p}-type"><rect x="{x0 - 2}" y="84" width="{fmt(full + 4)}" height="36">'
        f'<animate attributeName="width" begin="0s" dur="{fmt(dur)}s" fill="freeze" calcMode="discrete" '
        f'values="{";".join(fmt(w + 4) if w else "0" for w in widths)}" keyTimes="{keytimes(kt, dur)}"/></rect></clipPath>'
    )
    d.reg("m5", greet)
    gtext = (
        f'<text x="{x0}" y="110" class="{p}-m5" font-size="{gsize}" fill="{BLUE}">'
        f'<tspan fill="{CRIMSON}">&gt;</tspan>{esc(greet[1:])}</text>'
    )
    caret_x = [x0 + w + 3 for w in widths]
    d.css.append(f".{p}-caret{{animation:{p}-blink 1.05s steps(1) {fmt(dur)}s infinite}}")
    body.append(
        f'<g class="{p}-motion"><g clip-path="url(#{p}-type)">{gtext}</g>'
        f'<rect x="{fmt(caret_x[-1])}" y="91" width="11" height="24" rx="1.5" fill="{BLUE}" class="{p}-caret">'
        f'<animate attributeName="x" begin="0s" dur="{fmt(dur)}s" fill="freeze" calcMode="discrete" '
        f'values="{";".join(fmt(c) for c in caret_x)}" keyTimes="{keytimes(kt, dur)}"/></rect></g>'
        f'<g class="{p}-static">{gtext}<rect x="{fmt(caret_x[-1])}" y="91" width="11" height="24" rx="1.5" fill="{BLUE}"/></g>'
    )

    # ---------- name with rising masks
    nsize, nls = 118, -3
    lines = [("Manash", 222, INK), ("Ranjan", 334, f"url(#{p}-name)")]
    wname = max(tw(s, "d8", nsize, nls) for s, _, _ in lines)
    if x0 + wname > 590:
        raise SystemExit(f"name too wide: {wname}")
    d.defs.append(
        f'<linearGradient id="{p}-name" x1="{x0}" y1="0" x2="{fmt(x0 + tw("Ranjan", "d8", nsize, nls))}" y2="0" '
        f'gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="{CRIMSON}"/></linearGradient>'
    )
    d.css.append(
        f"@keyframes {p}-rise{{from{{transform:translateY(140px)}}to{{transform:translateY(0)}}}}"
        f".{p}-rise{{animation:{p}-rise 1.05s cubic-bezier(.16,1,.3,1) both}}"
    )
    clips = [(118, 132), (226, 150)]  # (top, height) – line 2 includes the 'j' descender
    for k, ((s, base, fill), (top, hh)) in enumerate(zip(lines, clips)):
        d.defs.append(f'<clipPath id="{p}-ln{k}"><rect x="40" y="{top}" width="580" height="{hh}"/></clipPath>')
        body.append(
            f'<g clip-path="url(#{p}-ln{k})"><g class="{p}-rise"{delay(1.15 + k * .2)}>'
            + d.text(x0 - 4, base, s, "d8", nsize, fill, ls=nls)
            + "</g></g>"
        )

    # ---------- cycling roles (SMIL, 14 s loop, 3.5 s per role)
    ry = 396
    rsize = 30
    cyc, slot, tr = 14.0, 3.5, 0.35
    role_items = []
    for k, role in enumerate(ROLES):
        s, e = k * slot, (k + 1) * slot
        if k == 0:
            times = [0, tr, e - tr, e, cyc]
            ops = [0, 1, 1, 0, 0]
            ys = [18, 0, 0, -18, -18]
        else:
            times = [0, s, s + tr, e - tr, e]
            ops = [0, 0, 1, 1, 0]
            ys = [18, 18, 0, 0, -18]
            if e < cyc:
                times.append(cyc)
                ops.append(0)
                ys.append(-18)
        splines = ";".join([".2 .8 .2 1"] * (len(times) - 1))
        base_op = 1 if k == 0 else 0
        role_items.append(
            f'<g opacity="{base_op}"><animate attributeName="opacity" begin="0s" dur="{fmt(cyc)}s" repeatCount="indefinite" '
            f'calcMode="spline" keySplines="{splines}" values="{";".join(map(str, ops))}" keyTimes="{keytimes(times, cyc)}"/>'
            f'<animateTransform attributeName="transform" type="translate" begin="0s" dur="{fmt(cyc)}s" repeatCount="indefinite" '
            f'calcMode="spline" keySplines="{splines}" values="{";".join(f"0 {v}" for v in ys)}" keyTimes="{keytimes(times, cyc)}"/>'
            + d.text(x0 + 24, ry, role, "d6", rsize, INK, ls=-.3)
            + "</g>"
        )
    body.append(
        f'<g class="{p}-up"{delay(2.0)}>'
        f'<rect x="{x0}" y="{ry - 21}" width="12" height="12" rx="3" fill="{CRIMSON}" transform="rotate(45 {x0 + 6} {ry - 15})"/>'
        f'<g clip-path="url(#{p}-rclip)"><g class="{p}-motion">{"".join(role_items)}</g>'
        f'<g class="{p}-static">{d.text(x0 + 24, ry, ROLES[0], "d6", rsize, INK, ls=-.3)}</g></g></g>'
    )
    d.defs.append(f'<clipPath id="{p}-rclip"><rect x="{x0 + 18}" y="{ry - 36}" width="520" height="50"/></clipPath>')

    # ---------- pitch
    psize = 18.5
    pw = tw(PITCH, "d4", psize)
    if x0 + pw > 590:
        raise SystemExit(f"pitch too wide: {pw:.0f}")
    body.append(f'<g class="{p}-up"{delay(2.25)}>' + d.text(x0, 440, PITCH, "d4", psize, MUTED) + "</g>")

    # ---------- location / role chips
    cx0, cyy, ch = x0, 474, 40
    for k, (gname, label) in enumerate([("pin", LOCATION), ("bag", ROLE_LINE)]):
        wlab = tw(label, "d5", 15)
        cw = wlab + 54
        body.append(
            f'<g class="{p}-up"{delay(2.45 + k * .12)}>'
            f'<rect x="{fmt(cx0)}" y="{cyy}" width="{fmt(cw)}" height="{ch}" rx="20" fill="{SURF2}" fill-opacity=".9" stroke="{LINE}"/>'
            + glyph(gname, cx0 + 14, cyy + 10, 20, BLUE if k == 0 else CRIMSON, 2)
            + d.text(cx0 + 41, cyy + 25.5, label, "d5", 15, INK)
            + "</g>"
        )
        cx0 += cw + 12
    if cx0 - 12 > 606:
        raise SystemExit(f"chips too wide: {cx0}")

    body.append(frame_close(d))
    return d.render("".join(body))


# ======================================================================= ABOUT + LIFE
CAPS = [
    ("spark", "AI workflows & agents", "LangChain, LangGraph & Gemini pipelines"),
    ("layers", "Full-stack web apps", "React + Node/Express APIs on MongoDB"),
    ("chip", "IoT & device integration", "ESP32 & Arduino over MQTT and WebSockets"),
    ("flow", "Automation & data pipelines", "Playwright scrapers that ship Excel reports"),
]
SLIDES = [
    ("3D art in Blender", ["Modelling, lighting and rendering", "3D scenes, one frame at a time."]),
    ("Electronics tinkering", ["ESP32, Arduino and Raspberry Pi", "builds, wired up to the cloud."]),
    ("Hackathons", ["Shipping prototypes against the clock,", "from HackFest 2.0 to SIH 2025."]),
]


def slide_blender(d: Doc, ax, ay, aw, ah) -> str:
    p = d.p
    cx, cy, R = ax + aw / 2 + 30, ay + ah / 2 + 4, 72
    orange = "#" + ICONS["blender"]["hex"]
    d.defs.append(
        f'<radialGradient id="{p}-sph" cx=".38" cy=".34" r=".75"><stop offset="0" stop-color="{orange}" stop-opacity=".42"/>'
        f'<stop offset=".6" stop-color="{orange}" stop-opacity=".12"/><stop offset="1" stop-color="{orange}" stop-opacity=".04"/></radialGradient>'
        f'<radialGradient id="{p}-shadow"><stop offset="0" stop-color="#000" stop-opacity=".55"/><stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>'
    )
    out = [
        f'<ellipse cx="{fmt(cx)}" cy="{fmt(cy + R + 14)}" rx="{R}" ry="10" fill="url(#{p}-shadow)"/>',
        f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{R}" fill="url(#{p}-sph)"/>',
    ]
    # latitude rings (static) – a UV sphere seen slightly from above
    for phi in (-60, -30, 0, 30, 60):
        r = R * math.cos(math.radians(phi))
        yy = cy + R * math.sin(math.radians(phi))
        out.append(
            f'<ellipse cx="{fmt(cx)}" cy="{fmt(yy)}" rx="{fmt(r)}" ry="{fmt(r * .26)}" stroke="{orange}" stroke-opacity=".5" stroke-width="1.2"/>'
        )
    # meridians rotate: rx = R*|cos(a + wt)|, sampled
    N = 24
    for k in range(6):
        a = k * math.pi / 6
        vals = [R * abs(math.cos(a + 2 * math.pi * s / N / 2)) for s in range(N + 1)]
        out.append(
            f'<ellipse cx="{fmt(cx)}" cy="{fmt(cy)}" rx="{fmt(vals[0])}" ry="{R}" stroke="{orange}" stroke-opacity=".75" stroke-width="1.3">'
            f'<animate attributeName="rx" begin="0s" dur="9s" repeatCount="indefinite" values="{";".join(fmt(v) for v in vals)}"/></ellipse>'
        )
    out.append(f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{R}" stroke="{orange}" stroke-width="2"/>')
    out.append(f'<ellipse cx="{fmt(cx - 26)}" cy="{fmt(cy - 30)}" rx="16" ry="10" fill="#fff" fill-opacity=".14" transform="rotate(-30 {fmt(cx - 26)} {fmt(cy - 30)})"/>')
    # viewport gizmo
    gx, gy = ax + aw - 34, ay + ah - 30
    out.append(
        f'<g stroke-width="2.2" stroke-linecap="round"><path d="M{gx} {gy}h18" stroke="{CRIMSON}"/>'
        f'<path d="M{gx} {gy}l-10 9" stroke="#8bd450"/><path d="M{gx} {gy}v-18" stroke="{BLUE}"/></g>'
        f'<circle cx="{gx}" cy="{gy}" r="2.6" fill="{INK}"/>'
    )
    # brand chip
    out.append(
        f'<rect x="{ax + 16}" y="{ay + 16}" width="40" height="40" rx="11" fill="{SURF2}" stroke="{LINE}"/>'
        + d.icon("blender", ax + 26, ay + 26, 20, orange)
        + d.text(ax + 66, ay + 41, "uv_sphere.blend", "m5", 14, DIM)
    )
    return "".join(out)


def slide_iot(d: Doc, ax, ay, aw, ah) -> str:
    p = d.p
    teal = "#" + ICONS["arduino"]["hex"]
    bx, by, bw, bh = ax + 70, ay + 34, aw - 96, ah - 62
    out = [
        f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="14" fill="#0a1d22" stroke="{teal}" stroke-opacity=".75" stroke-width="1.4"/>'
    ]
    # header pins
    for row_y in (by + 12, by + bh - 20):
        for k in range(10):
            out.append(f'<rect x="{fmt(bx + 26 + k * 21)}" y="{row_y}" width="8" height="8" rx="1.5" fill="#d4a531" fill-opacity=".85"/>')
    # module with PCB antenna
    mx, my, mw, mh = bx + bw / 2 - 52, by + bh / 2 - 34, 104, 68
    out.append(
        f'<rect x="{fmt(mx)}" y="{fmt(my)}" width="{mw}" height="{mh}" rx="6" fill="#111a2c" stroke="#3b4b6b"/>'
        f'<path d="M{fmt(mx + 10)} {fmt(my + 12)}h10v-6h8v6h8v-6h8v6h8v-6h8v6h10" stroke="#d4a531" stroke-opacity=".8" stroke-width="1.6" fill="none"/>'
        + d.text(mx + mw / 2, my + 48, "ESP32", "m7", 17, INK, anchor="middle", ls=1)
    )
    # traces + travelling pulses
    traces = [
        f"M{fmt(mx)} {fmt(my + 40)}H{fmt(bx + 60)}V{fmt(by + 20)}",
        f"M{fmt(mx + mw)} {fmt(my + 40)}H{fmt(bx + bw - 56)}V{fmt(by + bh - 16)}",
        f"M{fmt(mx + 30)} {fmt(my + mh)}V{fmt(by + bh - 16)}",
        f"M{fmt(mx + mw - 30)} {fmt(my)}V{fmt(by + 20)}",
    ]
    for k, t in enumerate(traces):
        L = 260
        out.append(f'<path d="{t}" stroke="{teal}" stroke-opacity=".6" stroke-width="2" fill="none"/>')
        out.append(
            f'<path d="{t}" stroke="{BLUE}" stroke-width="2.6" stroke-linecap="round" fill="none" stroke-dasharray="12 {L - 12}" stroke-dashoffset="0">'
            f'<animate attributeName="stroke-dashoffset" begin="0s" dur="2.2s" repeatCount="indefinite" '
            f'values="{L - k * 40};{-k * 40}"/></path>'
        )
    # blinking LED
    lx, ly = bx + bw - 26, by + bh / 2
    d.defs.append(
        f'<radialGradient id="{p}-led"><stop offset="0" stop-color="{CRIMSON}" stop-opacity=".8"/><stop offset="1" stop-color="{CRIMSON}" stop-opacity="0"/></radialGradient>'
    )
    out.append(
        f'<g><circle cx="{fmt(lx)}" cy="{fmt(ly)}" r="16" fill="url(#{p}-led)"/><circle cx="{fmt(lx)}" cy="{fmt(ly)}" r="5.5" fill="{CRIMSON}"/>'
        f'<animate attributeName="opacity" begin="0s" dur="1.2s" repeatCount="indefinite" values="1;1;.2;.2;1" keyTimes="0;.45;.5;.95;1"/></g>'
    )
    out.append(
        f'<rect x="{ax + 16}" y="{ay + 16}" width="40" height="40" rx="11" fill="{SURF2}" stroke="{LINE}"/>'
        + d.icon("arduino", ax + 26, ay + 26, 20, brand_on_dark("arduino", SURF2))
        + f'<rect x="{ax + 16}" y="{ay + 64}" width="40" height="40" rx="11" fill="{SURF2}" stroke="{LINE}"/>'
        + d.icon("espressif", ax + 26, ay + 74, 20, brand_on_dark("espressif", SURF2))
        + f'<rect x="{ax + 16}" y="{ay + 112}" width="40" height="40" rx="11" fill="{SURF2}" stroke="{LINE}"/>'
        + d.icon("raspberrypi", ax + 26, ay + 122, 20, brand_on_dark("raspberrypi", SURF2))
    )
    return "".join(out)


def slide_hack(d: Doc, ax, ay, aw, ah) -> str:
    p = d.p
    tx, ty, tw_, th = ax + 16, ay + 18, 232, ah - 36
    out = [
        f'<rect x="{tx}" y="{ty}" width="{tw_}" height="{th}" rx="12" fill="#0a1120" stroke="{LINE}"/>',
        f'<path d="M{tx} {ty + 28}h{tw_}" stroke="{LINE}"/>',
    ]
    for k, c in enumerate((CRIMSON, "#ffb84d", "#3ccf7a")):
        out.append(f'<circle cx="{tx + 16 + k * 14}" cy="{ty + 14}" r="4.2" fill="{c}"/>')
    lines = ["git checkout -b demo", "npm run build", "git push origin demo"]
    for k, ln in enumerate(lines):
        yy = ty + 58 + k * 30
        d.reg("m5", "$ " + ln)
        out.append(
            f'<text x="{tx + 14}" y="{yy}" class="{p}-m5" font-size="13.5" fill="{INK}">'
            f'<tspan fill="{BLUE}">$</tspan> {esc(ln)}</text>'
        )
    out.append(
        f'<rect x="{tx + 14}" y="{ty + 132}" width="8" height="15" fill="{BLUE}"><animate attributeName="opacity" begin="0s" dur="1s" '
        f'repeatCount="indefinite" calcMode="discrete" values="1;0" keyTimes="0;.5"/></rect>'
    )
    # countdown ring
    rcx, rcy, rr = ax + aw - 62, ay + ah / 2 - 6, 40
    C = 2 * math.pi * rr
    d.defs.append(
        f'<linearGradient id="{p}-arc" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="{CRIMSON}"/></linearGradient>'
    )
    out.append(
        f'<circle cx="{fmt(rcx)}" cy="{fmt(rcy)}" r="{rr}" stroke="{LINE}" stroke-width="7"/>'
        f'<circle cx="{fmt(rcx)}" cy="{fmt(rcy)}" r="{rr}" stroke="url(#{p}-arc)" stroke-width="7" stroke-linecap="round" '
        f'stroke-dasharray="{fmt(C)}" stroke-dashoffset="{fmt(C * .25)}" transform="rotate(-90 {fmt(rcx)} {fmt(rcy)})">'
        f'<animate attributeName="stroke-dashoffset" begin="0s" dur="4s" repeatCount="indefinite" values="{fmt(C)};{fmt(C * .02)}"/></circle>'
        + glyph("trophy", rcx - 15, rcy - 16, 30, INK, 1.8)
        + d.text(rcx, rcy + rr + 30, "ship it", "m5", 14, DIM, anchor="middle")
    )
    return "".join(out)


def build_about() -> str:
    d = Doc(
        "abt", 1000, 520,
        "What I build, and what I do off the clock",
        "Left: four capabilities — " + "; ".join(f"{t}: {s}" for _, t, s in CAPS)
        + ". Right: a carousel that changes every 4 seconds through three interests — "
        + "; ".join(f"{t}: {' '.join(c)}" for t, c in SLIDES) + ".",
    )
    p = d.p
    body = [frame_open(d, [(120, 0, 380, 240, "B"), (980, 520, 380, 260, "R")])]

    # ---------- capabilities
    x0 = 56
    body.append(f'<g class="{p}-up"{delay(.1)}>' + kicker(d, x0, 78, "01", "WHAT I DO") + "</g>")
    body.append(f'<g class="{p}-up"{delay(.2)}>' + d.text(x0 - 2, 124, "What I build", "d8", 42, INK, ls=-1) + "</g>")
    for k, (gname, title, sub) in enumerate(CAPS):
        y = 160 + k * 84
        if x0 + 72 + tw(sub, "d4", 16.5) > 512:
            raise SystemExit(f"capability text too wide: {sub}")
        body.append(
            f'<g class="{p}-up"{delay(.35 + k * .12)}>'
            f'<rect x="{x0}" y="{y}" width="54" height="54" rx="16" fill="{SURF2}"/>'
            f'<rect x="{x0 + .5}" y="{y + .5}" width="53" height="53" rx="15.5" stroke="url(#{p}-tile)"/>'
            + glyph(gname, x0 + 15, y + 15, 24, BLUE if k % 2 == 0 else CRIMSON, 1.9)
            + d.text(x0 + 72, y + 22, title, "d6", 21, INK)
            + d.text(x0 + 72, y + 46, sub, "d4", 16.5, MUTED)
            + "</g>"
        )

    # ---------- carousel card
    cx, cy, cw, chh = 532, 40, 420, 440
    pad = 24
    ax, ay, aw, ah = cx + pad, cy + 84, cw - 2 * pad, 200
    seg_gap = 8
    seg_w = (cw - 2 * pad - 2 * seg_gap) / 3
    cyc = 12.0
    card = [panel(d, cx, cy, cw, chh, 24, SURF, .94)]
    card.append(kicker(d, cx + pad, cy + 60, "02", "OFF THE CLOCK"))
    d.defs.append(
        f'<linearGradient id="{p}-seg" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="{CRIMSON}"/></linearGradient>'
        f'<clipPath id="{p}-area"><rect x="{ax}" y="{ay}" width="{aw}" height="{ah}" rx="18"/></clipPath>'
    )
    # segment progress bars
    segs = []
    for k in range(3):
        sx = cx + pad + k * (seg_w + seg_gap)
        if k == 0:
            vals, times = [0, seg_w, seg_w], [0, 4, cyc]
        elif k == 1:
            vals, times = [0, 0, seg_w, seg_w], [0, 4, 8, cyc]
        else:
            vals, times = [0, 0, seg_w], [0, 8, cyc]
        base = seg_w if k == 0 else 0
        segs.append(
            f'<rect x="{fmt(sx)}" y="{cy + 22}" width="{fmt(seg_w)}" height="5" rx="2.5" fill="#ffffff" fill-opacity=".12"/>'
            f'<rect x="{fmt(sx)}" y="{cy + 22}" width="{fmt(base)}" height="5" rx="2.5" fill="url(#{p}-seg)">'
            f'<animate attributeName="width" begin="0s" dur="{fmt(cyc)}s" repeatCount="indefinite" '
            f'values="{";".join(fmt(v) for v in vals)}" keyTimes="{keytimes(times, cyc)}"/></rect>'
        )
    static_segs = (
        f'<rect x="{cx + pad}" y="{cy + 22}" width="{cw - 2 * pad}" height="5" rx="2.5" fill="url(#{p}-seg)"/>'
    )
    # slides
    makers = [slide_blender, slide_iot, slide_hack]
    slides = []
    for k, ((title, cap), mk) in enumerate(zip(SLIDES, makers)):
        s, e = 4 * k, 4 * (k + 1)
        t1 = .3
        if k == 0:
            times = [0, e - t1, e, cyc - t1, cyc]
            ops = [1, 1, 0, 0, 1]
            xs = [0, 0, -26, 26, 0]
        elif k == 1:
            times = [0, s - t1, s, e - t1, e, cyc]
            ops = [0, 0, 1, 1, 0, 0]
            xs = [26, 26, 0, 0, -26, -26]
        else:
            times = [0, s - t1, s, cyc - t1, cyc]
            ops = [0, 0, 1, 1, 0]
            xs = [26, 26, 0, 0, -26]
        content = (
            f'<rect x="{ax}" y="{ay}" width="{aw}" height="{ah}" rx="18" fill="#0a1121" stroke="{LINE}"/>'
            f'<g clip-path="url(#{p}-area)"><rect x="{ax}" y="{ay}" width="{aw}" height="{ah}" fill="url(#{p}-dots)"/>'
            + mk(d, ax, ay, aw, ah)
            + "</g>"
            + d.text(cx + cw - pad, cy + 60, f"0{k + 1} / 03", "m5", 14, DIM, anchor="end")
            + d.text(cx + pad, ay + ah + 46, title, "d8", 31, INK, ls=-.6)
            + "".join(d.text(cx + pad, ay + ah + 78 + j * 25, ln, "d4", 17, MUTED) for j, ln in enumerate(cap))
        )
        for ln in cap:
            if tw(ln, "d4", 17) > cw - 2 * pad:
                raise SystemExit(f"slide caption too wide: {ln}")
        slides.append(
            f'<g opacity="{1 if k == 0 else 0}">'
            f'<animate attributeName="opacity" begin="0s" dur="{fmt(cyc)}s" repeatCount="indefinite" values="{";".join(map(str, ops))}" keyTimes="{keytimes(times, cyc)}"/>'
            f'<animateTransform attributeName="transform" type="translate" begin="0s" dur="{fmt(cyc)}s" repeatCount="indefinite" '
            f'values="{";".join(f"{v} 0" for v in xs)}" keyTimes="{keytimes(times, cyc)}"/>'
            f"{content}</g>"
        )
    # reduced-motion: all three interests listed at once
    static_rows = []
    icons = [("blender", None), ("arduino", None), (None, "trophy")]
    for k, ((title, cap), (slug, gl)) in enumerate(zip(SLIDES, icons)):
        y = cy + 96 + k * 108
        tile = f'<rect x="{cx + pad}" y="{y}" width="56" height="56" rx="16" fill="{SURF2}" stroke="{LINE}"/>'
        ic = d.icon(slug, cx + pad + 16, y + 16, 24, brand_on_dark(slug, SURF2)) if slug else glyph(gl, cx + pad + 15, y + 15, 26, INK)
        static_rows.append(
            tile + ic + d.text(cx + pad + 74, y + 24, title, "d6", 22, INK)
            + d.text(cx + pad + 74, y + 49, cap[0], "d4", 16, MUTED)
            + d.text(cx + pad + 74, y + 71, cap[1], "d4", 16, MUTED)
        )
    card.append(f'<g class="{p}-motion">{"".join(segs)}{"".join(slides)}</g>')
    card.append(f'<g class="{p}-static">{static_segs}{"".join(static_rows)}</g>')
    body.append(f'<g class="{p}-left"{delay(.45)}>{"".join(card)}</g>')
    body.append(frame_close(d))
    return d.render("".join(body))


# ======================================================================= STACK
# Rings turn together (same period + direction) so the phase offsets below keep
# every pill clear of its neighbours for the whole loop; the geometry was chosen
# with a collision simulation (min clearance ~6 units incl. the core).
ORBIT_PERIOD = 40
ORBITS = [
    # rx, ry, tilt(deg), ring phase(deg), icons
    (150, 84, -6, 0, [("python", "Python"), ("javascript", "JavaScript"), ("typescript", "TypeScript")]),
    (290, 138, 3, 30, [("react", "React"), ("nodedotjs", "Node.js"), ("express", "Express"), ("mongodb", "MongoDB"), ("tailwindcss", "Tailwind CSS"), ("socketdotio", "Socket.io")]),
    (415, 194, -3, 0, [("langchain", "LangChain"), ("googlegemini", "Gemini"), ("tensorflow", "TensorFlow"), ("arduino", "Arduino"), ("espressif", "Espressif"), ("docker", "Docker")]),
]
STACK_GROUPS = [
    ("LANGUAGES", [("python", "Python"), ("javascript", "JavaScript"), ("typescript", "TypeScript"), ("cplusplus", "C++"), ("c", "C"), (None, "Java")]),
    ("FRONTEND", [("react", "React"), ("tailwindcss", "Tailwind CSS"), ("vite", "Vite"), ("threedotjs", "Three.js"), ("gsap", "GSAP")]),
    ("BACKEND & DATA", [("nodedotjs", "Node.js"), ("express", "Express"), ("fastapi", "FastAPI"), ("flask", "Flask"), ("mongodb", "MongoDB"), ("mysql", "MySQL"), ("socketdotio", "Socket.io")]),
    ("AI / ML", [("langchain", "LangChain"), ("langgraph", "LangGraph"), ("googlegemini", "Gemini API"), ("tensorflow", "TensorFlow"), ("pytorch", "PyTorch"), ("scikitlearn", "scikit-learn")]),
    ("IOT & AUTOMATION", [("espressif", "ESP32"), ("arduino", "Arduino"), ("raspberrypi", "Raspberry Pi"), ("mqtt", "MQTT"), (None, "Playwright"), ("n8n", "n8n")]),
    ("CLOUD & TOOLS", [("docker", "Docker"), (None, "AWS EC2"), ("vercel", "Vercel"), ("firebase", "Firebase"), ("git", "Git"), ("postman", "Postman")]),
]


def build_stack() -> str:
    W = 1000
    # ---- chip layout first so the canvas height follows the content
    col_w, col_gap, gx0 = 280, 24, 56
    chip_h, chip_gap, chip_font = 31, 8, 14.5
    group_layouts = []
    for gi, (gname, items) in enumerate(STACK_GROUPS):
        rows, cur, x = [], [], 0
        for slug, label in items:
            cw = tw(label, "m5", chip_font) + 35
            if cur and x + cw > col_w:
                rows.append(cur)
                cur, x = [], 0
            cur.append((slug, label, x, cw))
            x += cw + chip_gap
        rows.append(cur)
        group_layouts.append((gname, rows))
    row_heights = []
    for r in range(2):
        row_heights.append(max(34 + len(group_layouts[r * 3 + c][1]) * (chip_h + chip_gap) for c in range(3)))
    chips_top = 612
    H = int(chips_top + row_heights[0] + 22 + row_heights[1] + 34)
    d = Doc(
        "stk", W, H,
        "Tech stack",
        "Labelled tech icons orbit a core on three tilted rings — inner: "
        + ", ".join(l for _, l in ORBITS[0][4]) + "; middle: " + ", ".join(l for _, l in ORBITS[1][4])
        + "; outer: " + ", ".join(l for _, l in ORBITS[2][4]) + ". Below, grouped stack chips — "
        + "; ".join(f"{g.title()}: {', '.join(l for _, l in it)}" for g, it in STACK_GROUPS) + ".",
    )
    p = d.p
    body = [frame_open(d, [(500, 354, 470, 250, "B"), (980, H, 340, 240, "R"), (60, 60, 300, 200, "R")])]
    body.append(f'<g class="{p}-up"{delay(.05)}>' + kicker(d, 56, 72, "03", "TOOLKIT") + "</g>")
    body.append(f'<g class="{p}-up"{delay(.15)}>' + d.text(54, 118, "Tech I ship with", "d8", 42, INK, ls=-1) + "</g>")
    legend = [("inner", "languages"), ("middle", "web stack"), ("outer", "AI · IoT · cloud")]
    lx = W - 56
    leg = []
    for k, (a, b) in enumerate(reversed(legend)):
        s = f"{a} · {b}"
        leg.append(d.text(lx, 66 + (2 - k) * 22, s, "m5", 14, DIM, anchor="end"))
    body.append(f'<g class="{p}-fade"{delay(.3)}>{"".join(leg)}</g>')

    # ---- orbits
    ocx, ocy = 500, 354
    d.defs.append(
        f'<linearGradient id="{p}-orb" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{BLUE}"/>'
        f'<stop offset=".5" stop-color="#ffffff" stop-opacity=".25"/><stop offset="1" stop-color="{CRIMSON}"/></linearGradient>'
        f'<radialGradient id="{p}-core" cx=".4" cy=".35" r=".7"><stop offset="0" stop-color="#3d8bff"/><stop offset=".55" stop-color="#16306b"/>'
        f'<stop offset="1" stop-color="#0b1430"/></radialGradient>'
        f'<radialGradient id="{p}-halo"><stop offset="0" stop-color="{BLUE}" stop-opacity=".45"/><stop offset="1" stop-color="{BLUE}" stop-opacity="0"/></radialGradient>'
    )
    rings = []
    for k, (rx, ry, tilt, *_r) in enumerate(ORBITS):
        dash = ' stroke-dasharray="3 7"' if k == 1 else ""
        rings.append(
            f'<ellipse cx="{ocx}" cy="{ocy}" rx="{rx}" ry="{ry}" transform="rotate({tilt} {ocx} {ocy})" '
            f'stroke="url(#{p}-orb)" stroke-opacity=".55" stroke-width="1.3"{dash}/>'
        )
    body.append(f'<g class="{p}-fade"{delay(.2)}>{"".join(rings)}</g>')
    # core
    body.append(
        f'<g class="{p}-fade"{delay(.3)}>'
        f'<circle cx="{ocx}" cy="{ocy}" r="80" fill="url(#{p}-halo)"/>'
        f'<g class="{p}-motion"><circle cx="{ocx}" cy="{ocy}" r="44" stroke="{BLUE}" stroke-width="1.5" fill="none">'
        f'<animate attributeName="r" begin="0s" dur="3s" repeatCount="indefinite" values="44;74"/>'
        f'<animate attributeName="stroke-opacity" begin="0s" dur="3s" repeatCount="indefinite" values=".7;0"/></circle></g>'
        f'<circle cx="{ocx}" cy="{ocy}" r="42" fill="url(#{p}-core)" stroke="url(#{p}-orb)" stroke-width="1.5"/>'
        + d.text(ocx, ocy + 8, "</>", "m7", 22, INK, anchor="middle")
        + "</g>"
    )
    # orbiting pills: sampled positions so depth (scale/opacity) stays in sync
    N = 120
    moving, still = [], []
    period = ORBIT_PERIOD
    for rx, ry, tilt, ring_phase, items in ORBITS:
        tr = math.radians(tilt)
        for j, (slug, label) in enumerate(items):
            phase = math.radians(ring_phase) + 2 * math.pi * j / len(items) + 0.35
            pos, scl, opa = [], [], []
            for s_ in range(N + 1):
                th = phase + 2 * math.pi * s_ / N
                x, y = rx * math.cos(th), ry * math.sin(th)
                X = ocx + x * math.cos(tr) - y * math.sin(tr)
                Y = ocy + x * math.sin(tr) + y * math.cos(tr)
                depth = math.sin(th)  # +1 = front (bottom of ring)
                pos.append(f"{fmt(X)} {fmt(Y)}")
                scl.append(fmt(0.84 + 0.16 * (depth + 1) / 2))
                opa.append(fmt(0.55 + 0.45 * (depth + 1) / 2))
            col = brand_on_dark(slug, SURF2)
            pw = tw(label, "m5", 14) + 46
            badge = (
                f'<rect x="{fmt(-pw / 2)}" y="-16" width="{fmt(pw)}" height="32" rx="16" fill="{SURF2}"/>'
                f'<rect x="{fmt(-pw / 2 + .5)}" y="-15.5" width="{fmt(pw - 1)}" height="31" rx="15.5" stroke="url(#{p}-tile)"/>'
                + d.icon(slug, -pw / 2 + 11, -9, 18, col)
                + d.text(-pw / 2 + 35, 5, label, "m5", 14, INK)
            )
            moving.append(
                f'<g transform="translate({pos[0]})" opacity="{opa[0]}">'
                f'<animateTransform attributeName="transform" type="translate" begin="0s" dur="{period}s" repeatCount="indefinite" values="{";".join(pos)}"/>'
                f'<animate attributeName="opacity" begin="0s" dur="{period}s" repeatCount="indefinite" values="{";".join(opa)}"/>'
                f'<g transform="scale({scl[0]})"><animateTransform attributeName="transform" type="scale" begin="0s" dur="{period}s" '
                f'repeatCount="indefinite" values="{";".join(scl)}"/>{badge}</g></g>'
            )
            still.append(f'<g transform="translate({pos[0]})" opacity="{opa[0]}"><g transform="scale({scl[0]})">{badge}</g></g>')
    body.append(
        f'<g class="{p}-fade"{delay(.5)}><g class="{p}-motion">{"".join(moving)}</g>'
        f'<g class="{p}-static">{"".join(still)}</g></g>'
    )

    # ---- grouped chips
    y = chips_top
    for r in range(2):
        for c in range(3):
            gi = r * 3 + c
            gname, rows = group_layouts[gi]
            gx = gx0 + c * (col_w + col_gap)
            parts = [
                f'<rect x="{gx}" y="{y - 13}" width="6" height="6" rx="1.5" fill="{BLUE if gi % 2 == 0 else CRIMSON}"/>',
                d.text(gx + 14, y - 6, gname, "m7", 13.5, MUTED, ls=1.6),
                f'<path d="M{gx} {y + 6}h{col_w}" stroke="{LINE}"/>',
            ]
            for ri, row in enumerate(rows):
                cy_ = y + 18 + ri * (chip_h + chip_gap)
                for slug, label, xo, cw in row:
                    dot = "#" + ICONS[slug]["hex"] if slug else DIM
                    if slug and contrast(dot, SURF2) < 2.4:
                        dot = INK
                    parts.append(
                        f'<rect x="{fmt(gx + xo)}" y="{fmt(cy_)}" width="{fmt(cw)}" height="{chip_h}" rx="{chip_h / 2}" fill="{SURF2}" stroke="{LINE}"/>'
                        f'<circle cx="{fmt(gx + xo + 15)}" cy="{fmt(cy_ + chip_h / 2)}" r="4" fill="{dot}"/>'
                        + d.text(gx + xo + 25, cy_ + 20, label, "m5", chip_font, INK)
                    )
            body.append(f'<g class="{p}-up"{delay(.7 + gi * .1)}>{"".join(parts)}</g>')
        y += row_heights[r] + 22
    body.append(frame_close(d))
    return d.render("".join(body))


# ======================================================================= ID + DASHBOARD
C128 = (
    "212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 221312 231212 112232 122132 122231 113222 "
    "123122 123221 223211 221132 221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 212123 212321 "
    "232121 111323 131123 131321 112313 132113 132311 211313 231113 231311 112133 112331 132131 113123 113321 133121 "
    "313121 211331 231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 314111 221411 431111 111224 "
    "111422 121124 121421 141122 141221 112214 112412 122114 122411 142112 142211 241211 221114 413111 241112 134111 "
    "111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 214121 412121 111143 111341 131141 114113 "
    "114311 411113 411311 113141 114131 311141 411131 211412 211214 211232"
).split()


def code128b(s: str) -> list[int]:
    vals = [ord(c) - 32 for c in s]
    chk = (104 + sum((i + 1) * v for i, v in enumerate(vals))) % 103
    widths = "".join(C128[v] for v in [104, *vals, chk]) + "2331112"
    return [int(c) for c in widths]


LANG_COLORS = {  # GitHub linguist colours
    "JavaScript": "#f1e05a", "HTML": "#e34c26", "Python": "#3572A5", "CSS": "#663399",
    "TypeScript": "#3178c6", "C++": "#f34b7d", "EJS": "#a91e50",
}
FEATURED = ["OpenPin-Cloud", "YojanaHarvest", "MarkFlow"]


def build_id() -> str:
    W, H = 1000, 740
    prof = SNAP["profile"]
    created = datetime.strptime(prof["created_at"][:10], "%Y-%m-%d")
    d = Doc(
        "idc", W, H,
        "Developer ID and verified GitHub numbers",
        f"A lanyard ID card for Manash Ranjan Mahanand (@ManashR7488) drops in and swings gently. "
        f"Beside it, public GitHub data as of {AS_OF}: {SNAP['public_repo_count']} public repositories, "
        f"{SNAP['public_star_total']} stars across them, {prof['followers']} followers, on GitHub since "
        f"{created:%B %Y}; primary-language split and three featured repositories.",
    )
    p = d.p
    body = [frame_open(d, [(240, 160, 300, 300, "B"), (980, 700, 360, 260, "R"), (720, 40, 360, 160, "B")])]

    # ================= dashboard (drawn first so the swinging card sits above it)
    dx, dw = 452, 500
    dash = [f'<g class="{p}-up"{delay(.2)}>' + kicker(d, dx, 82, "04", "VERIFIED ON GITHUB") + "</g>"]
    dash.append(f'<g class="{p}-up"{delay(.3)}>' + d.text(dx - 2, 128, "By the numbers", "d8", 42, INK, ls=-1) + "</g>")
    dash.append(
        f'<g class="{p}-up"{delay(.4)}>'
        + d.text(dx, 158, f"Source: GitHub API · public data as of {AS_OF}", "m5", 13.5, MUTED)
        + "</g>"
    )
    tiles = [
        ("repo", f"{SNAP['public_repo_count']}", "Public repositories"),
        ("star", f"{SNAP['public_star_total']}", "Stars on public repos"),
        ("users", f"{prof['followers']}", "Followers"),
        ("cal", f"{created:%Y}", f"On GitHub since {created:%b %Y}"),
    ]
    tw_, th_, gap = (dw - 16) / 2, 104, 16
    roll_kf = set()
    for k, (gname, num, label) in enumerate(tiles):
        tx = dx + (k % 2) * (tw_ + gap)
        ty = 182 + (k // 2) * (th_ + gap)
        nsize = 46
        parts = [panel(d, tx, ty, tw_, th_, 18, SURF2, .85), glyph(gname, tx + tw_ - 40, ty + 18, 22, BLUE if k % 2 == 0 else CRIMSON, 1.8)]
        # rolling digits
        clip = d.i(f"roll{k}")
        nx = tx + 22
        base = ty + 60
        d.defs.append(f'<clipPath id="{clip}"><rect x="{fmt(nx - 4)}" y="{fmt(base - nsize * .86)}" width="200" height="{fmt(nsize * 1.06)}"/></clipPath>')
        cols = []
        for j, ch in enumerate(num):
            cw = tw(ch, "d8", nsize, -1)
            steps = 7 + 3 * j
            line = nsize * 1.1
            digs = [(int(ch) - steps + i) % 10 for i in range(steps + 1)]
            strip = "".join(
                d.text(nx + cw / 2, base - (steps - i) * line, str(dg), "d8", nsize, INK, anchor="middle") for i, dg in enumerate(digs)
            )
            dist = fmt(steps * line)
            roll_kf.add(dist)
            cols.append(
                f'<g style="animation:{p}-roll{dist.replace(".", "_")} 1.5s cubic-bezier(.2,.9,.25,1) {fmt(.55 + k * .12 + j * .06)}s both">{strip}</g>'
            )
            nx += cw
        parts.append(f'<g clip-path="url({"#" + clip})">{"".join(cols)}</g>')
        parts.append(d.text(tx + 22, ty + 86, label, "d5", 15.5, MUTED))
        dash.append(f'<g class="{p}-up"{delay(.45 + k * .1)}>{"".join(parts)}</g>')
    for dist in roll_kf:
        d.css.append(f"@keyframes {p}-roll{dist.replace('.', '_')}{{from{{transform:translateY({dist}px)}}to{{transform:translateY(0)}}}}")

    # language split
    ly = 436
    counts = SNAP["primary_language_counts"]
    total = sum(counts.values())
    major = ["JavaScript", "HTML", "Python", "CSS"]
    other = sum(v for k2, v in counts.items() if k2 not in major and k2 != "None")
    segs = [(m, counts.get(m, 0), LANG_COLORS[m]) for m in major] + [("Other", other, "#8d97b0"), ("Not set", counts.get("None", 0), "#3b4767")]
    other_names = [k2 for k2 in counts if k2 not in major and k2 != "None"]
    lang = [d.text(dx, ly, f"PRIMARY LANGUAGE · {total} PUBLIC REPOS", "m7", 13.5, MUTED, ls=1.4)]
    d.defs.append(f'<clipPath id="{p}-bar"><rect x="{dx}" y="{ly + 14}" width="{dw}" height="14" rx="7"/></clipPath>')
    d.css.append(
        f"@keyframes {p}-grow{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}"
        f".{p}-grow{{transform-box:fill-box;transform-origin:0 50%;animation:{p}-grow 1.2s cubic-bezier(.16,1,.3,1) both}}"
    )
    bx = dx
    bar = []
    for k, (name, v, col) in enumerate(segs):
        sw = dw * v / total
        bar.append(f'<rect x="{fmt(bx)}" y="{ly + 14}" width="{fmt(max(sw - 2, 0))}" height="14" fill="{col}" class="{p}-grow"{delay(1.0 + k * .08)}/>')
        bx += sw
    lang.append(f'<rect x="{dx}" y="{ly + 14}" width="{dw}" height="14" rx="7" fill="#ffffff" fill-opacity=".06"/><g clip-path="url(#{p}-bar)">{"".join(bar)}</g>')
    lx, lyy = dx, ly + 54
    for name, v, col in segs:
        s = f"{name} {v}"
        wl = tw(s, "m5", 13) + 20
        if lx + wl > dx + dw:
            lx, lyy = dx, lyy + 22
        lang.append(f'<circle cx="{fmt(lx + 5)}" cy="{lyy - 4.5}" r="4.5" fill="{col}"/>' + d.text(lx + 15, lyy, s, "m5", 13, INK))
        lx += wl + 8
    dash.append(f'<g class="{p}-up"{delay(.9)}>{"".join(lang)}</g>')

    # featured repos
    fy = lyy + 44
    repos = {r["name"]: r for r in SNAP["repos"]}
    rows = [d.text(dx, fy, "FEATURED REPOS", "m7", 13.5, MUTED, ls=1.4)]
    for k, name in enumerate(FEATURED):
        r = repos[name]
        ry = fy + 16 + k * 44
        pushed = datetime.strptime(r["pushed_at"][:10], "%Y-%m-%d")
        lang_c = LANG_COLORS.get(r["language"], "#8d97b0")
        right = f"last push {pushed:%b %Y}"
        rows.append(
            f'<rect x="{dx}" y="{ry}" width="{dw}" height="36" rx="11" fill="{SURF2}" fill-opacity=".8" stroke="{LINE}"/>'
            + glyph("repo", dx + 12, ry + 9, 18, MUTED, 1.7)
            + d.text(dx + 38, ry + 24, name, "d6", 17, INK)
        )
        nx = dx + 38 + tw(name, "d6", 17) + 16
        rows.append(f'<circle cx="{fmt(nx + 5)}" cy="{ry + 18}" r="5" fill="{lang_c}"/>' + d.text(nx + 15, ry + 23, r["language"], "m5", 13, MUTED))
        nx += 15 + tw(r["language"], "m5", 13) + 14
        rows.append(f'<path d="{star_path(nx + 6, ry + 18, 6.5)}" fill="#f5c451"/>' + d.text(nx + 17, ry + 23, str(r["stargazers_count"]), "m5", 13, MUTED))
        rows.append(d.text(dx + dw - 14, ry + 23, right, "m5", 13, DIM, anchor="end"))
    dash.append(f'<g class="{p}-up"{delay(1.1)}>{"".join(rows)}</g>')
    if fy + 16 + 3 * 44 > H - 24:
        raise SystemExit(f"dashboard overflows: {fy + 16 + 3 * 44}")
    body.append("".join(dash))

    # ================= lanyard + card
    px, py = 246, -140  # pendulum pivot (above the frame)
    cx0, cy0, cw, ch = 96, 244, 300, 466
    d.defs.append(
        f'<linearGradient id="{p}-metal" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f6f8fc"/><stop offset=".35" stop-color="#a5adbf"/>'
        f'<stop offset=".55" stop-color="#eef1f7"/><stop offset="1" stop-color="#6b7488"/></linearGradient>'
        f'<linearGradient id="{p}-metalh" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#7b8498"/><stop offset=".45" stop-color="#f4f6fb"/>'
        f'<stop offset="1" stop-color="#8a93a6"/></linearGradient>'
        f'<linearGradient id="{p}-strap" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#b3172d"/><stop offset="1" stop-color="{CRIMSON}"/></linearGradient>'
        f'<linearGradient id="{p}-cardbg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#121c36"/><stop offset="1" stop-color="#0a1020"/></linearGradient>'
        f'<linearGradient id="{p}-band" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="{CRIMSON}"/></linearGradient>'
        f'<radialGradient id="{p}-photobg" cx=".5" cy=".38" r=".75"><stop offset="0" stop-color="#2a4f9e"/><stop offset=".65" stop-color="#14224a"/>'
        f'<stop offset="1" stop-color="#3a1426"/></radialGradient>'
        f'<linearGradient id="{p}-holo" x1="0" y1="0" x2="1" y2="1" gradientUnits="objectBoundingBox">'
        f'<stop offset="0" stop-color="#7ef3ff"/><stop offset=".25" stop-color="#b892ff"/><stop offset=".5" stop-color="#ff8fd8"/>'
        f'<stop offset=".75" stop-color="#ffe18a"/><stop offset="1" stop-color="#7ef3ff"/>'
        f'<animateTransform attributeName="gradientTransform" type="translate" begin="0s" dur="5s" repeatCount="indefinite" values="-.5 -.5;.5 .5;-.5 -.5"/></linearGradient>'
        f'<linearGradient id="{p}-sweep" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        f'<stop offset=".5" stop-color="#fff" stop-opacity=".22"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        f'<clipPath id="{p}-cardclip"><rect x="{cx0}" y="{cy0}" width="{cw}" height="{ch}" rx="24"/></clipPath>'
        f'<radialGradient id="{p}-cardshadow"><stop offset="0" stop-color="#000" stop-opacity=".5"/><stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>'
    )
    card = []
    # straps (two ribbons converging on the ring), printed text along one of them
    ring_x, ring_y = px, 186
    for sx in (-78, 78):
        top = px + sx
        poly = f"M{top - 13} -160 L{top + 13} -160 L{ring_x + (6 if sx > 0 else -6) + 6} {ring_y - 6} L{ring_x + (6 if sx > 0 else -6) - 6} {ring_y - 6}Z"
        card.append(f'<path d="{poly}" fill="url(#{p}-strap)"/>')
        card.append(f'<path d="M{top - 13} -160 L{ring_x + (6 if sx > 0 else -6) - 6} {ring_y - 6}" stroke="#ff8796" stroke-opacity=".5" stroke-width="1"/>')
    strap_path = d.i("strapline")
    d.defs.append(f'<path id="{strap_path}" d="M{px - 78} -150 L{ring_x - 6} {ring_y - 10}"/>')
    d.reg("m7", "MANASHR7488 •")
    card.append(
        f'<text class="{p}-m7" font-size="10.5" fill="#ffffff" fill-opacity=".85" letter-spacing="2.4">'
        f'<textPath href="#{strap_path}" startOffset="158">MANASHR7488 •</textPath></text>'
    )
    # ring + lobster clasp + clip
    card.append(
        f'<circle cx="{ring_x}" cy="{ring_y}" r="10" stroke="url(#{p}-metalh)" stroke-width="4"/>'
        f'<path d="M{ring_x - 7} {ring_y + 10} C{ring_x - 13} {ring_y + 26} {ring_x - 9} {ring_y + 40} {ring_x} {ring_y + 44} '
        f'C{ring_x + 9} {ring_y + 40} {ring_x + 13} {ring_y + 26} {ring_x + 7} {ring_y + 10}Z" fill="url(#{p}-metalh)" stroke="#5c6478" stroke-width=".8"/>'
        f'<path d="M{ring_x + 4} {ring_y + 16} C{ring_x + 8} {ring_y + 24} {ring_x + 7} {ring_y + 32} {ring_x + 2} {ring_y + 38}" stroke="#4b5366" stroke-width="1.2"/>'
        f'<rect x="{ring_x - 4}" y="{ring_y + 42}" width="8" height="12" rx="2" fill="url(#{p}-metalh)"/>'
    )
    # card shadow
    card.append(f'<ellipse cx="{cx0 + cw / 2 + 10}" cy="{cy0 + ch / 2 + 16}" rx="{cw / 2 + 20}" ry="{ch / 2 + 10}" fill="url(#{p}-cardshadow)"/>')
    # card body
    band_h = 64
    card.append(
        f'<rect x="{cx0}" y="{cy0}" width="{cw}" height="{ch}" rx="24" fill="url(#{p}-cardbg)"/>'
        f'<g clip-path="url(#{p}-cardclip)">'
        f'<rect x="{cx0}" y="{cy0}" width="{cw}" height="{band_h}" fill="url(#{p}-band)"/>'
        f'<rect x="{cx0}" y="{cy0 + band_h}" width="{cw}" height="{ch - band_h}" fill="url(#{p}-dots)"/>'
        f'<path d="M{cx0} {cy0 + band_h}h{cw}" stroke="#ffffff" stroke-opacity=".25"/>'
        f"</g>"
        f'<rect x="{cx0 + .5}" y="{cy0 + .5}" width="{cw - 1}" height="{ch - 1}" rx="23.5" stroke="url(#{p}-hair)" stroke-opacity=".9"/>'
        # slot
        f'<rect x="{px - 30}" y="{cy0 + 12}" width="60" height="11" rx="5.5" fill="{NAVY}" stroke="#000" stroke-opacity=".4"/>'
    )
    card.append(d.text(cx0 + 20, cy0 + 48, "DEV ID", "m7", 13, "#ffffff", ls=3))
    card.append(d.icon("github", cx0 + cw - 40, cy0 + 30, 22, "#ffffff"))
    # clip that bites the card through the slot
    card.append(
        f'<rect x="{px - 16}" y="{ring_y + 52}" width="32" height="{cy0 + 22 - ring_y - 52}" rx="4" fill="url(#{p}-metalh)" stroke="#5c6478" stroke-width=".8"/>'
        f'<circle cx="{px}" cy="{cy0 + 6}" r="2.6" fill="#5c6478"/>'
    )
    # photo window – the real portrait, cropped to head & shoulders, alpha intact
    phx, phy, phw, phh = cx0 + 62, cy0 + band_h + 22, 176, 206
    src = load_rgba("id.png")
    crop = src.crop((170, 70, 916, 70 + round(746 * phh / phw)))
    crop = resize_rgba(crop, 352)
    d.defs.append(f'<clipPath id="{p}-photo"><rect x="{phx}" y="{phy}" width="{phw}" height="{phh}" rx="18"/></clipPath>')
    card.append(
        f'<g clip-path="url(#{p}-photo)"><rect x="{phx}" y="{phy}" width="{phw}" height="{phh}" fill="url(#{p}-photobg)"/>'
        f'<rect x="{phx}" y="{phy}" width="{phw}" height="{phh}" fill="url(#{p}-dots)"/>'
        f'<image href="{png_uri(crop)}" x="{phx}" y="{phy}" width="{phw}" height="{fmt(phw * crop.height / crop.width)}" preserveAspectRatio="xMidYMin meet"/></g>'
        f'<rect x="{phx + .5}" y="{phy + .5}" width="{phw - 1}" height="{phh - 1}" rx="17.5" stroke="url(#{p}-hair)"/>'
    )
    # holographic foil sticker
    fx, fy_ = phx + phw - 26, phy + phh - 26
    card.append(
        f'<g><rect x="{fx}" y="{fy_}" width="44" height="44" rx="12" fill="url(#{p}-holo)" fill-opacity=".92" stroke="#ffffff" stroke-opacity=".6"/>'
        + d.text(fx + 22, fy_ + 28, "MR", "d8", 16, "#1b1640", anchor="middle", ls=-.4)
        + "</g>"
    )
    # name + role
    ny = phy + phh + 40
    card.append(d.text(cx0 + cw / 2, ny, "MANASH RANJAN", "d8", 25, INK, anchor="middle", ls=.4))
    card.append(d.text(cx0 + cw / 2, ny + 28, "MAHANAND", "d8", 25, INK, anchor="middle", ls=.4))
    card.append(d.text(cx0 + cw / 2, ny + 55, "FORWARD DEPLOYED ENGINEER", "m7", 13, BLUE, anchor="middle", ls=.8))
    for s, size, font in [("MANASH RANJAN", 25, "d8"), ("FORWARD DEPLOYED ENGINEER", 13, "m7")]:
        if tw(s, font, size, .6) > cw - 28:
            raise SystemExit(f"card text too wide: {s}")
    # barcode (real Code 128-B of the GitHub handle)
    mods = code128b("ManashR7488")
    mw = 1.5
    bw_total = sum(mods) * mw
    bx0 = cx0 + (cw - bw_total) / 2
    byy = ny + 70
    path, x, bar_on = [], bx0, True
    for m in mods:
        if bar_on:
            path.append(f"M{fmt(x)} {byy}h{fmt(m * mw)}v32h-{fmt(m * mw)}z")
        x += m * mw
        bar_on = not bar_on
    card.append(f'<path d="{"".join(path)}" fill="{INK}" fill-opacity=".92"/>')
    card.append(d.text(cx0 + cw / 2, byy + 50, "@ManashR7488", "m5", 13, MUTED, anchor="middle", ls=1))
    if byy + 50 > cy0 + ch - 10:
        raise SystemExit("card content overflows")
    # light sweep across the card
    card.append(
        f'<g clip-path="url(#{p}-cardclip)"><g><rect x="{cx0 - 160}" y="{cy0 - 40}" width="110" height="{ch + 80}" fill="url(#{p}-sweep)" transform="skewX(-14)"/>'
        f'<animateTransform attributeName="transform" type="translate" begin="0s" dur="6s" repeatCount="indefinite" '
        f'values="0 0;0 0;560 0;560 0" keyTimes="0;.55;.8;1"/></g></g>'
    )

    # pendulum: drop (CSS), damped settle + steady ±1.7° swing (SMIL, both begin at 0 s)
    P = 2.4  # full swing period
    half = P / 2
    targets = [None, 1.7, -3.8, 3.1, -2.6, 2.2, -1.9, 1.7]  # combined angle at each half-period extreme
    steady = [(-1.7 if k % 2 == 0 else 1.7) for k in range(len(targets))]
    dvals = [0.0, 0.0] + [targets[k] - steady[k] for k in range(2, len(targets))]
    dvals[-1] = 0.0
    times = [k * half for k in range(len(targets))]
    dur = times[-1]
    spl = ";".join([".45 0 .55 1"] * (len(dvals) - 1))
    settle = (
        f'<animateTransform attributeName="transform" type="rotate" begin="0s" dur="{fmt(dur)}s" fill="freeze" calcMode="spline" '
        f'keySplines="{spl}" keyTimes="{keytimes(times, dur)}" values="{";".join(f"{fmt(v)} {px} {py}" for v in dvals)}"/>'
    )
    swing = (
        f'<animateTransform attributeName="transform" type="rotate" begin="0s" dur="{fmt(P)}s" repeatCount="indefinite" calcMode="spline" '
        f'keySplines=".45 0 .55 1;.45 0 .55 1" keyTimes="0;.5;1" values="-1.7 {px} {py};1.7 {px} {py};-1.7 {px} {py}"/>'
    )
    d.css.append(
        f"@keyframes {p}-drop{{0%{{transform:translateY(-820px);animation-timing-function:cubic-bezier(.55,0,.9,.5)}}"
        f"62%{{transform:translateY(16px);animation-timing-function:cubic-bezier(.3,0,.5,1)}}"
        f"78%{{transform:translateY(-7px);animation-timing-function:cubic-bezier(.5,0,.5,1)}}"
        f"90%{{transform:translateY(2px)}}100%{{transform:translateY(0)}}}}"
        f".{p}-drop{{animation:{p}-drop 1.25s .05s both}}"
    )
    # card artwork defined once and instanced twice (animated + reduced-motion)
    d.defs.append(f'<g id="{p}-lanyard">{"".join(card)}</g>')
    body.append(
        f'<g class="{p}-drop"><g class="{p}-motion"><g>{settle}<g>{swing}<use href="#{p}-lanyard"/></g></g></g>'
        f'<g class="{p}-static"><use href="#{p}-lanyard"/></g></g>'
    )
    body.append(frame_close(d))
    return d.render("".join(body))


# ======================================================================= CONNECT
SOCIALS = [
    ("linkedin", "LinkedIn", "in/manash-ranjan-mahanand-r27488"),
    ("github", "GitHub", "github.com/ManashR7488"),
    ("youtube", "YouTube", "youtube.com/@manashr2"),
    ("instagram", "Instagram", "instagram.com/manash_r_6452"),
    ("gmail", "Email", "mahanandmanash91@gmail.com"),
]


def build_connect() -> str:
    W, H = 1000, 640
    d = Doc(
        "cnx", W, H,
        "Let's connect",
        "Manash points toward five contact cards: " + "; ".join(f"{n} — {h}" for _, n, h in SOCIALS)
        + ". Clickable versions of these links are in the README text below the image.",
    )
    p = d.p
    body = [frame_open(d, [(220, 250, 300, 330, "B"), (980, 640, 380, 260, "R"), (300, 640, 300, 120, "R")])]

    # figure
    fig = resize_rgba(load_rgba("right_pointing.png"), 480)
    fh = 588
    fw = fh * fig.width / fig.height
    fx, fy = 22, H - fh - 26
    d.defs.append(
        f'<radialGradient id="{p}-floor"><stop offset="0" stop-color="{BLUE}" stop-opacity=".45"/><stop offset=".6" stop-color="#000" stop-opacity=".35"/>'
        f'<stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>'
        f'<linearGradient id="{p}-ring" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="{CRIMSON}"/></linearGradient>'
    )
    body.append(
        f'<g class="{p}-fade"{delay(.1)}><circle cx="{fmt(fx + fw * .45)}" cy="{fmt(fy + fh * .32)}" r="150" stroke="url(#{p}-ring)" stroke-opacity=".5" stroke-width="1.5"/>'
        f'<circle cx="{fmt(fx + fw * .45)}" cy="{fmt(fy + fh * .32)}" r="176" stroke="#fff" stroke-opacity=".07" stroke-dasharray="2 9"/></g>'
        f'<ellipse cx="{fmt(fx + fw * .43)}" cy="{fmt(fy + fh - 6)}" rx="150" ry="16" fill="url(#{p}-floor)"/>'
        f'<g class="{p}-up"{delay(.2)}><image href="{png_uri(fig)}" x="{fmt(fx)}" y="{fy}" width="{fmt(fw)}" height="{fh}"/></g>'
    )
    # fingertip of the pointing hand (measured on the source image: 862,343 of 1024x1536)
    tipx, tipy = fx + fw * 862 / 1024, fy + fh * 343 / 1536
    chev = []
    for k in range(3):
        x = tipx + 22 + k * 18
        chev.append(
            f'<path d="M{fmt(x)} {fmt(tipy - 9)}l9 9-9 9" stroke="url(#{p}-ring)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" opacity=".35">'
            f'<animate attributeName="opacity" begin="0s" dur="1.5s" repeatCount="indefinite" values=".25;.25;1;.25;.25" '
            f'keyTimes="0;{fmt(k * .2)};{fmt(k * .2 + .2)};{fmt(k * .2 + .4)};1"/></path>'
        )
    still_chev = "".join(
        f'<path d="M{fmt(tipx + 22 + k * 18)} {fmt(tipy - 9)}l9 9-9 9" stroke="url(#{p}-ring)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" opacity="{[.4, .7, 1][k]}"/>'
        for k in range(3)
    )
    body.append(f'<g class="{p}-fade"{delay(1.0)}><g class="{p}-motion">{"".join(chev)}</g><g class="{p}-static">{still_chev}</g></g>')

    # heading
    rx0, rw = 470, 486
    body.append(f'<g class="{p}-up"{delay(.25)}>' + kicker(d, rx0, 76, "05", "CONNECT") + "</g>")
    body.append(f'<g class="{p}-up"{delay(.35)}>' + d.text(rx0 - 2, 128, "Let’s connect", "d8", 50, INK, ls=-1.2) + "</g>")
    sub = "Clickable links are right below this card."
    body.append(f'<g class="{p}-up"{delay(.45)}>' + d.text(rx0, 162, sub, "d4", 17.5, MUTED) + "</g>")

    # social cards
    ch, gap, top = 68, 20, 194
    for k, (slug, name, handle) in enumerate(SOCIALS):
        y = top + k * (ch + gap)
        hexc = "#" + ICONS[slug]["hex"]
        tile_fill, glyph_fill = hexc, "#ffffff"
        if slug == "github":
            tile_fill, glyph_fill = INK, hexc
        if tw(handle, "m5", 14.5) > rw - 76 - 64:
            raise SystemExit(f"handle too wide: {handle}")
        ax_, ay_ = rx0 + rw - 36, y + ch / 2
        nudge_t = [0, k * .12 + .1, k * .12 + .35, k * .12 + .6, 3.0]
        arrow = (
            f'<circle cx="{fmt(ax_)}" cy="{fmt(ay_)}" r="19" fill="{NAVY}" stroke="url(#{p}-tile)"/>'
            f'<g class="{p}-motion"><g><animateTransform attributeName="transform" type="translate" begin="0s" dur="3s" repeatCount="indefinite" '
            f'calcMode="spline" keySplines=".4 0 .2 1;.4 0 .2 1;.4 0 .2 1;.4 0 .2 1" values="0 0;0 0;7 0;0 0;0 0" keyTimes="{keytimes(nudge_t, 3.0)}"/>'
            + glyph("arrow", ax_ - 10, ay_ - 10, 20, INK, 2.1)
            + "</g></g>"
            f'<g class="{p}-static">' + glyph("arrow", ax_ - 10, ay_ - 10, 20, INK, 2.1) + "</g>"
        )
        body.append(
            f'<g class="{p}-left"{delay(.55 + k * .12)}>'
            + panel(d, rx0, y, rw, ch, 18, SURF2, .9)
            + f'<rect x="{rx0 + 12}" y="{y + 11}" width="46" height="46" rx="13" fill="{tile_fill}"/>'
            + d.icon(slug, rx0 + 23, y + 22, 24, glyph_fill)
            + d.text(rx0 + 74, y + 30, name, "d6", 20, INK)
            + d.text(rx0 + 74, y + 52, handle, "m5", 14.5, MUTED)
            + arrow
            + "</g>"
        )
    if top + 5 * ch + 4 * gap > H - 24:
        raise SystemExit("cards overflow")
    body.append(frame_close(d))
    return d.render("".join(body))


BUILDERS = {
    "hero.svg": build_hero,
    "about-life.svg": build_about,
    "stack.svg": build_stack,
    "id-dashboard.svg": build_id,
    "connect.svg": build_connect,
}

if __name__ == "__main__":
    import sys

    want = sys.argv[1:] or list(BUILDERS)
    for name in want:
        svg = BUILDERS[name]()
        (ASSETS / name).write_text(svg, encoding="utf-8")
        print(f"{name:18s} {len(svg.encode()) / 1024:8.1f} KB")
