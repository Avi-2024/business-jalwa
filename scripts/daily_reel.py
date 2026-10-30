"""Build and publish one explicitly approved narrated carousel adaptation.

Durable state is committed BEFORE each non-idempotent publish request. An
uncertain response must be reconciled manually; reruns never blindly republish.
"""
import asyncio, datetime as dt, hashlib, json, math, os, subprocess, sys, time
import urllib.request, urllib.parse, urllib.error, wave
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path('.')
REPO='Avi-2024/business-jalwa'
API='https://graph.facebook.com/v23.0/'
def run(*args): return subprocess.check_output(args, text=True).strip()
def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
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
async def build(post,plan,directory):
    import edge_tts
    from PIL import Image,ImageDraw,ImageFont
    directory.mkdir(parents=True,exist_ok=True)
    work=Path('.reel-work');work.mkdir(exist_ok=True)
    font='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    chunks=[]
    for i,(url,scene) in enumerate(zip(post['image_urls'],plan['scenes'])):
        jpg=work/f'{i}.jpg';urllib.request.urlretrieve(url,jpg)
        im=Image.new('RGB',(720,1280),(250,245,229));d=ImageDraw.Draw(im)
        d.rectangle((0,0,720,135),fill=(23,62,48))
        d.text((35,34),'BUSINESS JALWA',font=ImageFont.truetype(font,32),fill='white')
        d.text((35,87),'BUSINESS IN HINGLISH',font=ImageFont.truetype(font,17),fill=(223,174,92))
        art=Image.open(jpg).convert('RGB');art.thumbnail((694,868))
        im.paste(art,((720-art.width)//2,141+(868-art.height)//2))
        for box,text,color,ink in [((35,1030,685,1108),scene['question'],(23,62,48),'white'),((35,1120,685,1245),scene['answer'],(255,255,250),(23,62,48))]:
            d.rounded_rectangle(box,radius=20,fill=color)
            size=24
            while True:
                f=ImageFont.truetype(font,size);words=text.split();lines=['']
                for word in words:
                    trial=(lines[-1]+' '+word).strip()
                    if d.textlength(trial,font=f)>596: lines.append(word)
                    else: lines[-1]=trial
                if len(lines)*(size+5)<=box[3]-box[1]-26: break
                size-=1
                if size<18: raise ValueError('Shorten scene overlay text')
            d.multiline_text((box[0]+20,box[1]+14),'\n'.join(lines),font=f,fill=ink,spacing=5)
        png=work/f'{i}.png';im.save(png)
        mp3=work/f'{i}.mp3'
        await edge_tts.Communicate(scene['narration'],'hi-IN-MadhurNeural',rate='+5%').save(str(mp3))
        duration=float(run('ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(mp3)))+.35
        clip=work/f'{i}.mp4';chunks.append(clip)
        run('ffmpeg','-y','-loglevel','error','-loop','1','-i',str(png),'-i',str(mp3),'-t',str(duration),'-vf','fps=24,format=yuv420p','-af','apad,loudnorm=I=-16:TP=-1.5:LRA=11','-c:v','libx264','-preset','veryfast','-crf','21','-c:a','aac','-ar','44100','-ac','1','-b:a','128k',str(clip))
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
