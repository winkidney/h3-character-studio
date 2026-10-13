"""Pixel typography and frame-indexed segmented video progress overlay."""
from functools import lru_cache
from pathlib import Path
import math
from PIL import Image,ImageDraw,ImageFont

FONT_PATH=Path(__file__).parent/'fonts/zlabs-pixel-12px-m-cn.ttf'
NATIVE=ImageFont.truetype(str(FONT_PATH),12)
DIRECTION_WORDS=['上方','下方','左侧','右侧']
DIRECTION_COLORS=['#f5c96b','#8cbfff','#73dfc5','#ffa18e']

@lru_cache(maxsize=2048)
def text_mask(text,scale=2):
    box=NATIVE.getbbox(text)
    width=max(1,math.ceil(NATIVE.getlength(text)))
    height=max(1,box[3]-box[1])
    mask=Image.new('1',(width,height))
    ImageDraw.Draw(mask).text((0,-box[1]),text,font=NATIVE,fill=1)
    return mask.convert('L').resize((width*scale,height*scale),Image.Resampling.NEAREST)

def text(image,xy,value,size=24,color='#f0eee5'):
    if size%12:raise ValueError('Pixel font size must be a multiple of native12px')
    mask=text_mask(value,size//12)
    image.paste(color,xy,mask)
    return mask.width,mask.height

def text_width(value,size=24):return text_mask(value,size//12).width

def audit_glyphs(strings):
    unknown=NATIVE.getmask(chr(0x10ffff));signature=(unknown.size,bytes(unknown))
    chars=set(''.join(strings));missing=[]
    for ch in sorted(chars):
        if ch.isspace():continue
        glyph=NATIVE.getmask(ch)
        if (glyph.size,bytes(glyph))==signature:missing.append(ch)
    if missing:raise ValueError('Pixel font missing glyphs: '+repr(missing))
    return len(chars)

SHORT_LABELS={'roam':'漫游','cardinal':'四向','orbit':'环绕','design':'设计','masters':'母版','install':'环境','workflow':'H3','failure':'背面','extract':'抠图','normals':'法线','topic':'体积','ownership':'修复','ending':'片尾'}

def short_label(part):
    if part.get('id','').startswith('light-'):
        return DIRECTION_WORDS[int(part['id'].split('-')[-1])]
    return part.get('short_title',SHORT_LABELS.get(part.get('id'),part['title']))

def progress_layout(parts):
    total=sum(p['frames'] for p in parts)
    minimum=[]
    for part in parts:
        label=short_label(part)
        widest=label+'·混' if part.get('id')=='orbit' else (label+'·右' if part.get('id')=='cardinal' else label)
        minimum.append(text_width(widest,24)+24)
    extra=1824-sum(minimum)
    if extra<0:raise ValueError('Progress labels do not fit the frame')
    bounds=[48];accumulated=0
    for part,width in zip(parts,minimum):
        accumulated+=part['frames']
        assigned=round(extra*accumulated/total)-round(extra*(accumulated-part['frames'])/total)
        bounds.append(bounds[-1]+width+assigned)
    assert bounds[-1]==1872
    return bounds

def progress_overlay(parts,frame,fps=30):
    total=sum(p['frames'] for p in parts)
    if not 0<=frame<total:raise ValueError('Frame outside timeline')
    starts=[0]
    for p in parts:starts.append(starts[-1]+p['frames'])
    current=next(i for i in range(len(parts)) if starts[i]<=frame<starts[i+1])
    local=frame-starts[current];part=parts[current]
    strip=Image.new('RGBA',(1920,92),(12,23,28,228));d=ImageDraw.Draw(strip)
    d.line((0,0,1919,0),fill='#3e5b5d',width=2)
    note=part.get('description',part['title'])
    if part.get('id')=='cardinal':
        direction=min(3,local//(part['frames']//4))
        prefix='原色与灰材质对照 · '
        text(strip,(48,7),prefix,24,'#a6b5af')
        text(strip,(48+text_width(prefix),7),DIRECTION_WORDS[direction]+'照射',24,DIRECTION_COLORS[direction])
    elif part.get('id')=='orbit':
        phase=min(2,local//(part['frames']//3))
        name=['仅冷光','仅暖光','冷暖混合'][phase]
        color=['#8cbfff','#f5c96b','#73dfc5'][phase]
        text(strip,(48,7),name,24,color)
        detail='低位正面扫光' if local%(part['frames']//3)<part['frames']//6 else '从一端经头顶返回另一端'
        text(strip,(48+text_width(name),7),' · 1× 行走 · '+detail,24,'#a6b5af')
    elif part.get('id','').startswith('light-'):
        text(strip,(48,7),part['title'],24,DIRECTION_COLORS[current])
    else:text(strip,(48,7),note,24,'#a6b5af')
    elapsed=frame//fps;duration=total//fps
    timer=f'{elapsed//60:02d}:{elapsed%60:02d} / {duration//60:02d}:{duration%60:02d}'
    text(strip,(1872-text_width(timer),7),timer,24,'#a6b5af')
    bounds=progress_layout(parts)
    for i,item in enumerate(parts):
        left,right=bounds[i:i+2];width=right-left
        d.rectangle((left,38,right-1,89),fill='#314047')
        fill=0
        if i<current:d.rectangle((left+2,40,right-3,87),fill='#a6d3b8')
        elif i==current:
            fill=round((width-4)*(frame-starts[i]+1)/item['frames'])
            if fill:d.rectangle((left+2,40,left+1+fill,87),fill='#e7ba72')
        label=short_label(item)
        if i==current and item.get('id')=='cardinal':label+='·'+DIRECTION_WORDS[min(3,local//(item['frames']//4))][0]
        elif i==current and item.get('id')=='orbit':label+='·'+['冷','暖','混'][min(2,local//(item['frames']//3))]
        assert text_width(label,24)<=width-24
        x=(width-text_width(label,24))//2;y=(52-text_mask(label,2).height)//2
        plate=Image.new('RGBA',(width,52),(0,0,0,0))
        text(plate,(x,y),label,24,'#0c171c' if i<current else '#f0eee5')
        if i==current and fill:
            dark=Image.new('RGBA',(width,52),(0,0,0,0));text(dark,(x,y),label,24,'#0c171c')
            plate.alpha_composite(dark.crop((0,0,min(width,2+fill),52)),(0,0))
        strip.alpha_composite(plate,(left,38))
    d=ImageDraw.Draw(strip)
    d.rectangle((48,38,1871,89),outline='#a6b5af',width=2)
    for x in bounds[1:-1]:d.line((x,38,x,89),fill='#a6b5af',width=2)
    return strip

def cardinal_caption(playback_scale):
    if playback_scale==.46875:return '单一白光 / 同步侧面慢步'
    return f'单一白光 / 同步侧面行走 · {playback_scale:g}×'

def header(shot,frame=0,direction_frames=180,playback_scale=.46875):
    height=150 if shot=='cardinal' else 116
    im=Image.new('RGBA',(1920,height),(15,24,30,255))
    if shot=='cardinal':
        names=['上方照射','下方照射','左侧照射','右侧照射'];index=min(3,frame//direction_frames)
        prefix='四向光照 · '
        x=48+text_width(prefix,36)
        text(im,(48,30),prefix,36)
        text(im,(x,30),DIRECTION_WORDS[index],36,DIRECTION_COLORS[index])
        text(im,(x+text_width(DIRECTION_WORDS[index],36),30),'照射',36)
        ImageDraw.Draw(im).rectangle((x,76,x+text_width(DIRECTION_WORDS[index],36)-1,79),fill=DIRECTION_COLORS[index])
        text(im,(1120,36),cardinal_caption(playback_scale),24,'#a6d3b8')
        text(im,(1120,78),'来源：Godot Forward+',24,'#a6b5af')
        text(im,(48,102),'原色 · 逐帧法线与银饰',24)
        text(im,(1008,102),'灰材质 · 观察形体受光',24)
    elif shot=='orbit':
        index=min(2,frame//360);names=['仅冷光','仅暖光','冷暖混合']
        text(im,(48,30),'青绿少女 · 动态光照与银饰',36)
        text(im,(1480,28),names[index]+f' · 第 {index+1} 轮',24)
        detail='低位正面扫光' if frame%360<180 else '一端 → 头顶掠过 → 另一端'
        text(im,(1310,78),detail,24,'#a6d3b8')
        text(im,(48,78),'来源：Godot Forward+ / 冷暖环绕光',24,'#a6b5af')
    elif shot=='roam':
        text(im,(48,30),'青绿少女 · 夜晚漫游',36)
        text(im,(1480,36),'中距离 / 10 秒',24,'#a6d3b8')
        text(im,(48,78),'来源：Godot Forward+ / 夜晚漫游',24,'#a6b5af')
    else:raise ValueError('Unknown shot')
    return im
