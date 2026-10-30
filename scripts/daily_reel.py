"""Build and publish one explicitly approved narrated carousel adaptation.

Durable state is committed BEFORE each non-idempotent publish request. An
uncertain response must be reconciled manually; reruns never blindly republish.
"""
import asyncio, datetime as dt, hashlib, json, math, os, re, subprocess, sys, time
import urllib.request, urllib.parse, urllib.error, wave
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path('.')
REPO='Avi-2024/business-jalwa'
API='https://graph.facebook.com/v23.0/'
def run(*args): return subprocess.check_output(args, text=True).strip()
def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def tighten_narration(source, destination):
    """Shorten only measured quiet pauses; leave spoken samples/speed unchanged."""
    pcm=destination.with_suffix('.decoded.wav')
    run('ffmpeg','-y','-loglevel','error','-i',str(source),'-ar','44100','-ac','1','-c:a','pcm_s16le',str(pcm))
    scan=subprocess.run(['ffmpeg','-hide_banner','-i',str(pcm),'-af',
                         'silencedetect=noise=-45dB:d=0.45','-f','null','-'],
                        capture_output=True,text=True,check=True)
    with wave.open(str(pcm),'rb') as audio:
        rate=audio.getframerate();count=audio.getnframes()
        data=audio.readframes(count);params=audio.getparams()
    duration=count/rate
    pauses=[];start=None
    for kind,value in re.findall(r'silence_(start|end):\s*([\d.]+)',scan.stderr):
        if kind=='start': start=float(value)
        elif start is not None:
            pauses.append((start,min(float(value),duration)));start=None
    if start is not None: pauses.append((start,duration))
    cuts=[]
    for a,b in pauses:
        if a<=.02: left,right=0,max(0,b-.06)
        elif b>=duration-.04: left,right=min(duration,a+.08),duration
        else: left,right=a+.11,b-.11
        if right>left: cuts.append((round(left*rate),round(right*rate)))
    pieces=[];cursor=0
    for left,right in cuts:
        pieces.append(data[cursor*2:left*2]);cursor=right
    pieces.append(data[cursor*2:]);output=b''.join(pieces)
    if len(output)<rate: raise ValueError('Narration is empty or too short after pause cleanup')
    with wave.open(str(destination),'wb') as audio:
        audio.setparams(params);audio.writeframes(output)
    pcm.unlink()
    trimmed=len(output)/2/rate
    print(f'Narration pauses: {duration:.2f}s -> {trimmed:.2f}s; {len(cuts)} long gaps shortened',flush=True)
    return trimmed
def checkpoint(paths):
    subprocess.run(['git','add','--',*map(str,paths)],check=True)
    if subprocess.run(['git','diff','--cached','--quiet']).returncode==0: return
    run('git','commit','-m','Save daily Reel assets and publishing checkpoint')
    run('git','pull','--rebase','origin','main')
    run('git','push','origin','HEAD:main')
def call(path,token,params=None,method='GET',headers=None):
    url=path if path.startswith('https://') else API+path
    data=None
    if params and method=='GET': url+='?'+urllib.parse.urlencode(params)
    elif params: data=urllib.parse.urlencode(params).encode()
    h={'Authorization':'Bearer '+token,**(headers or {})}
    req=urllib.request.Request(url,data=data,headers=h,method=method)
    try:
        with urllib.request.urlopen(req,timeout=90) as response: result=json.load(response)
    except urllib.error.HTTPError as e:
        try: code=json.loads(e.read()).get('error',{}).get('code','unknown')
        except Exception: code='unknown'
        raise RuntimeError(f'Meta API HTTP {e.code}; code {code}') from None
    if result.get('error'): raise RuntimeError('Meta API error; review account permissions')
    return result
def instagram(path,token,params=None,method='GET'):
    return call('https://graph.instagram.com/v23.0/'+path,token,params,method)
