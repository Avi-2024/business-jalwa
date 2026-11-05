"""Topic-matched six-panel original storyboard artwork for Business Jalwa Reels."""
from pathlib import Path
from PIL import Image, ImageDraw

BG=(17,23,33,255); WALL=(31,45,59,220); COUNTER=(120,78,52,220)
GOLD=(242,187,82,255); BLUE=(70,142,213,255); TEAL=(49,140,132,255)
RUST=(181,91,62,255); SKIN=(204,145,103,255); SKIN2=(230,180,137,255)
HAIR=(38,28,24,255); CREAM=(245,232,205,255); BOX=(179,133,83,255)
BOX2=(206,165,113,255); DARK=(14,18,24,255); WHITE=(244,241,230,255)
GREY=(112,126,139,255)

def person(d,x,y,shirt=TEAL,skin=SKIN,female=False,lean=False):
    # Transparent editorial character cutout, waist-up details and visible hands.
    d.rounded_rectangle((x-7,y+22,x+7,y+43),radius=4,fill=skin)
    if lean:
        d.polygon([(x-23,y+40),(x+19,y+38),(x+34,y+105),(x-32,y+105)],fill=shirt)
    else:
        d.polygon([(x-24,y+40),(x+24,y+40),(x+30,y+108),(x-30,y+108)],fill=shirt)
    if shirt==TEAL:
        d.polygon([(x-14,y+45),(x+14,y+45),(x+19,y+103),(x-19,y+103)],fill=(102,73,54,255))
        d.line((x-13,y+46,x-18,y+100),fill=GOLD,width=2)
    if lean:
        d.line((x-17,y+50,x-40,y+76,x-5,y+91),fill=skin,width=12,joint="curve")
        d.line((x+17,y+50,x+42,y+73,x+23,y+91),fill=skin,width=12,joint="curve")
    else:
        d.line((x-17,y+50,x-33,y+78,x-24,y+96),fill=skin,width=12,joint="curve")
        d.line((x+17,y+50,x+33,y+78,x+24,y+96),fill=skin,width=12,joint="curve")
    d.ellipse((x-22,y-6,x+22,y+42),fill=skin,outline=(78,54,42,255),width=2)
    d.pieslice((x-24,y-13,x+24,y+29),180,360,fill=HAIR)
    if female:
        d.ellipse((x-27,y+1,x-14,y+48),fill=HAIR)
        d.ellipse((x+14,y+1,x+27,y+48),fill=HAIR)
    d.ellipse((x-10,y+15,x-6,y+19),fill=DARK)
    d.ellipse((x+6,y+15,x+10,y+19),fill=DARK)
    d.arc((x-7,y+22,x+8,y+33),5,175,fill=(95,54,43,255),width=2)
    d.line((x-12,y+106,x-17,y+150),fill=(43,48,57,255),width=12)
    d.line((x+12,y+106,x+17,y+150),fill=(43,48,57,255),width=12)

def box(d,x,y,w=70,h=58,tone=BOX):
    d.rounded_rectangle((x,y,x+w,y+h),radius=5,fill=tone,outline=(91,64,44,255),width=3)
    d.line((x+5,y+13,x+w-5,y+13),fill=(132,93,58,255),width=3)
    d.line((x+w/2,y+2,x+w/2,y+13),fill=(132,93,58,255),width=3)
    # A paper-cup silhouette, not a label or word.
    d.polygon([(x+w*.37,y+h*.39),(x+w*.63,y+h*.39),(x+w*.58,y+h*.76),(x+w*.42,y+h*.76)],fill=CREAM)
    d.arc((x+w*.41,y+h*.32,x+w*.59,y+h*.48),180,360,fill=CREAM,width=2)

def paper(d,x,y,w=70,h=90):
    d.rounded_rectangle((x,y,x+w,y+h),radius=4,fill=CREAM,outline=(185,171,145,255),width=2)
    for yy in (y+23,y+42,y+61,y+78):
        d.line((x+9,yy,x+w-9,yy),fill=(185,177,158,255),width=2)

def cafe_tile(i):
    im=Image.new("RGBA",(480,320),(0,0,0,0)); d=ImageDraw.Draw(im)
    # Cafe shelf and counter establish a real shop setting without a full-frame card.
    d.line((15,48,166,48),fill=COUNTER,width=7)
    for x,c in ((25,BLUE),(52,GOLD),(79,TEAL),(106,RUST),(133,GREY)):
        d.rounded_rectangle((x,55,x+17,91),radius=3,fill=c)
    d.line((0,224,480,224),fill=COUNTER,width=12)
    if i==0:
        person(d,112,69,TEAL,lean=True); person(d,366,73,RUST,SKIN2,True)
        box(d,198,162,66,54); box(d,270,162,66,54,BOX2); box(d,342,162,66,54)
    elif i==1:
        person(d,133,69,TEAL); person(d,371,75,RUST,SKIN2,True)
        paper(d,205,148,82,104); box(d,305,175,61,49)
    elif i==2:
        person(d,100,68,TEAL,lean=True)
        for x in (188,263,338):
            box(d,x,159,66,65,BOX if x!=263 else BOX2)
            for j in range(3):
                d.polygon([(x+17+j*9,145),(x+25+j*9,145),(x+24+j*9,159),(x+18+j*9,159)],fill=WHITE)
    elif i==3:
        person(d,111,72,TEAL,lean=True); person(d,379,76,RUST,SKIN2,True)
        paper(d,177,147,68,102); paper(d,258,147,68,102); paper(d,339,147,68,102)
    elif i==4:
        person(d,122,72,TEAL); person(d,367,76,RUST,SKIN2,True)
        box(d,199,160,70,62,BOX2); box(d,286,160,70,62)
        d.line((278,150,278,228),fill=GOLD,width=4); paper(d,26,172,57,77)
    else:
        person(d,165,73,TEAL); person(d,326,73,RUST,SKIN2,True)
        d.line((193,164,264,164),fill=SKIN2,width=12); d.line((264,164,302,164),fill=SKIN,width=12)
        box(d,225,193,64,52); paper(d,365,165,56,76)
    return im

