"""Voice-led Business Jalwa Reel visuals; no carousel art appears in the video."""
import bisect
import json
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = (720, 1280)
FPS = 24
GREEN = (22, 61, 48)
RUST = (177, 70, 32)
CREAM = (248, 242, 225)
GOLD = (237, 180, 83)
WHITE = (255, 252, 243)
FONT_LATIN = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_HINDI = str(Path(__file__).resolve().parents[1] / 'assets/fonts/NotoSansDevanagari.ttf')


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


def caption_groups(words):
    """Keep the spoken caption in short, easy-to-read chunks."""
    groups = []
    for index, word in enumerate(words):
        if not groups or len(groups[-1]) >= 3 or sum(len(w['text']) for w in groups[-1]) + len(word['text']) > 22:
            groups.append([])
        groups[-1].append(word)
        if word['text'].endswith(('।', '?', '!', '.')):
            groups.append([])
    return [group for group in groups if group]


def fit_lines(draw, text, path, width, height, maximum, minimum):
    for size in range(maximum, minimum - 1, -2):
        font = ImageFont.truetype(path, size)
        lines = []
        for paragraph in text.splitlines():
            current = ''
            for word in paragraph.split():
                candidate = (current + ' ' + word).strip()
                if current and draw.textlength(candidate, font=font) > width:
                    lines.append(current)
                    current = word
                else:
                    current = candidate
            if current:
                lines.append(current)
        if lines and len(lines) * (size + 10) <= height and all(draw.textlength(line, font=font) <= width for line in lines):
            return lines, font, size
    raise ValueError('Shorten Reel question or answer text')


def draw_words(draw, group, t, x, top, width, foreground, accent):
    font = ImageFont.truetype(FONT_HINDI, 49)
    # Break on measured glyph width; RAQM shapes Devanagari conjuncts correctly.
    rows = [[]]
    for word in group:
        candidate = ' '.join(w['text'] for w in rows[-1] + [word])
        if rows[-1] and draw.textlength(candidate, font=font) > width:
            rows.append([word])
        else:
            rows[-1].append(word)
    height = 65 * len(rows)
    y = top + (180 - height) // 2
    for row in rows:
        line = ' '.join(w['text'] for w in row)
        cursor = x + (width - draw.textlength(line, font=font)) / 2
        for word in row:
            active = word['start'] <= t < word['end'] + .08
            ink = accent if active else foreground
            draw.text((round(cursor), y), word['text'], font=font, fill=ink, stroke_width=0)
            measured = draw.textlength(word['text'], font=font)
            if active:
                draw.rounded_rectangle((round(cursor), y + 60, round(cursor + measured), y + 65), radius=2, fill=accent)
            cursor += measured + draw.textlength(' ', font=font)
        y += 65


