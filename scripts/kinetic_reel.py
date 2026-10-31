"""Voice-led Business Jalwa Reel visuals; no carousel art appears in the video."""
import bisect
import json
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZE = (720, 1280)
FPS = 24
WHITE = (248, 247, 242)
MUTED = (168, 170, 168)
GOLD = (255, 199, 91)
FONT_LATIN = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_HINDI = str(Path(__file__).resolve().parents[1] / 'assets/fonts/NotoSansDevanagari.ttf')
LOGO = Path(__file__).resolve().parents[1] / 'assets/branding/business-jalwa-logo.jpg'
VISUAL_DIR = Path(__file__).resolve().parents[1] / 'assets/reels/visual-library'
VISUALS = sorted(VISUAL_DIR.glob('cutaway-*.webp'))


def remap_words(metadata_path, removed_intervals, audio_duration):
    """Use Edge TTS WordBoundary ticks, accounting for silence removed from audio."""
    boundaries = [json.loads(line) for line in Path(metadata_path).read_text().splitlines()]
    words = []
    for item in boundaries:
        if item.get('type') != 'WordBoundary' or not item.get('text', '').strip():
            continue
        original_start = item['offset'] / 10_000_000
        original_end = (item['offset'] + item['duration']) / 10_000_000
        def shortened(seconds):
            return seconds - sum(max(0, min(seconds, right) - left)
                                 for left, right in removed_intervals if seconds > left)
        start = max(0, shortened(original_start))
        end = max(start + .04, shortened(original_end))
        if start >= audio_duration + .15:
            continue
        words.append({'text': item['text'].strip(), 'start': start, 'end': min(end, audio_duration)})
    if len(words) < 5:
        raise ValueError('Word timestamps missing; refusing to make unsynchronised captions')
    if any(b['start'] + .03 < a['start'] for a, b in zip(words, words[1:])):
        raise ValueError('Word timestamps are out of order')
    return words


AMOUNTS = {
    'दो': 2, 'तीन': 3, 'चार': 4, 'पाँच': 5, 'पांच': 5,
    'छह': 6, 'सात': 7, 'आठ': 8, 'नौ': 9, 'दस': 10,
    'बीस': 20, 'तीस': 30, 'चालीस': 40, 'पचास': 50,
    'साठ': 60, 'सत्तर': 70, 'अस्सी': 80, 'नब्बे': 90,
    'सौ': 100,
}


def readable_words(words):
    """Show spoken amounts as digits without changing the audio timings.

    Only convert unambiguous number phrases. Other Hindi stays as narrated.
    """
    output = []
    i = 0
    while i < len(words):
        raw = [word['text'].rstrip('।,?!') for word in words[i:i + 4]]
        count, label = 1, words[i]['text']
        if (len(raw) >= 3 and raw[0] in AMOUNTS and raw[1] == 'गुणा'
                and raw[2] in AMOUNTS):
            count, label = 3, f"{AMOUNTS[raw[0]]:,} × ₹{AMOUNTS[raw[2]]:,}"
        elif (len(raw) >= 2 and raw[0] in AMOUNTS and raw[1] in ('हज़ार', 'हजार', 'लाख')):
            value = AMOUNTS[raw[0]] * (100_000 if raw[1] == 'लाख' else 1_000)
            count = 2
            if len(raw) >= 3 and raw[2] in ('रुपये', 'रुपए', 'रुपये।'):
                count = 3
            label = f"{'₹' if count == 3 else ''}{value:,}"
        elif raw[0] in AMOUNTS:
            value = AMOUNTS[raw[0]]
            count = 2 if len(raw) >= 2 and raw[1] in ('रुपये', 'रुपए') else 1
            label = f"{'₹' if count == 2 else ''}{value:,}"
        output.append({'text': label, 'start': words[i]['start'],
                       'end': words[i + count - 1]['end']})
        i += count
    return output