def phone(d,x,y,w=52,h=91,cracked=False,screen=(23,35,48,255)):
    d.rounded_rectangle((x,y,x+w,y+h),radius=8,fill=(22,27,33,255),outline=(180,192,201,255),width=3)
    d.rounded_rectangle((x+4,y+7,x+w-4,y+h-8),radius=5,fill=screen,outline=(75,93,109,255),width=1)
    d.ellipse((x+w/2-3,y+2,x+w/2+3,y+5),fill=GREY)
    if cracked:
        d.line((x+w*.58,y+h*.15,x+w*.38,y+h*.42,x+w*.62,y+h*.54,x+w*.35,y+h*.82),fill=WHITE,width=2)
        d.line((x+w*.38,y+h*.42,x+w*.18,y+h*.32),fill=WHITE,width=2)
        d.line((x+w*.62,y+h*.54,x+w*.82,y+h*.39),fill=WHITE,width=2)

def jobcard(d,x,y,w=74,h=96):
    d.rounded_rectangle((x,y,x+w,y+h),radius=4,fill=CREAM,outline=(185,171,145,255),width=2)
    for yy in (y+23,y+42,y+61,y+79):
        d.line((x+9,yy,x+w-9,yy),fill=(185,177,158,255),width=2)

def mobile_tile(i):
    im=Image.new("RGBA",(480,320),(0,0,0,0)); d=ImageDraw.Draw(im)
    d.line((15,48,176,48),fill=COUNTER,width=7)
    for x,c in ((24,BLUE),(55,GREY),(86,RUST),(117,TEAL),(148,GOLD)):
        d.rounded_rectangle((x,55,x+18,91),radius=3,fill=c)
    d.line((0,224,480,224),fill=COUNTER,width=12)
    if i==0:
        person(d,120,69,BLUE); person(d,359,74,GOLD,SKIN2,True)
        phone(d,214,145,60,103,True); d.line((171,169,211,169),fill=SKIN2,width=10)
    elif i==1:
        person(d,120,70,BLUE); person(d,368,76,GOLD,SKIN2,True)
        phone(d,193,157,48,86,True); jobcard(d,268,145,73,105)
    elif i==2:
        person(d,101,70,BLUE); person(d,380,76,GOLD,SKIN2,True)
        jobcard(d,180,145,82,107)
        d.rounded_rectangle((291,156,341,239),radius=5,fill=(25,31,40,255),outline=BLUE,width=3)
        d.rounded_rectangle((297,163,335,231),radius=3,fill=(69,103,129,255),outline=GREY,width=1)
        d.ellipse((310,233,321,244),fill=GOLD)
    elif i==3:
        person(d,144,70,BLUE); person(d,349,74,GOLD,SKIN2,True)
        jobcard(d,208,153,76,93); phone(d,161,166,40,73,True)
        d.line((327,145,301,166,287,158),fill=SKIN2,width=11)
        d.ellipse((280,151,295,167),fill=SKIN2)
    elif i==4:
        person(d,118,70,BLUE); person(d,368,76,GOLD,SKIN2,True)
        phone(d,214,154,57,98,False)
        d.rounded_rectangle((289,175,342,220),radius=7,fill=(28,34,42,255),outline=GOLD,width=3)
        d.rectangle((306,208,321,216),fill=GREY); jobcard(d,25,176,54,83)
    else:
        person(d,159,71,BLUE); person(d,340,76,GOLD,SKIN2,True)
        phone(d,229,150,57,100,False,(64,111,104,255))
        d.rounded_rectangle((292,193,344,230),radius=5,fill=(35,41,48,255),outline=GREY,width=2)
        d.line((300,199,335,223),fill=WHITE,width=2); d.line((335,199,300,223),fill=WHITE,width=2)
    return im

def ensure_storyboard(plan):
    """Create or repair the plan's 3x2 topic-matched PNG without changing its JSON."""
    path=Path(plan["visual_asset"])
    columns,rows=plan.get("visual_grid",[1,1])
    if columns!=3 or rows!=2:
        raise ValueError("Original Reel storyboard must use a 3x2 grid")
    if path.exists():
        try:
            with Image.open(path) as image:
                image.load()
                if image.width%columns==0 and image.height%rows==0:
                    return path
        except Exception:
            pass
    topic=str(plan.get("topic","")).lower()
    if any(term in topic for term in ("purchase order","supplier","cafe","कैफ़े")):
        tiles=[cafe_tile(i) for i in range(6)]
    elif any(term in topic for term in ("mobile repair","phone","मरम्मत")):
        tiles=[mobile_tile(i) for i in range(6)]
    else:
        raise ValueError("No topic-specific storyboard illustrator is available for this Reel")
    canvas=Image.new("RGBA",(1440,640),(0,0,0,0))
    for i,tile in enumerate(tiles):
        canvas.alpha_composite(tile,((i%3)*480,(i//3)*320))
    path.parent.mkdir(parents=True,exist_ok=True)
    canvas.save(path,format="PNG",optimize=True)
    return path
