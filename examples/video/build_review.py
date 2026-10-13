"""Build effects-first 180s review with native pixel text and a segmented overlay.

Inputs are recorded RGB/PNG evidence and existing character assets. This editor
never generates animation or changes color/normal/material assets.
"""
import argparse,json,subprocess,hashlib,shutil,math
from pathlib import Path
from PIL import Image,ImageDraw
from pixel_overlay import text,text_width,audit_glyphs,header,progress_overlay,FONT_PATH,cardinal_caption

HERE=Path(__file__).resolve().parent

def run(args):subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y']+list(map(str,args)),check=True)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def call_to_action(base,frame):
    im=base.copy()
    if frame<12:return im
    elapsed=min(1.0,(frame-12)/18)
    message='觉得有用记得一键三连喔'
    layer=Image.new('RGBA',im.size,(0,0,0,0))
    y=620+round(24*(1-elapsed)**2)-round(5*math.sin(elapsed*math.pi))
    text(layer,((1920-text_width(message,48))//2,y),message,48,'#efc873')
    layer.putalpha(layer.getchannel('A').point(lambda value:round(value*elapsed)))
    im=Image.alpha_composite(im.convert('RGBA'),layer).convert('RGB')
    d=ImageDraw.Draw(im)
    for i,(label,color) in enumerate(zip(['点赞','投币','收藏'],['#efc873','#8cbfff','#73dfc5'])):
        local=frame-(32+i*14)
        if local<0:continue
        progress=min(1.0,local/10)
        x=560+i*400
        top=744+round(12*(1-progress)**2)-round(5*math.sin(progress*math.pi))
        d.rectangle((x-140,top,x+140,top+84),fill='#1b2d33',outline=color,width=3)
        text(im,(x-text_width(label,36)//2,top+23),label,36,color)
        d.rectangle((x-140,top+88,x-140+round(280*progress),top+93),fill=color)
    return im

class Review:
    def __init__(self,root,out,cardinal_capture=None,reuse_review=None,orbit_review=None):
        self.root=root;self.out=out;out.mkdir(parents=True,exist_ok=True)
        self.cardinal_capture=cardinal_capture or root/'.local/hd2d-demo/build/ancient-canal/jade-cardinal-v10'
        self.reuse_review=reuse_review
        self.orbit_review=orbit_review
        self.orbit_selection=json.loads((orbit_review/'shot-recipe.json').read_text()) if orbit_review else None
        if reuse_review:
            prior=json.loads((reuse_review/'edit-recipe.json').read_text())
            if prior['font']['sha256']!=digest(FONT_PATH):raise ValueError('Cached review font changed')
            self.cached_timeline=prior['parts']
        self.cards=json.loads((HERE/'cards.json').read_text())
        self.timeline=json.loads((HERE/'timeline.json').read_text());self.parts=self.timeline['parts']
        assert sum(p['frames'] for p in self.parts)==5400
        capture_recipe=json.loads((self.cardinal_capture/'shot-recipe.json').read_text())
        cardinal_frames=len(capture_recipe['trajectory'])
        if cardinal_frames%4:raise ValueError('Four-direction capture must have equal frame counts')
        for part in self.parts:
            if part['id']=='cardinal':part['frames']=cardinal_frames
        self.total_frames=sum(p['frames'] for p in self.parts)
        self.lighting_selection=capture_recipe.get('saved_selection')
        self.cardinal_playback_scale=capture_recipe.get('params',{}).get('playback_scale',capture_recipe.get('playback_scale',.46875))
        if reuse_review and [(p['id'],p['frames']) for p in self.parts if p['id']!='cardinal']!=[(p['id'],p['frames']) for p in self.cached_timeline if p['id']!='cardinal']:raise ValueError('Cached non-cardinal review timeline changed')
        self.sources=[]

    def prepare_images(self):
        color=self.root/'output/jade-traveler-owned-surfaces-v8/character/right/frames/00013.png'
        Image.open(color).save(self.out/'topic-color.png')
        clay=self.root/'.local/hd2d-demo/build/ancient-canal/owned-surfaces-v8-normal-render/clay-sweep-right-key-13.png'
        Image.open(clay).crop((730,145,1190,945)).save(self.out/'topic-clay.png')
        # Rebuild contact captions with the selected font; source sprites stay intact.
        for name,folder,indices,label in [
            ('failure-original',self.root/'runs/up-001-extracted-v2/pixel-256',[0,8,27],'原始帧'),
            ('failure-revised',self.root/'output/jade-traveler-owned-surfaces-v8/character/up',[0,13,26],'选择帧')]:
            manifest=json.loads((folder/'animation.json').read_text());im=Image.new('RGB',(768,292),'#101b20')
            for column,i in enumerate(indices):
                image=Image.open(folder/manifest['frames'][i]['path']).convert('RGBA')
                im.paste(image,(column*256,0),image);text(im,(column*256+12,264),f'{label} {i:02d}',24,'#a6d3b8')
            im.save(self.out/(name+'.png'))
        self.cards['failure']['images']=[str(self.out/'failure-original.png'),str(self.out/'failure-revised.png')]
        self.cards['topic']['images']=[str(self.out/'topic-color.png'),str(self.out/'topic-clay.png')]

    def card(self,name):
        spec=self.cards[name];im=Image.new('RGB',(1920,1080),'#101b20');d=ImageDraw.Draw(im)
        d.rectangle((80,74,154,82),fill='#a6d3b8')
        title_size=60 if text_width(spec['title'],60)<1760 else 48
        text(im,(80,126),spec['title'],title_size)
        if spec.get("subtitle"):text(im,(80,215),spec["subtitle"],24,"#e7ba72")
        if spec.get('source'):
            assert text_width(spec['source'],24)<1730
            text(im,(80,258),spec['source'],24,'#a6d3b8')
        y=306 if spec.get('source') else 270
        for line in spec['lines']:
            is_command=line.startswith(('python','.venv','h3-character','.runtime','simple scheduler','https://'))
            size=24 if is_command else 36
            assert text_width(line,size)<1730,line
            text(im,(80,y),line,size);y+=63
        if spec['images']:
            cell=1720//len(spec['images'])
            image_top=max(475,y+16)
            image_bottom=828 if spec.get('image_notes') else 925
            for i,path in enumerate(spec['images']):
                path=Path(path);path=path if path.is_absolute() else self.root/path
                source=Image.open(path).convert('RGBA');source.thumbnail((cell-30,image_bottom-image_top),Image.Resampling.NEAREST)
                x=80+i*cell+(cell-source.width)//2
                im.paste(source,(x,image_top+(image_bottom-image_top-source.height)//2),source)
                if i<len(spec['labels']):text(im,(80+i*cell+20,854 if spec.get('image_notes') else 946),spec['labels'][i],24,'#a6d3b8')
                if spec.get('image_notes'):
                    for row,note in enumerate(spec['image_notes'][i]):
                        assert text_width(note,24)<cell-30,note
                        text(im,(80+i*cell+20,890+row*30),note,24)
        path=self.out/(spec['asset_name']+'.png');im.save(path);return path

    def still(self,name,frames):
        path=self.card(name);target=self.out/(name+'.mkv')
        if name=='ending':
            base=Image.open(path).convert('RGB')
            args=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pixel_format','rgb24','-video_size','1920x1080','-framerate','30','-i','pipe:0','-frames:v',str(frames),'-an','-c:v','libx264rgb','-crf','0','-preset','fast','-pix_fmt','rgb24',str(target)]
            proc=subprocess.Popen(args,stdin=subprocess.PIPE)
            try:
                for frame in range(frames):
                    image=call_to_action(base,frame)
                    if frame in [12,36,90]:image.save(self.out/f'ending-animation-{frame:03d}.png')
                    proc.stdin.write(image.tobytes())
                proc.stdin.close()
                if proc.wait():raise RuntimeError('Call-to-action animation encode failed')
            except Exception:
                proc.kill();proc.wait();raise
            self.sources.append(dict(id=name,path=target.name,frames=frames,source=str(path.relative_to(self.root)),kind='native pixel-text call-to-action animation'))
            return target
        if self.reuse_review and (self.reuse_review/path.name).exists() and digest(path)==digest(self.reuse_review/path.name):
            shutil.copy2(self.reuse_review/target.name,target)
            self.sources.append(dict(id=name,path=target.name,frames=frames,source=str(path.relative_to(self.root)),kind='verified identical pixel-font card'))
            return target
        run(['-loop','1','-framerate','30','-i',path,'-frames:v',frames,'-an','-c:v','libx264rgb','-crf','0','-preset','fast','-pix_fmt','rgb24',target])
        self.sources.append(dict(id=name,path=target.name,frames=frames,source=str(path.relative_to(self.root)),kind='pixel-font-card'))
        return target

    def shot(self,name,frames):
        if name=='cardinal':
            raw=self.cardinal_capture
            recipe=json.loads((raw/'shot-recipe.json').read_text())
            assert len(recipe['trajectory'])==frames and all(r['animation_frame']==r['clay_animation_frame'] for r in recipe['trajectory'])
            start=recipe.get('source_start_frame',len(list(raw.glob('raw*.png')))-(frames+15))
            assert start>=15
            inputs=['-framerate','30','-start_number',start,'-i',raw/'raw%08d.png']
            step=frames//4;checkpoints=[step*i for i in range(4)]
            dump(self.out/'cardinal-source.json',dict(recipe=recipe,source_start_frame=start,PNG_frames=frames))
        else:
            raw=self.root/'output/clean-frame-review-v8'
            if name=='orbit' and self.orbit_review:
                evidence=json.loads((self.orbit_review/'validation.json').read_text())
                assert evidence['frames']==frames and evidence['latest_assets_hashes_match']
                source=self.orbit_review/'orbit-base-rgb-lossless.mkv'
                dump(self.out/'orbit-source.json',dict(source=str(source.relative_to(self.root)),validation=evidence,recipe=self.orbit_selection,user_approved_replacement=True))
            elif self.reuse_review:source=self.reuse_review/(name+'.mkv')
            else:source=raw/('night-roam-10s-rgb-lossless.mkv' if name=='roam' else 'light-orbit-36s-rgb-lossless.mkv')
            inputs=['-i',source]
            checkpoints=[0] if name=='roam' else [0,180,360,540,720,900]
            step=frames if name=='roam' else 180
        filters=['[0:v]format=rgb24[base]'];previous='base'
        for idx,start in enumerate(checkpoints,1):
            plate=self.out/f'{name}-header-{start:04d}.png';header(name,start,step if name=='cardinal' else 180,self.cardinal_playback_scale).save(plate)
            inputs+=['-loop','1','-framerate','30','-i',plate]
            output='header'+str(idx)
            filters.append(f"[{previous}][{idx}:v]overlay=0:0:format=rgb:enable='gte(n,{start})*lt(n,{start+step})'[{output}]");previous=output
        if name=='orbit':
            plate=Image.new('RGBA',(1920,1080),(0,0,0,0));d=ImageDraw.Draw(plate)
            for rect,xy,value in [((1250,160,1810,207),(1268,171),'脸颈 / 鼻部 · 表面归属'),((1250,620,1810,667),(1268,631),'银饰 / 腰饰 · 逐帧镜面')]:
                d.rectangle(rect,fill=(15,24,30,255));text(plate,xy,value,24)
            path=self.out/'orbit-pixel-captions.png';plate.save(path)
            inputs+=['-loop','1','-framerate','30','-i',path]
            filters.append(f'[{previous}][{len(checkpoints)+1}:v]overlay=0:0:format=rgb[final]');previous='final'
        target=self.out/(name+'.mkv')
        run(inputs+['-filter_complex',';'.join(filters),'-map',f'[{previous}]','-frames:v',frames,'-r','30','-an','-c:v','libx264rgb','-crf','0','-preset','fast','-pix_fmt','rgb24',target])
        self.sources.append(dict(id=name,path=target.name,frames=frames,kind='actual-GPU-shot',original_animation_regenerated=False,typography_only_overlay=True))
        if name=='cardinal':
            direction_parts=[dict(id='light-'+str(i),title=name,frames=frames//4) for i,name in enumerate(['上方照射','下方照射','左侧照射','右侧照射'])]
            standalone_name=f'four-direction-lighting-{frames/30:g}s'
            standalone=self.overlay(target,self.out/(standalone_name+'-rgb-lossless.mkv'),direction_parts)
            run(['-i',standalone,'-c:v','libx264','-crf','16','-preset','fast','-pix_fmt','yuv420p','-movflags','+faststart',self.out/(standalone_name+'.mp4')])
        return target

    def overlay(self,base,target=None,parts=None):
        selected_parts=self.parts if parts is None else parts
        frame_count=sum(p['frames'] for p in selected_parts)
        target=target or self.out/'technical-demo-3min-rgb-lossless.mkv'
        args=['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(base),'-f','rawvideo','-pixel_format','rgba','-video_size','1920x92','-framerate','30','-i','pipe:0','-filter_complex','[0:v]format=rgb24[body];[body][1:v]overlay=0:988:format=rgb[final]','-map','[final]','-frames:v',str(frame_count),'-r','30','-an','-c:v','libx264rgb','-crf','0','-preset','fast','-pix_fmt','rgb24',str(target)]
        with (self.out/'overlay-encode.log').open('w') as log:
            proc=subprocess.Popen(args,stdin=subprocess.PIPE,stderr=log)
            try:
                for frame in range(frame_count):
                    image=progress_overlay(selected_parts,frame)
                    if parts is None and frame in [0,299,300,1019,1020,2099,2100,5399]:image.save(self.out/f'progress-{frame:04d}.png')
                    proc.stdin.write(image.tobytes())
                proc.stdin.close();status=proc.wait()
            except Exception:
                proc.kill();proc.wait();raise
        if status:raise RuntimeError((self.out/'overlay-encode.log').read_text())
        return target

    def build(self):
        self.prepare_images();strings=[]
        for s in self.cards.values():strings += [s['title']]+s['lines']+s['labels']+([s['subtitle']] if s.get('subtitle') else [])+([s['source']] if s.get('source') else [])+[note for notes in s.get('image_notes',[]) for note in notes]
        strings += [p['source'] for p in self.parts if p.get('source')]+[p['subtitle'] for p in self.parts if p.get('subtitle')]
        strings += [p['title'] for p in self.parts]+['上方照射','下方照射','左侧照射','右侧照射','原色 · 逐帧法线与银饰','灰材质 · 观察形体受光','单一白光 / 同步侧面慢步','青绿少女 · 动态光照与银饰','青绿少女 · 夜晚漫游','脸颈 / 鼻部 · 表面归属','银饰 / 腰饰 · 逐帧镜面','仅冷光','仅暖光','冷暖混合','一端 → 头顶掠过 → 另一端','中距离 / 10 秒','低位正面扫光','第 1 轮','00:00 / 03:00','原始帧 00','选择帧 13']
        strings.append(cardinal_caption(self.cardinal_playback_scale))
        strings += ['觉得有用记得一键三连喔','点赞','投币','收藏']
        strings += [p.get('description','') for p in self.parts]+[p.get('short_title',p['title']) for p in self.parts]+['四向·右','环绕·冷','环绕·暖','环绕·混','来源：Godot Forward+ / 夜晚漫游','来源：Godot Forward+ / 冷暖环绕光']
        glyphs=audit_glyphs(strings);clips=[]
        for part in self.parts:
            ident=part['id'];frames=part['frames']
            if ident in ['roam','cardinal','orbit']:clips.append(self.shot(ident,frames))
            elif ident=='extract':clips += [self.still('extract',240),self.still('animation',120)]
            elif ident=='normals':clips += [self.still('normals',240),self.still('materials',180)]
            else:clips.append(self.still(ident,frames))
            print('BUILT_PART',ident,flush=True)
        concat=self.out/'timeline.ffconcat';concat.write_text('ffconcat version 1.0\n'+''.join(f"file '{p.name}'\n" for p in clips))
        base=self.out/'effects-first-base-rgb.mkv';run(['-f','concat','-safe','0','-i',concat,'-c','copy',base])
        review_name='technical-demo-3min' if self.total_frames==5400 else f'technical-demo-{self.total_frames/30:g}s'
        master=self.overlay(base,self.out/(review_name+'-rgb-lossless.mkv'));proxy=self.out/(review_name+'-review.mp4')
        run(['-i',master,'-an','-c:v','libx264','-crf','16','-preset','fast','-pix_fmt','yuv420p','-movflags','+faststart',proxy])
        starts=0;rows=[]
        for part in self.parts:
            rows.append(dict(part,start_frame=starts,end_frame=starts+part['frames'],start_seconds=starts/30,end_seconds=(starts+part['frames'])/30));starts+=part['frames']
        dump(self.out/'edit-recipe.json',dict(fps=30,size=[1920,1080],duration=self.total_frames/30,effects_first=True,effects_end_seconds=sum(p["frames"] for p in self.parts[:3])/30,lighting_selection=self.lighting_selection,orbit_selection=self.orbit_selection,parts=rows,sources=self.sources,card_annotations={key:{field:value for field,value in spec.items() if field in ["subtitle","source","lines","labels","image_notes"]} for key,spec in self.cards.items()},call_to_action=dict(text="觉得有用记得一键三连喔",actions=["点赞","投币","收藏"],animation="pixel text slides in; actions light sequentially",start_seconds=(self.total_frames-120+12)/30,end_seconds=self.total_frames/30),font=dict(path='fonts/'+FONT_PATH.name,sha256=digest(FONT_PATH),source='jibijibi-game playable theme',native_size=12,title_size=60,body_size=36,command_and_caption_size=24,shot_title_size=36,progress_title_size=24,integer_nearest_scaling=True,glyph_count=glyphs,no_fallback=True),direction_highlights=dict(words=['上方','下方','左侧','右侧'],colors=['#f5c96b','#8cbfff','#73dfc5','#ffa18e'],underline=True,also_in_current_part=True),progress=dict(type='mint gold gray chapter boxes with short titles inside',overlay_rect=[0,988,1920,92],track_rect=[48,1026,1824,52],segments=13,current_part_title_above=False,labels_inside_segments=True,explanation_above=True,palette=dict(past="#a6d3b8",current="#e7ba72",future="#314047"),label_font_size=24,minimum_label_padding=24,segment_sizes="minimum text width plus duration-weighted free space"),master=master.name,preview=proxy.name,artistic_review='pending',copy_review='pending'))
        print('BUILT_REVIEW',proxy,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=HERE.parents[1]);parser.add_argument('--output',type=Path);parser.add_argument('--cardinal-capture',type=Path);parser.add_argument('--reuse-review',type=Path);parser.add_argument('--orbit-review',type=Path)
    a=parser.parse_args();root=a.root.resolve();out=(a.output or root/'output/video-technical-v10-review').resolve();Review(root,out,a.cardinal_capture.resolve() if a.cardinal_capture else None,a.reuse_review.resolve() if a.reuse_review else None,a.orbit_review.resolve() if a.orbit_review else None).build()
