from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUTPUT = Path("/home/ubuntu/corrector-ai/performance/copie_test_pilote.png")


def load_font(size: int):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


image = Image.new("RGB", (1600, 1100), "white")
draw = ImageDraw.Draw(image)
title_font = load_font(42)
body_font = load_font(32)
small_font = load_font(26)

lines = [
    ("Copie synthétique de pilote — Sciences", title_font),
    ("Nom : Élève Test          Classe : 4ème A", small_font),
    ("", body_font),
    ("Exercice 1 — Photosynthèse (10 points)", body_font),
    ("La photosynthèse permet aux plantes de produire de la matière", body_font),
    ("organique grâce à la lumière, à l'eau et au dioxyde de carbone.", body_font),
    ("Elle libère du dioxygène.", body_font),
    ("", body_font),
    ("Exercice 2 — Calcul (10 points)", body_font),
    ("2 + 2 = 4.", body_font),
]

y = 85
for line, font in lines:
    draw.text((100, y), line, font=font, fill="black")
    y += 74 if line else 34

draw.line((100, 65, 1500, 65), fill="black", width=3)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
image.save(OUTPUT, "PNG")
print(OUTPUT)