def select(date,posts,plan):
    matches=[p for p in posts if p.get('publish_at','')[:10]==date and p.get('id')==plan.get('source_post_id')]
    if len(matches)!=1: raise ValueError('Expected exactly one matching source carousel')
    p=matches[0]
    if p.get('manual_approved') is not True or plan.get('approved') is not True: raise ValueError('Approval missing')
    if len(p.get('image_urls',[]))!=5 or len(plan.get('scenes',[]))!=5: raise ValueError('Exactly five scenes required')
    for url,s in zip(p['image_urls'],plan['scenes']):
        if not url.startswith('https://raw.githubusercontent.com/'+REPO+'/main/assets/'): raise ValueError('Unexpected image host/path')
        if not all(isinstance(s.get(k),str) and s[k].strip() for k in ('narration','question','answer')): raise ValueError('Incomplete scene')
    return p
def wrap_card_text(draw,text,font,max_width):
    lines=[]
    for paragraph in text.splitlines():
        words=paragraph.split();line=''
        for word in words:
            trial=(line+' '+word).strip()
            if line and draw.textlength(trial,font=font)>max_width:
                lines.append(line);line=word
            else: line=trial
        if line: lines.append(line)
    return lines
def card(text,background,foreground,height,border=None):
    from PIL import Image,ImageDraw,ImageFont
    font='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    image=Image.new('RGBA',(650,height),(0,0,0,0));draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((0,0,649,height-1),radius=20,fill=background,outline=border,width=2 if border else 1)
    for size in range(24,17,-1):
        face=ImageFont.truetype(font,size)
        lines=wrap_card_text(draw,text,face,605)
        spacing=5;line_height=size+spacing
        if lines and len(lines)*line_height<=height-24 and all(draw.textlength(line,font=face)<=605 for line in lines): break
    else: raise ValueError('Shorten scene overlay text')
    draw.multiline_text((22,(height-len(lines)*line_height+spacing)//2),'\n'.join(lines),font=face,fill=foreground,spacing=spacing)
    return image
def render_scene(art,scene,index,duration,narration,clip):
    """Animate only small movements so the original educational slide stays legible."""
    from PIL import Image,ImageDraw,ImageFont
    green=(23,62,48);rust=(180,72,32);cream=(250,245,229)
    font='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    title=ImageFont.truetype(font,32);small=ImageFont.truetype(font,17)
    question=card(scene['question'],green,(255,255,250),78)
    answer=card(scene['answer'],(255,255,250),green,125,border=(211,194,162))
    def reveal(card_image,amount):
        opacity=round(max(0,min(1,amount))*10)
        if not opacity:return None
        if opacity==10:return card_image
        alpha=card_image.getchannel('A').point(lambda value:value*opacity//10)
        result=card_image.copy();result.putalpha(alpha)
        return result
    question_levels=[reveal(question,j/10) for j in range(11)]
    answer_levels=[reveal(answer,j/10) for j in range(11)]
    base=Image.new('RGB',(720,1280),cream);base_draw=ImageDraw.Draw(base)
    base_draw.rectangle((0,0,720,135),fill=green)
    base_draw.text((35,34),'BUSINESS JALWA',font=title,fill=cream)
    base_draw.text((35,88),'BUSINESS IN HINGLISH',font=small,fill=(223,174,92))
    base_draw.text((615,89),f'{index+1:02}/05',font=small,fill=cream)
    base_draw.rectangle((0,135,720,1015),fill=(235,226,204))
    base_draw.line((0,1015,720,1015),fill=(198,161,111),width=3)
    base_draw.rounded_rectangle((35,1257,685,1265),radius=4,fill=(220,210,186))
    frames=math.ceil(duration*24);duration=frames/24
    command=['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24',
             '-s','720x1280','-r','24','-i','-','-i',str(narration),'-frames:v',str(frames),
             '-t',str(duration),'-af','apad,loudnorm=I=-16:TP=-1.5:LRA=11',
             '-c:v','libx264','-preset','veryfast','-crf','21','-pix_fmt','yuv420p',
             '-c:a','aac','-ar','44100','-ac','1','-b:a','128k',str(clip)]
    process=subprocess.Popen(command,stdin=subprocess.PIPE)
    try:
        for frame in range(frames):
            t=frame/24;progress=frame/max(1,frames-1)
            image=base.copy()
            # A 1.5% push-in adds movement without cropping educational text.
            zoom=1+.015*progress
            width=round(694*zoom);height=round(868*zoom)
            slide=art.resize((width,height),Image.Resampling.BICUBIC)
            image.paste(slide,((720-width)//2,141+(868-height)//2))
            draw=ImageDraw.Draw(image)
            draw.rectangle((0,1018,720,1255),fill=cream)
            q=min(1,max(0,t/.4));q=1-(1-q)**3
            a=min(1,max(0,(t-min(1.05,duration*.12))/.45));a=1-(1-a)**3
            for layer,value,y in ((question_levels,q,1030),(answer_levels,a,1120)):
                part=layer[round(value*10)]
                if part:image.paste(part,(35,y+round(16*(1-value))),part)
            draw.rounded_rectangle((35,1257,35+round(650*(index+progress)/5),1265),radius=4,fill=rust)
            process.stdin.write(image.tobytes())
    finally:
        process.stdin.close()
    if process.wait()!=0: raise RuntimeError('FFmpeg animated scene render failed')
async def build(post,plan,directory):
    import edge_tts
    from PIL import Image
    directory.mkdir(parents=True,exist_ok=True)
    work=Path('.reel-work');work.mkdir(exist_ok=True)
    chunks=[]
    for i,(url,scene) in enumerate(zip(post['image_urls'],plan['scenes'])):
        jpg=work/f'{i}.jpg';urllib.request.urlretrieve(url,jpg)
        art=Image.open(jpg).convert('RGB');art.thumbnail((694,868))
        mp3=work/f'{i}.mp3'
        await edge_tts.Communicate(scene['narration'],'hi-IN-MadhurNeural',rate='+5%').save(str(mp3))
        narration=work/f'{i}.wav'
        duration=tighten_narration(mp3,narration)+.08
        clip=work/f'{i}.mp4';chunks.append(clip)
        render_scene(art,scene,i,duration,narration,clip)
    listing=work/'clips.txt';listing.write_text(''.join("file '"+str(p.resolve())+"'\n" for p in chunks))
    output=directory/'reel.mp4'
    run('ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',str(listing),'-c','copy','-movflags','+faststart',str(output))
    duration=float(run('ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(output)))
    if not 15<=duration<=90: raise ValueError(f'Reel duration {duration:.1f}s outside 15–90s')
    return output
def main():
    local=dt.datetime.now(ZoneInfo('Asia/Kolkata'))
    date=os.environ.get('REEL_DATE') or local.date().isoformat()
    if date>local.date().isoformat() or (date==local.date().isoformat() and local.hour<19):
        print('Not due until 19:00 Asia/Kolkata');return
    planpath=Path(f'reels/plans/{date}.json')
    if not planpath.exists(): raise RuntimeError(f'No narrated Reel plan for {date}; daily preparation has not completed')
    plan=json.loads(planpath.read_text());posts=json.loads(Path('posts.json').read_text())
    post=select(date,posts,plan)
    if not post.get('instagram_media_id') or not post.get('verified_at'):
        raise RuntimeError('Source carousel not yet verified published; leave Reel pending')
    statepath=Path(f'reels/state/{date}.json');statepath.parent.mkdir(parents=True,exist_ok=True)
    signature=hashlib.sha256(json.dumps([plan,post['image_urls']],sort_keys=True).encode()).hexdigest()
    state=json.loads(statepath.read_text()) if statepath.exists() else {'date':date,'source_post_id':post['id'],'signature':signature}
    if state['signature']!=signature: raise RuntimeError('Content changed after processing began')
    def save():
        statepath.write_text(json.dumps(state,indent=2)+'\n');checkpoint([statepath])
    ig=os.environ['IG_USER_ID'];page=os.environ['FACEBOOK_PAGE_ID']
    it=os.environ['META_ACCESS_TOKEN'].strip();ft=os.environ['FACEBOOK_PAGE_ACCESS_TOKEN'].strip()
    if instagram(ig,it,{'fields':'id,username'}).get('username')!='business.jalwa': raise RuntimeError('Wrong Instagram account')
    p=call('me',ft,{'fields':'id,name'})
    if str(p.get('id'))!=page or p.get('name')!='Business Jalwa': raise RuntimeError('Wrong Facebook Page')
    asset=Path(f'assets/reels/{date}/reel.mp4')
    if not state.get('video_url'):
        asyncio.run(build(post,plan,asset.parent));checkpoint([asset,planpath])
        sha=run('git','rev-parse','HEAD')
        state['video_url']=f'https://raw.githubusercontent.com/{REPO}/{sha}/{asset.as_posix()}'
        state['created_at']=now();save()
    caption=plan['caption']
    # Instagram: save the processing container, then save intent before publish.
    if not state.get('instagram_media_id'):
        if state.get('instagram_publish_requested_at'): raise RuntimeError('Uncertain Instagram result; reconcile before any retry')
        if not state.get('instagram_container_id'):
            state['instagram_container_id']=instagram(ig+'/media',it,{'media_type':'REELS','video_url':state['video_url'],'caption':caption,'share_to_feed':'true'},'POST')['id'];save()
        for _ in range(40):
            status=instagram(state['instagram_container_id'],it,{'fields':'status_code'}).get('status_code')
            if status=='FINISHED': break
            if status in ('ERROR','EXPIRED'): raise RuntimeError('Instagram video container '+status)
            time.sleep(15)
        else: raise RuntimeError('Instagram processing pending; rerun later')
        state['instagram_publish_requested_at']=now();save()
        result=instagram(ig+'/media_publish',it,{'creation_id':state['instagram_container_id']},'POST')
        state['instagram_media_id']=result['id'];state['instagram_published_at']=now();save()
    if not state.get('instagram_verified_at'):
        media=instagram(state['instagram_media_id'],it,{'fields':'id,permalink,media_product_type,timestamp'})
        if media.get('media_product_type')!='REELS': raise RuntimeError('Instagram result is not a Reel')
        state['instagram_permalink']=media['permalink'];state['instagram_verified_at']=now();save()
    # Facebook: uploaded draft video is distinct from a published Reel.
    if not state.get('facebook_publish_requested_at'):
        if not state.get('facebook_video_id'):
            result=call(page+'/video_reels',ft,{'upload_phase':'start'},'POST')
            state['facebook_video_id']=result['video_id'];state['facebook_upload_url']=result['upload_url'];save()
        if not state.get('facebook_uploaded_at'):
            url=state['facebook_upload_url']
            if urllib.parse.urlparse(url).hostname!='rupload.facebook.com': raise RuntimeError('Unexpected upload host')
            response=call(url,ft,method='POST',headers={'file_url':state['video_url']})
            if response.get('success') is not True: raise RuntimeError('Facebook upload not accepted')
            state['facebook_uploaded_at']=now();save()
        state['facebook_publish_requested_at']=now();save()
        result=call(page+'/video_reels',ft,{'upload_phase':'finish','video_id':state['facebook_video_id'],'video_state':'PUBLISHED','description':caption},'POST')
        if result.get('success') is not True: raise RuntimeError('Uncertain Facebook publish; reconcile before retry')
        state['facebook_publish_accepted_at']=now();save()
    if not state.get('facebook_verified_at'):
        for _ in range(40):
            video=call(state['facebook_video_id'],ft,{'fields':'id,status,permalink_url'})
            status=video.get('status',{})
            if status.get('publishing_phase',{}).get('status')=='complete':
                state['facebook_verified_at']=now();state['facebook_permalink']=video.get('permalink_url');save();break
            if status.get('video_status')=='error': raise RuntimeError('Facebook video processing failed')
            time.sleep(15)
        else: raise RuntimeError('Facebook publication not yet verified; check saved video ID')
    print(json.dumps({k:v for k,v in state.items() if 'permalink' in k or 'verified_at' in k}))
if __name__=='__main__': main()
