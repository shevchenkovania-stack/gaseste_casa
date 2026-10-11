# Brand logo v2: house with a keyhole - "Găsește Casa" = find your house (and the key to it).
# Drawn at 4x with LANCZOS downscale so every edge is smooth at 100 px. Full-bleed gradient:
# Telegram crops both bot avatars and channel photos to a circle, so nothing important may sit
# near a corner. No text: names are rendered by Telegram itself, an icon must survive alone.
from PIL import Image, ImageDraw

S = 4096
TEAL_TOP = (13, 148, 136)      # #0D9488
TEAL_BOT = (15, 94, 89)        # #0F5E59
WHITE = (255, 255, 255, 255)

img = Image.new("RGBA", (S, S))
d = ImageDraw.Draw(img)

# vertical gradient, full bleed
for y in range(S):
    t = y / S
    c = tuple(int(TEAL_TOP[i] + (TEAL_BOT[i] - TEAL_TOP[i]) * t) for i in range(3))
    d.line([(0, y), (S, y)], fill=c + (255,))

# chimney (behind the roof line, slightly right of the slope)
d.rounded_rectangle((0.600 * S, 0.230 * S, 0.665 * S, 0.360 * S), radius=0.012 * S, fill=WHITE)

# roof: thick stroked polyline with round joints = soft modern gable
W = int(0.048 * S)
pts = [(0.175 * S, 0.465 * S), (0.5 * S, 0.175 * S), (0.825 * S, 0.465 * S)]
d.line(pts + [pts[0]], fill=WHITE, width=W, joint="curve")

# body: bold rounded square
d.rounded_rectangle((0.275 * S, 0.430 * S, 0.725 * S, 0.815 * S), radius=0.035 * S, fill=WHITE)

# keyhole: circle + wedge, punched through in the mid-gradient colour
mid = tuple(int((TEAL_TOP[i] + TEAL_BOT[i]) / 2) for i in range(3)) + (255,)
cx, cy, r = 0.5 * S, 0.575 * S, 0.052 * S
d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=mid)
d.polygon([(cx, cy - 0.005 * S), (cx - 0.048 * S, 0.735 * S), (cx + 0.048 * S, 0.735 * S)], fill=mid)

out = img.resize((1024, 1024), Image.LANCZOS).convert("RGB")
out.save("deploy/logo.png", optimize=True)
print("logo written")
