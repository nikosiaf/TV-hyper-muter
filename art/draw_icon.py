import sys, os
from PIL import Image, ImageDraw, ImageFont
S = 1024
INK = (38, 34, 58, 255)
RED = (225, 40, 50, 255)
W = 26  # outline width

def tv(size):
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # shadow
    d.ellipse((190, 880, 834, 960), fill=(0, 0, 0, 45))
    # legs
    for x in (330, 694):
        d.rounded_rectangle((x - 40, 800, x + 40, 905), 30, fill=(255, 176, 59, 255), outline=INK, width=W)
    # antennas
    d.line((512, 250, 360, 80), fill=INK, width=W + 6)
    d.line((512, 250, 680, 95), fill=INK, width=W + 6)
    for cx, cy, col in ((360, 80, (255, 92, 92, 255)), (680, 95, (92, 200, 255, 255))):
        d.ellipse((cx - 46, cy - 46, cx + 46, cy + 46), fill=col, outline=INK, width=W)
    # body
    d.rounded_rectangle((110, 230, 914, 840), 120, fill=(255, 176, 59, 255), outline=INK, width=W)
    d.rounded_rectangle((140, 262, 884, 420), 90, fill=(255, 205, 120, 255))  # highlight
    # screen
    d.rounded_rectangle((175, 300, 735, 775), 80, fill=(232, 247, 255, 255), outline=INK, width=W)
    d.arc((215, 335, 435, 555), 190, 255, fill=(255, 255, 255, 255), width=26)  # glare
    # knobs
    for cy in (380, 520):
        d.ellipse((770, cy - 50, 870, cy + 50), fill=(124, 92, 255, 255), outline=INK, width=W)
        d.line((820, cy - 30, 820, cy), fill=INK, width=18)
    for cy in (640, 700):
        d.rounded_rectangle((768, cy - 14, 872, cy + 14), 14, fill=INK)
    # speaker on screen
    d.polygon([(300, 470), (370, 470), (470, 390), (470, 690), (370, 610), (300, 610)],
              fill=(60, 72, 110, 255), outline=INK)
    d.line([(300, 470), (370, 470), (470, 390), (470, 690), (370, 610), (300, 610), (300, 470)],
           fill=INK, width=20, joint="curve")
    # red mute X with round ends: ink layer first, then red on top
    segs = (((525, 465), (665, 615)), ((665, 465), (525, 615)))
    for col, w in ((INK, 66), ((240, 60, 70, 255), 34)):
        for a, b in segs:
            d.line((a, b), fill=col, width=w)
            for x, y in (a, b):
                d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=col)
    return im.resize((size, size), Image.LANCZOS)

out = sys.argv[1]
tv(128).save(f"{out}/icon.png")
# logo: icon + name, ~250x100
big = Image.new("RGBA", (1000, 400), (0, 0, 0, 0))
big.alpha_composite(tv(380), (0, 10))
d = ImageDraw.Draw(big)
font, small = ImageFont.load_default(118), ImageFont.load_default(118)
for txt, y, fnt in (("TV hyper", 60, font), ("muter", 200, small)):
    d.text((405, y), txt, font=fnt, fill=RED, stroke_width=3, stroke_fill=RED)
big.resize((500, 200), Image.LANCZOS).save(f"{out}/logo.png")  # 2x the usual 250x100
tv(512).save(f"{out}/preview.png")