def caption_groups(words):
    """Keep each spoken thought on screen for about one second."""
    groups = []
    for word in words:
        if not groups or len(groups[-1]) >= 4 or sum(len(w['text']) for w in groups[-1]) + len(word['text']) > 26:
            groups.append([])
        groups[-1].append(word)
        if word['text'].endswith(('।', '?', '!', '.')):
            groups.append([])
    return [group for group in groups if group]


def caption_layer(group, shown):
    """Show the whole phrase while the spoken word gains emphasis."""
    visible = group
    canvas = Image.new('RGBA', (650, 300), (0, 0, 0, 0))
    if not visible:
        return canvas
    d = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(FONT_HINDI, 48)
    rows = [[]]
    for word in visible:
        trial = ' '.join(w['text'] for w in rows[-1] + [word])
        if rows[-1] and d.textlength(trial, font=font) > 550:
            rows.append([word])
        else:
            rows[-1].append(word)
    if len(rows) > 2:
        raise ValueError('Spoken caption exceeds two lines')
    y = 126 - (len(rows) - 1) * 33
    for row in rows:
        whole = ' '.join(word['text'] for word in row)
        x = (650 - d.textlength(whole, font=font)) / 2
        for word in row:
            active = word is group[shown - 1]
            ink = GOLD if active else MUTED
            # Hold back the result until its own voice beat; keep its space
            # reserved so the centered phrase never jumps horizontally.
            if active or word not in group[shown:] or not any(ch.isdigit() for ch in word['text']):
                d.text((round(x), y), word['text'], font=font, fill=ink)
            x += d.textlength(word['text'], font=font) + d.textlength(' ', font=font)
        y += 67
    glow = Image.new('RGBA', canvas.size, (255, 250, 241, 0))
    glow.putalpha(canvas.getchannel('A').filter(ImageFilter.GaussianBlur(17)).point(lambda value: value // 3))
    return Image.alpha_composite(glow, canvas)


def background():
    """Pure black brand canvas with visible fine corner arcs and the logo."""
    image = Image.new('RGBA', SIZE, (0, 0, 0, 255))
    detail = Image.new('RGBA', SIZE, (0, 0, 0, 0))
    d = ImageDraw.Draw(detail)
    # Keep the lines visible on black without tinting the caption area.
    d.arc((-320, -305, 300, 315), 3, 89, fill=(255, 194, 76, 205), width=3)
    d.arc((-255, -242, 235, 248), 5, 85, fill=(54, 106, 245, 220), width=2)
    d.arc((460, 1010, 1060, 1610), 186, 272, fill=(255, 194, 76, 205), width=3)
    d.arc((510, 1056, 1010, 1556), 185, 270, fill=(54, 106, 245, 220), width=2)
    image = Image.alpha_composite(image, detail)
    if not LOGO.exists():
        raise FileNotFoundError('Bundled Business Jalwa logo is required')
    diameter = 148
    left, top = (SIZE[0] - diameter) // 2, 66
    logo = Image.open(LOGO).convert('RGB').resize((diameter, diameter), Image.Resampling.LANCZOS)
    mask = Image.new('L', (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((1, 1, diameter - 2, diameter - 2), fill=255)
    image.paste(logo, (left, top), mask)
    ring = ImageDraw.Draw(image)
    ring.ellipse((left, top, left + diameter - 1, top + diameter - 1),
                 outline=(255, 199, 91, 230), width=2)
    return image.convert('RGB')


def visual_layer(index, elapsed, scene=None):
    """Use a unique generated image for this Reel; fall back to the general library only when absent."""
    custom_path = Path(scene.get('visual_asset', '')) if scene else Path()
    if custom_path.is_file():
        source = Image.open(custom_path).convert('RGBA')
        columns, rows = (scene or {}).get('visual_grid', [1, 1])
        if columns > 1 or rows > 1:
            tile_index = (index + int(elapsed / 3.5)) % (columns * rows)
            tile_width, tile_height = source.width // columns, source.height // rows
            left = (tile_index % columns) * tile_width
            top = (tile_index // columns) * tile_height
            source = source.crop((left, top, left + tile_width, top + tile_height))
    else:
        if not VISUALS:
            raise FileNotFoundError('Business cutaway visuals are required')
        source = Image.open(VISUALS[index % len(VISUALS)]).convert('RGBA')
    """Subtle moving cutout visual; switch to a new business scene every 3.5 seconds."""
    bounds = source.getbbox()
    if bounds:
        source = source.crop(bounds)
    phase = (elapsed % 3.5) / 3.5
    scale = min(610 / source.width, 565 / source.height) * (1 + .035 * phase)
    size = (max(1, round(source.width * scale)), max(1, round(source.height * scale)))
    source = source.resize(size, Image.Resampling.LANCZOS)
    x = (SIZE[0] - size[0]) // 2 + round(7 * math.sin(phase * math.pi))
    y = SIZE[1] - size[1] - 48
    return source, (x, y)


def scene_topic(scene):
    """Classify the current spoken beat so the illustration follows its lesson."""
    text = ' '.join(str(scene.get(k, '')) for k in ('visual', 'topic', 'question', 'answer', 'narration')).lower()
    rules = [
        ('inventory', ('inventory', 'stock turnover', 'stock level', 'slow-moving stock', 'average inventory', 'reorder point', 'इन्वेंटरी', 'स्टॉक')),
        ('acquisition', ('customer acquisition', 'acquisition cost', 'new customer', 'marketing', 'ad spend', 'campaign', 'cac', 'विज्ञापन', 'नए ग्राहक')),
        ('breakeven', ('break-even', 'break even', 'break_even', 'breakeven', 'ब्रेक-ईवन')),
        ('pricing', ('discount', 'pricing', 'selling price', 'price cut', 'छूट', 'कीमत')),
        ('cashflow', ('cash flow', 'cashflow', 'cash-flow', 'due date', 'payment', 'cash', 'भुगतान', 'पेमेंट')),
        ('retention', ('repeat', 'reorder', 'returning customer', 'customer rate', 'customer retention', 'दोबारा', 'ग्राहक')),
        ('costs', ('cost', 'expense', 'contribution', 'profit', 'margin', 'खर्च', 'लागत', 'कमाई')),
        ('growth', ('growth', 'sales', 'revenue', 'increase', 'बढ़', 'विकास', 'बिक्री')),
    ]
    for category, keys in rules:
        if any(key in text for key in keys):
            return category
    return 'business'


def topic_visual_layer(scene, elapsed):
    """A small animated editorial illustration that matches the spoken topic."""
    category = scene_topic(scene)
    size = 176
    layer = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    pulse = 1 + .025 * math.sin(elapsed * 2.3)
    pad = round(10 * (1 - pulse))
    d.ellipse((10 + pad, 10 + pad, 166 - pad, 166 - pad),
              fill=(0, 0, 0, 220), outline=(255, 199, 91, 225), width=2)
    gold, blue, white, mint = (255, 199, 91, 255), (74, 137, 255, 255), (248, 247, 242, 245), (106, 211, 169, 255)
    def line(points, fill=white, width=5):
        d.line(points, fill=fill, width=width, joint='curve')
    if category == 'breakeven':
        # Fixed-cost threshold and a rising contribution line crossing it.
        line([(37, 132), (37, 47)], blue, 4); line([(37, 132), (141, 132)], blue, 4)
        for x in (57, 79, 101, 123):
            d.rounded_rectangle((x, 112 - (x - 57), x + 10, 130), radius=3, fill=(74, 137, 255, 170))
        line([(45, 117), (72, 105), (94, 91), (121, 65), (141, 49)], gold, 6)
        line([(41, 91), (138, 91)], (248, 247, 242, 140), 2)
        d.ellipse((111, 55, 129, 73), fill=gold)
    elif category == 'cashflow':
        # Payment calendar with dated in/out movement and a coin.
        d.rounded_rectangle((38, 42, 112, 119), radius=9, outline=blue, width=5)
        line([(38, 62), (112, 62)], blue, 4)
        for x in (57, 92): line([(x, 34), (x, 50)], gold, 5)
        for x, y in ((56, 78), (76, 78), (96, 78), (56, 98), (76, 98)):
            d.ellipse((x-3, y-3, x+3, y+3), fill=white)
        d.ellipse((111, 92, 151, 132), fill=(0,0,0,255), outline=gold, width=4)
        d.text((119, 98), '₹', font=ImageFont.truetype(FONT_LATIN, 23), fill=gold)
        line([(123, 85), (138, 69)], mint, 4); line([(131, 69), (138, 69), (138, 76)], mint, 4)
    elif category == 'retention':
        # Returning customers linked by a circular repeat arrow.
        for cx, cy in ((63, 76), (113, 76)):
            d.ellipse((cx-12, cy-26, cx+12, cy-2), outline=white, width=4)
            d.arc((cx-25, cy-2, cx+25, cy+45), 190, 350, fill=blue, width=5)
        d.arc((42, 35, 139, 138), 202, 318, fill=gold, width=5)
        line([(123, 43), (139, 45), (134, 59)], gold, 5)
    elif category == 'costs':
        # Itemized receipt and a calculator cue.
        line([(54, 36), (116, 36), (116, 119), (54, 119), (54, 36)], white, 4)
        for y, col in ((56, blue), (75, gold), (94, blue)):
            line([(65, y), (82, y)], white, 3)
            d.rounded_rectangle((91, y-8, 105, y+7), radius=4, fill=col)
        line([(60, 107), (108, 107)], (248,247,242,150), 2)
        d.ellipse((118, 105, 151, 138), fill=(0,0,0,255), outline=gold, width=4)
        d.text((125, 108), '−', font=ImageFont.truetype(FONT_LATIN, 22), fill=gold)
    elif category == 'inventory':
        # Stock shelf with distinct boxes and a reorder marker.
        line([(40, 124), (138, 124)], blue, 5)
        line([(45, 83), (133, 83)], blue, 5)
        for x, y, w, h, col in ((49, 55, 29, 27, gold), (86, 49, 38, 34, white),
                                (57, 92, 35, 28, white), (101, 91, 29, 29, gold)):
            d.rounded_rectangle((x, y, x+w, y+h), radius=4, outline=col, width=4)
        line([(121, 44), (141, 44), (141, 64)], mint, 4)
        line([(133, 55), (141, 64), (149, 55)], mint, 4)
    elif category == 'acquisition':
        # Megaphone aimed at new customer dots.
        line([(43, 73), (96, 55), (96, 117), (43, 99), (43, 73)], gold, 5)
        line([(43, 78), (32, 78), (32, 94), (43, 94)], white, 4)
        line([(54, 102), (63, 129), (79, 129), (70, 108)], blue, 5)
        line([(108, 63), (125, 52)], mint, 4)
        line([(111, 86), (137, 86)], mint, 4)
        line([(108, 108), (125, 121)], mint, 4)
        for x, y in ((136, 47), (145, 82), (136, 124)):
            d.ellipse((x-5, y-5, x+5, y+5), fill=gold)
    elif category == 'pricing':
        # Price tag and a visible before/after bar comparison.
        line([(39, 71), (76, 38), (119, 38), (138, 57), (94, 101), (39, 71)], gold, 5)
        d.ellipse((111, 47, 120, 56), fill=white)
        line([(49, 132), (138, 132)], blue, 4)
        d.rounded_rectangle((57, 92, 79, 128), radius=4, fill=white)
        d.rounded_rectangle((99, 107, 121, 128), radius=4, fill=gold)
        line([(81, 86), (97, 98)], mint, 4)
    elif category == 'growth':
        # Rising sales bars with an upward trend arrow.
        line([(41, 132), (41, 49)], blue, 4); line([(41, 132), (140, 132)], blue, 4)
        for x, height in ((55, 24), (78, 43), (101, 63), (124, 83)):
            d.rounded_rectangle((x, 128-height, x+13, 128), radius=4, fill=gold if x == 124 else blue)
        line([(55, 95), (81, 79), (104, 68), (136, 43)], mint, 5)
        line([(125, 43), (136, 43), (136, 55)], mint, 5)
    else:
        # Small shopfront plus the order bag for general business topics.
        d.rectangle((43, 64, 113, 124), outline=blue, width=4)
        line([(37, 64), (48, 43), (108, 43), (120, 64)], gold, 5)
        for x in (48, 70, 92, 111): line([(x, 44), (x, 64)], gold, 3)
        d.rectangle((62, 87, 91, 124), outline=white, width=4)
        d.rounded_rectangle((112, 84, 145, 128), radius=5, outline=gold, width=4)
        d.arc((119, 71, 138, 100), 180, 360, fill=gold, width=4)
    return layer

def render_scene(scene, index, duration, narration, words, clip):
    """Render voice words with restrained center motion and soft dissolves."""
    if not Path(FONT_HINDI).exists():
        raise FileNotFoundError('Bundled Devanagari font is required')
    groups = caption_groups(readable_words(words))
    starts = [group[0]['start'] for group in groups]
    frames = math.ceil(duration * FPS)
    duration = frames / FPS
    base = background()
    layers = {(gi, shown): caption_layer(group, shown)
              for gi, group in enumerate(groups) for shown in range(1, len(group) + 1)}
    command = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
               '-s', '720x1280', '-r', str(FPS), '-i', '-', '-i', str(narration),
               '-frames:v', str(frames), '-t', str(duration),
               '-af', 'apad,loudnorm=I=-16:TP=-1.5:LRA=11', '-c:v', 'libx264',
               '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
               '-c:a', 'aac', '-ar', '44100', '-ac', '1', '-b:a', '128k', str(clip)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for frame in range(frames):
            t = frame / FPS
            image = base.copy().convert('RGBA')
            visual_index = (index + int(t / 3.5)) % len(VISUALS)
            cutout, cutout_position = visual_layer(visual_index, t, scene)
            image.alpha_composite(cutout, cutout_position)
            group_index = bisect.bisect_right(starts, t) - 1
            if group_index >= 0:
                group = groups[group_index]
                shown = min(len(group), bisect.bisect_right([word['start'] for word in group], t))
                if shown:
                    line = layers[group_index, shown]
                    start = group[0]['start']
                    next_start = starts[group_index + 1] if group_index + 1 < len(groups) else duration
                    age = max(0, t - start)
                    fade_in = min(1, age / .17)
                    fade_out = min(1, (next_start - t) / .19)
                    opacity = max(0, min(fade_in, fade_out))
                    shift = round(12 * (1 - fade_in) - 5 * (1 - fade_out))
                    if opacity < 1:
                        line = line.copy()
                        line.putalpha(line.getchannel('A').point(lambda value: round(value * opacity)))
                    image.alpha_composite(line, (35, 490 + shift))
            elif index == 0 and frame < 5:
                # A brief opening frame can also serve as the video cover.
                title = Image.new('RGBA', SIZE, (0, 0, 0, 0))
                d = ImageDraw.Draw(title)
                font = ImageFont.truetype(FONT_LATIN, 41)
                label = scene['question']
                d.text(((720 - d.textlength(label, font=font)) / 2, 630), label, fill=WHITE, font=font)
                image = Image.alpha_composite(image, title)
            process.stdin.write(image.convert('RGB').tobytes())
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError('Kinetic Reel render failed')
