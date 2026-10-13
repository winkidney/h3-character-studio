"""Create editable cover layouts using the project pixel font and pixel assets.

Python draws typography as SVG paths only. Sharp handles image placement and
nearest-neighbor scaling, then exports PNGs from the editable SVG layouts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from pixel_overlay import audit_glyphs, text_mask, text_width

ROOT = Path(__file__).resolve().parents[2]
STRINGS = [
    '有手就能做！', 'HD2D', '动态光影', '角色动画制作', '全流程解析',
    '（其实是有 AI 就能做）', '从角色设定到游戏实装',
    '青绿少女', '角色设定', '颜色', '法线', '银饰蒙版', '冷光', '暖光',
]


def rect(x, y, w, h, color, extra=''):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}" {extra}/>'


def text(value, x, y, size, color, shadow=True):
    assert size % 12 == 0
    mask = text_mask(value, 1)
    path = []
    for row in range(mask.height):
        col = 0
        while col < mask.width:
            if not mask.getpixel((col, row)):
                col += 1
                continue
            start = col
            while col < mask.width and mask.getpixel((col, row)):
                col += 1
            path.append(f'M{start},{row}h{col-start}v1h-{col-start}z')
    scale = size // 12
    glyphs = f'<path d="{"".join(path)}"/>'
    result = ''
    if shadow:
        result += f'<g transform="translate({x+scale},{y+scale}) scale({scale})" fill="#07141b">{glyphs}</g>'
    result += f'<g data-text="{value}" transform="translate({x},{y}) scale({scale})" fill="{color}">{glyphs}</g>'
    return result


def image(name, x, y, w, h):
    return f'<image data-asset="{name}" x="{x}" y="{y}" width="{w}" height="{h}" href="ASSET:{name}:{w}:{h}"/>'


def laugh(x, y, unit=6):
    # Hand-drawn pixel badge represents the user's laughing emoji without a
    # different emoji font. All lettering uses the actual game TTF.
    parts = [rect(x+unit, y, 10*unit, 12*unit, '#e7ba72'), rect(x, y+unit, 12*unit, 10*unit, '#e7ba72')]
    cells = [(2,3),(3,4),(2,5),(8,3),(7,4),(8,5),(3,7),(4,8),(5,8),(6,8),(7,7)]
    parts += [rect(x+cx*unit,y+cy*unit,unit,unit,'#132832') for cx,cy in cells]
    return ''.join(parts)


def layout(w, h, compact=False):
    mint, gold, white = '#a6d3b8', '#e7ba72', '#f1eee2'
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<title>有手就能做！HD2D 动态光影角色动画制作全流程解析</title>',
        '<desc>青绿少女像素角色封面。文字由 Z Labs Pixel12px 游戏字体转换为像素路径。</desc>',
        '<defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#0b1924"/><stop offset="1" stop-color="#182e38"/></linearGradient></defs>',
        rect(0,0,w,h,'url(#bg)')]
    board_x = 940 if not compact else 800
    # Concept-sheet grid and measuring ticks sit behind the original design.
    for x in range(board_x,w,48):
        parts.append(f'<path d="M{x} 0V{h}" stroke="#29414a" stroke-width="1" opacity=".5"/>')
    for y in range(0,h,48):
        parts.append(f'<path d="M{board_x} {y}H{w}" stroke="#29414a" stroke-width="1" opacity=".5"/>')
    parts.append(f'<path d="M{board_x+50} 76h80 M{board_x+50} 76v80 M{w-64} 76h-80 M{w-64} 76v80 M{w-64} {h-66}h-80 M{w-64} {h-66}v-80" fill="none" stroke="#638a89" stroke-width="3"/>')
    for y in range(182,h-100,24):
        parts.append(rect(w-70,y,18 if y%48==38 else 8,2,'#567575'))
    # Character artwork is a separate raster asset; no synthetic lettering.
    hero_h = h - 48
    hero_w = round(hero_h*1095/1437)
    hero_x = 748 if compact else 1080
    parts.append(image('hero',hero_x,16,hero_w,hero_h))
    parts.append(text('青绿少女',w-168,104,24,mint))
    parts.append(text('角色设定',w-168,140,24,'#90aca6',False))
    swatches=['#463634','#8b6450','#e7d9b9','#769184','#27545c','#9b4944','#b9c1bb']
    for i,c in enumerate(swatches):
        parts.append(rect(w-72,356+i*38,24,24,c))
    # Warm and cool design marks underline the dynamic lighting theme.
    parts.append(f'<path d="M{board_x+86} 270h72l-18 -18 M{board_x+158} 270l-18 18" fill="none" stroke="#87bbd9" stroke-width="4"/>')
    parts.append(text('冷光',board_x+68,302,24,'#8cbfff',False))
    parts.append(f'<path d="M{w-90} 800h-60l18 -18 M{w-150} 800l18 18" fill="none" stroke="{gold}" stroke-width="4"/>')
    parts.append(text('暖光',w-166,834,24,gold,False))
    # Left title column, with deliberately different title and body sizes.
    x = 80
    heading_size = 96 if compact else 108
    parts.append(laugh(x,90,6))
    parts.append(text('有手就能做！',x+100,90,heading_size,gold))
    parts.append(text('HD2D',x,260,168 if not compact else 144,white))
    parts.append(text('动态光影',x+(360 if not compact else 314),278 if not compact else 272,108 if not compact else 96,mint))
    parts.append(text('角色动画制作',x,428 if not compact else 412,120 if not compact else 108,white))
    tag_y = 594 if not compact else 566
    tag_size = 72
    parts.append(rect(x-8,tag_y-12,504,106,'#e7ba72'))
    parts.append(rect(x-8,tag_y+94,16,12,'#a57f4c'))
    parts.append(text('全流程解析',x+32,tag_y+4,tag_size,'#142731',False))
    parts.append(text('（其实是有 AI 就能做）',x-12,tag_y+142,48,mint))
    panel_y = 828 if not compact else 844
    panel_w, panel_h = (236,190) if not compact else (218,226)
    for i,(name,label) in enumerate([('color','颜色'),('normal','法线'),('metal','银饰蒙版')]):
        px=x+i*(panel_w+22)
        parts.append(rect(px,panel_y,panel_w,panel_h,'#132630', 'stroke="#4c686c" stroke-width="2"'))
        parts.append(rect(px,panel_y,8,panel_h,mint if i!=1 else '#919acf'))
        side=144 if not compact else 168
        ix=px+(panel_w-side)//2;iy=panel_y+8
        if name=='metal':
            # Display the actual mask in warm gold over a faint color silhouette.
            # This is a labeled visualization, not a changed production mask.
            parts.append('<g opacity=".28">'+image('color',ix,iy,side,side)+'</g>')
            parts.append('<defs><mask id="metal-preview" mask-type="luminance">'+image('metal',ix,iy,side,side)+'</mask></defs>')
            parts.append(rect(ix,iy,side,side,'#ffe4a1','mask="url(#metal-preview)"'))
        else:
            parts.append(image(name,ix,iy,side,side))
        parts.append(text(label,px+(panel_w-text_width(label,24))//2,panel_y+panel_h-34,24,'#c3d1c6',False))
    if compact:
        parts.append(text('从角色设定到游戏实装',x,1126,36,'#9bb8b1'))
    # Thin colored edge unifies both ratios with the finished video's palette.
    parts.extend([rect(0,0,w,8,mint),rect(0,h-8,w,8,gold),'</svg>'])
    return '\n'.join(parts)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--hero',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    output=args.output.resolve();assets=output/'assets';assets.mkdir(parents=True,exist_ok=True)
    source=ROOT/'output/jade-traveler-owned-surfaces-v8'
    paths={'hero':args.hero.resolve(),
        'color':source/'character/right/frames/00011.png',
        'normal':source/'normals/right/frames/00011.png',
        'metal':source/'normals/right/masks/00011.png',
        'font':Path(__file__).parent/'fonts/zlabs-pixel-12px-m-cn.ttf'}
    receipts={}
    for name,path in paths.items():
        dst=assets/(name+path.suffix)
        shutil.copyfile(path,dst)
        receipts[name]={'source':str(path),'file':str(dst.relative_to(output)),
            'sha256':hashlib.sha256(dst.read_bytes()).hexdigest()}
    glyphs=audit_glyphs(STRINGS)
    for name,w,h,compact in [('16x9',1920,1080,False),('4x3',1600,1200,True)]:
        (output/f'cover-{name}.layout.svg').write_text(layout(w,h,compact))
    (output/'receipt.json').write_text(json.dumps({'assets':receipts,'glyph_count':glyphs,
        'font_method':'12px monochrome masks to integer-scaled SVG paths',
        'illustration':'built-in image_gen pixel detail enhancement from approved v8 sprite; smooth anime draft rejected',
        'cover_sizes':{'16x9':[1920,1080],'4x3':[1600,1200]},
        'small_material_previews':'actual same-pose v8 color, normal and per-frame metal-mask assets'},ensure_ascii=False,indent=2)+'\n')
    print(output)


if __name__=='__main__':
    main()
