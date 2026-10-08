import re
from PIL import Image, ImageDraw, ImageFont
Font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 16)
CellW, CellH = 10, 20
Base = [(0,0,0),(205,49,49),(13,188,121),(229,229,16),(36,114,200),(188,63,188),(17,168,205),(229,229,229),(102,102,102),(241,76,76),(35,209,139),(245,245,67),(59,142,234),(214,112,214),(41,184,219),(255,255,255)]
def Xterm(n):
    if n < 16: return Base[n]
    if n < 232:
        n -= 16; l = (0,95,135,175,215,255)
        return (l[n//36], l[(n//6)%6], l[n%6])
    v = 8 + 10*(n-232); return (v,v,v)
Token = re.compile(r"\x1b\[([0-9;?]*)([A-Za-z])")
DefFg, DefBg = (204,204,204), (16,16,16)
def Parse(text):
    rows = []
    for line in text.split("\n"):
        fg, bg, bold = DefFg, DefBg, False
        cells = []; pos = 0
        for m in Token.finditer(line):
            for ch in line[pos:m.start()]: cells.append((ch, fg, bg, bold))
            pos = m.end()
            if m.group(2) != "m": continue
            codes = [int(c) if c else 0 for c in m.group(1).split(";")]
            i = 0
            while i < len(codes):
                c = codes[i]
                if c == 0: fg, bg, bold = DefFg, DefBg, False
                elif c == 1: bold = True
                elif c == 22: bold = False
                elif c == 39: fg = DefFg
                elif c == 49: bg = DefBg
                elif 30 <= c <= 37: fg = Base[c-30]
                elif 90 <= c <= 97: fg = Base[c-90+8]
                elif 40 <= c <= 47: bg = Base[c-40]
                elif c in (38, 48) and i+2 < len(codes) and codes[i+1] == 5:
                    (fg if c == 38 else bg).__class__
                    col = Xterm(codes[i+2])
                    if c == 38: fg = col
                    else: bg = col
                    i += 2
                i += 1
        for ch in line[pos:]: cells.append((ch, fg, bg, bold))
        rows.append(cells)
    return rows
def Render(text, path, cols=110, rows=50):
    grid = Parse(text)
    img = Image.new("RGB", (cols*CellW, rows*CellH), DefBg)
    d = ImageDraw.Draw(img)
    for y, cells in enumerate(grid[:rows]):
        for x, (ch, fg, bg, bold) in enumerate(cells[:cols]):
            if bg != DefBg: d.rectangle([x*CellW, y*CellH, (x+1)*CellW-1, (y+1)*CellH-1], fill=bg)
            if ch != " ":
                col = tuple(min(255, int(v*1.25)) for v in fg) if bold else fg
                d.text((x*CellW, y*CellH), ch, font=Font, fill=col)
    img.save(path)
