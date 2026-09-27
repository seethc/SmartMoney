"""Render the geometric icon.svg design as dependency-free Pillow PWA icons."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1] / 'frontend'
scale = 8
image = Image.new('RGB', (192*scale, 192*scale), '#245344')
draw = ImageDraw.Draw(image)
def box(values):
    return tuple(round(x*scale) for x in values)
draw.ellipse(box((101,29,149,77)), fill='#f3c86b')
draw.rounded_rectangle(box((37,67,155,152)), radius=23*scale, fill='#d8f0dd')
points = [(int((67+58*t/100)*scale), int((110+62*(t/100)*(1-t/100))*scale)) for t in range(101)]
draw.line(points, fill='#245344', width=9*scale, joint='curve')
for x,y,r in [(67,110,4.5),(125,110,4.5),(69,94,5),(123,94,5)]:
    draw.ellipse(box((x-r,y-r,x+r,y+r)), fill='#245344')
for size in (192,512):
    image.resize((size,size), Image.Resampling.LANCZOS).save(root / f'icon-{size}.png')
