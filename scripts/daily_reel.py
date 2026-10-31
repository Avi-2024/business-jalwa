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
    return trimmed, [(left/rate, right/rate) for left,right in cuts]
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
    if plan.get('content_mode')=='original':
        if plan.get('approved') is not True: raise ValueError('Approval missing')
        if plan.get('source_post_id') not in (None,''): raise ValueError('Original Reel must not claim a carousel source')
        scenes=plan.get('scenes',[])
        if len(scenes)!=5: raise ValueError('Exactly five scenes required')
        for s in scenes:
            if not all(isinstance(s.get(k),str) and s[k].strip() for k in ('narration','question','answer')): raise ValueError('Incomplete scene')
        return None
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
    from kinetic_reel import remap_words,render_scene
    directory.mkdir(parents=True,exist_ok=True)
    work=Path('.reel-work');work.mkdir(exist_ok=True)
    chunks=[]
    for i,scene in enumerate(plan['scenes']):
        mp3=work/f'{i}.mp3';metadata=work/f'{i}.words.jsonl'
        # WordBoundary offsets come from the same TTS stream as this audio.
        for attempt in range(4):
            try:
                await edge_tts.Communicate(scene['narration'],'hi-IN-MadhurNeural',
                                           rate='+5%',boundary='WordBoundary').save(str(mp3),str(metadata))
                break
            except edge_tts.exceptions.NoAudioReceived:
                if attempt==3: raise
                delay=5*(attempt+1)
                print(f'Voice service returned no audio; retrying scene {i+1} in {delay}s',flush=True)
                await asyncio.sleep(delay)
        narration=work/f'{i}.wav'
        voice_duration,removed=tighten_narration(mp3,narration)
        words=remap_words(metadata,removed,voice_duration)
        clip=work/f'{i}.mp4';chunks.append(clip)
        render_scene({**scene, 'topic': plan.get('topic', ''), 'visual_asset': plan.get('visual_asset', '')},i,voice_duration+.08,narration,words,clip)
    listing=work/'clips.txt';listing.write_text(''.join("file '"+str(p.resolve())+"'\n" for p in chunks))
    output=directory/f'Business-Jalwa-Reel-{directory.name}.mp4'
    run('ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',str(listing),'-c','copy','-movflags','+faststart',str(output))
    duration=float(run('ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(output)))
    if not 15<=duration<=90: raise ValueError(f'Reel duration {duration:.1f}s outside 15–90s')
    return output
def main():
    local=dt.datetime.now(ZoneInfo('Asia/Kolkata'))
    today=local.date().isoformat()
    requested_date=os.environ.get('REEL_DATE')
    force_render_only=os.environ.get('REEL_RENDER_ONLY','').lower() in ('true','1','yes')
    # On repository pushes, render the earliest future plan that has no committed video.
    if not requested_date and os.environ.get('GITHUB_EVENT_NAME')=='push':
        for plan_file in sorted(Path('reels/plans').glob('????-??-??.json')):
            candidate=plan_file.stem
            if candidate<=today: continue
            pending_state=Path(f'reels/state/{candidate}.json')
            saved=json.loads(pending_state.read_text()) if pending_state.exists() else {}
            if not saved.get('video_url'):
                requested_date=candidate
                force_render_only=True
                print(f'Pending future Reel found; preparing {requested_date} only')
                break
    date=requested_date or today
    if date>today and not force_render_only:
        print('Future Reel date; no processing yet');return
    render_only=force_render_only or os.environ.get('GITHUB_EVENT_NAME')=='push' or (date==today and local.hour<9)
    planpath=Path(f'reels/plans/{date}.json')
    if not planpath.exists(): raise RuntimeError(f'No narrated Reel plan for {date}; daily preparation has not completed')
    plan=json.loads(planpath.read_text());posts=json.loads(Path('posts.json').read_text())
    post=select(date,posts,plan)
    if post and (not post.get('instagram_media_id') or not post.get('verified_at')):
        raise RuntimeError('Source carousel not yet verified published; leave Reel pending')
    statepath=Path(f'reels/state/{date}.json');statepath.parent.mkdir(parents=True,exist_ok=True)
    source_id=post['id'] if post else None
    source_images=post['image_urls'] if post else []
    signature=hashlib.sha256(json.dumps([plan,source_images],sort_keys=True).encode()).hexdigest()
    state=json.loads(statepath.read_text()) if statepath.exists() else {'date':date,'source_post_id':source_id,'signature':signature}
    if state['signature']!=signature: raise RuntimeError('Content changed after processing began')
    def save():
        statepath.write_text(json.dumps(state,indent=2)+'\n');checkpoint([statepath])
    ig=os.environ['IG_USER_ID'];page=os.environ['FACEBOOK_PAGE_ID']
    it=os.environ['META_ACCESS_TOKEN'].strip();ft=os.environ['FACEBOOK_PAGE_ACCESS_TOKEN'].strip()
    if instagram(ig,it,{'fields':'id,username'}).get('username')!='business.jalwa': raise RuntimeError('Wrong Instagram account')
    p=call('me',ft,{'fields':'id,name'})
    if str(p.get('id'))!=page or p.get('name')!='Business Jalwa': raise RuntimeError('Wrong Facebook Page')
    asset=Path(f'assets/reels/{date}/Business-Jalwa-Reel-{date}.mp4')
    legacy_asset=Path(f'assets/reels/{date}/reel.mp4')
    if (not state.get('instagram_media_id') and not state.get('facebook_publish_requested_at')
            and not asset.exists() and legacy_asset.exists()):
        legacy_asset.rename(asset)
        checkpoint([legacy_asset,asset])
        sha=run('git','rev-parse','HEAD')
        state['video_url']=f'https://raw.githubusercontent.com/{REPO}/{sha}/{asset.as_posix()}'
        state['renamed_at']=now()
        save()
    if not state.get('video_url'):
        asyncio.run(build(post,plan,asset.parent));checkpoint([asset,planpath])
        sha=run('git','rev-parse','HEAD')
        state['video_url']=f'https://raw.githubusercontent.com/{REPO}/{sha}/{asset.as_posix()}'
        state['created_at']=now();save()
    if render_only:
        print('Reel video rendered and committed; publishing waits until 19:00 Asia/Kolkata')
        return
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