def render_scene(scene, index, duration, narration, words, clip):
    """Draw an original kinetic typography scene at the voice's word timestamps."""
    if not Path(FONT_HINDI).exists():
        raise FileNotFoundError('Bundled Devanagari font is required')
    groups = caption_groups(words)
    starts = [group[0]['start'] for group in groups]
    frames = math.ceil(duration * FPS)
    duration = frames / FPS
    dark = index % 2 == 0
    background = GREEN if dark else CREAM
    ink = CREAM if dark else GREEN
    panel = (35, 81, 68) if dark else WHITE
    card_ink = WHITE if dark else GREEN
    base = Image.new('RGB', SIZE, background)
    base_draw = ImageDraw.Draw(base)
    for j in range(50):
        x = (j * 139 + 47) % 720
        y = (j * 211 + 138) % 1160
        base_draw.ellipse((x, y, x + 2, y + 2), fill=(67, 104, 87) if dark else (225, 208, 177))
    headline, headline_font, head_size = fit_lines(base_draw, scene['question'], FONT_LATIN, 595, 210, 54, 34)
    takeaway, takeaway_font, takeaway_size = fit_lines(base_draw, scene['answer'], FONT_LATIN, 570, 132, 30, 20)
    command = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
               '-s', '720x1280', '-r', str(FPS), '-i', '-', '-i', str(narration),
               '-frames:v', str(frames), '-t', str(duration),
               '-af', 'apad,loudnorm=I=-16:TP=-1.5:LRA=11', '-c:v', 'libx264',
               '-preset', 'veryfast', '-crf', '21', '-pix_fmt', 'yuv420p',
               '-c:a', 'aac', '-ar', '44100', '-ac', '1', '-b:a', '128k', str(clip)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for frame in range(frames):
            t = frame / FPS
            progress = frame / max(1, frames - 1)
            image = base.copy()
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((43, 65, 286, 104), radius=18, fill=RUST)
            draw.text((59, 73), 'BUSINESS JALWA', font=ImageFont.truetype(FONT_LATIN, 16), fill=WHITE)
            draw.text((613, 73), f'{index + 1:02}/05', font=ImageFont.truetype(FONT_LATIN, 17), fill=ink)
            draw.text((45, 156), 'BUSINESS, SIMPLY EXPLAINED', font=ImageFont.truetype(FONT_LATIN, 16), fill=GOLD if dark else RUST)
            reveal = min(1, t / .4)
            reveal = 1 - (1 - reveal) ** 3
            y = 238 + round(24 * (1 - reveal))
            draw.rounded_rectangle((45, y, 51, y + min(155, len(headline) * (head_size + 10))), radius=3, fill=GOLD if dark else RUST)
            draw.multiline_text((72, y - 8), '\n'.join(headline), font=headline_font, spacing=10, fill=ink)
            # Animated outline, counter, and accent bars keep a steady visual beat.
            angle = t * .45
            cx = 594 + 15 * math.sin(angle)
            cy = 428 + 9 * math.cos(angle)
            draw.ellipse((cx - 55, cy - 55, cx + 55, cy + 55), outline=RUST if not dark else GOLD, width=3)
            draw.ellipse((cx - 33, cy - 33, cx + 33, cy + 33), outline=RUST if not dark else GOLD, width=2)
            draw.rounded_rectangle((45, 510, 675, 805), radius=28, fill=panel)
            draw.text((77, 541), 'SUNO • SAMJHO', font=ImageFont.truetype(FONT_LATIN, 17), fill=GOLD if dark else RUST)
            selected = bisect.bisect_right(starts, t) - 1
            if selected >= 0:
                group = groups[selected]
                elapsed = max(0, t - group[0]['start'])
                rise = round(20 * (1 - min(1, elapsed / .22)) ** 2)
                draw_words(draw, group, t, 75, 585 + rise, 570, card_ink, GOLD if dark else RUST)
            for bar in range(5):
                bottom = 886
                maximum = 22 + (bar * 31 % 64)
                wave = .5 + .5 * math.sin(t * 2.8 - bar * .8)
                height = maximum * (.5 + .5 * wave)
                x = 52 + bar * 30
                draw.rounded_rectangle((x, bottom - height, x + 14, bottom), radius=5, fill=GOLD if dark else RUST)
            answer_delay = max(2.1, duration * .54)
            if t >= answer_delay:
                amount = min(1, (t - answer_delay) / .42)
                amount = 1 - (1 - amount) ** 3
                offset = round(19 * (1 - amount))
                draw.rounded_rectangle((45, 912 + offset, 675, 1120 + offset), radius=23, fill=CREAM if dark else GREEN)
                draw.text((71, 935 + offset), 'TAKEAWAY', font=ImageFont.truetype(FONT_LATIN, 16), fill=RUST if dark else GOLD)
                draw.multiline_text((71, 971 + offset), '\n'.join(takeaway), font=takeaway_font,
                                    fill=GREEN if dark else WHITE, spacing=10)
            draw.rounded_rectangle((45, 1167, 675, 1176), radius=4, fill=(91, 121, 102) if dark else (225, 209, 181))
            draw.rounded_rectangle((45, 1167, 45 + round(630 * (index + progress) / 5), 1176),
                                   radius=4, fill=GOLD if dark else RUST)
            draw.text((47, 1192), 'Business Jalwa • Save this lesson', font=ImageFont.truetype(FONT_LATIN, 15), fill=ink)
            process.stdin.write(image.tobytes())
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError('Kinetic Reel render failed')
