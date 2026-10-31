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
