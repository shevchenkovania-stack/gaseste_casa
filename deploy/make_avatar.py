from PIL import Image, ImageDraw

S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# background circle (Telegram crops to circle)
d.ellipse((0, 0, S, S), fill=(15, 118, 110, 255))

# subtle inner ring
d.ellipse((34, 34, S - 34, S - 34), outline=(255, 255, 255, 60), width=6)

# house
white = (255, 255, 255, 255)
roof = [(110, 268), (256, 138), (402, 268)]
d.polygon(roof, fill=white)
d.rectangle((158, 262, 354, 404), fill=white)
# door
d.rectangle((232, 314, 280, 404), fill=(15, 118, 110, 255))
# window
d.rectangle((186, 292, 224, 330), fill=(15, 118, 110, 255))
# magnifier (search) lower-right
d.ellipse((300, 300, 380, 380), outline=white, width=16)
d.line((368, 368, 408, 408), fill=white, width=20)

img.save("/root/avatar.png")
print("avatar written")
