"""Local OCR for user-supplied account-overview screenshots.

OCR output is a draft, never an instruction to change financial records.
Images live only for the duration of the request; there are no cloud calls.
"""
import csv
import io
import os
import re
import shutil
import subprocess
import threading
import warnings
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 8_000_000
MAX_PIXELS = 16_000_000
LOCK = threading.BoundedSemaphore(1)
AMOUNT = re.compile(r'(?<![\w.,])(?P<sign>[-−–]?\s*)(?:£|GBP)\s*(?P<after>[-−–]?\s*)(?P<number>(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2})(?![\d.,])', re.I)
SUMMARY = re.compile(r'\b(total|net worth|all accounts|available to spend|spent|spending|budget|income|cash flow|credit limit|overdraft limit)\b', re.I)
NO_LABEL = re.compile(r'^(accounts?|current accounts?|savings|credit cards?|balance|available|updated.*|last updated.*|today|yesterday|snoop\+?|home|overview|\d[\d :/.-]*)$', re.I)


class ScreenshotError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def executable():
    configured = os.environ.get('SMARTMONEY_TESSERACT')
    if configured:
        return shutil.which(configured)
    found = shutil.which('tesseract')
    if not found and os.name == 'nt':
        candidate = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Tesseract-OCR' / 'tesseract.exe'
        if candidate.is_file():
            found = str(candidate)
    return found


def read_lines(raw):
    # Reserve the whole decode/OCR operation, not just the subprocess. This keeps
    # concurrent uploads from decoding several large images on a 1 GB Pi.
    if not LOCK.acquire(blocking=False):
        raise ScreenshotError('Another screenshot is being read. Try again when it finishes.', 503)
    try:
        return _read_lines(raw)
    finally:
        LOCK.release()


def _read_lines(raw):
    if not raw or len(raw) > MAX_BYTES:
        raise ScreenshotError('Choose a PNG, JPEG or WebP screenshot smaller than 8 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ('PNG', 'JPEG', 'WEBP') or getattr(source, 'n_frames', 1) != 1:
                    raise ScreenshotError('Choose a single PNG, JPEG or WebP image.')
                if source.width * source.height > MAX_PIXELS or min(source.size) < 100:
                    raise ScreenshotError('Use an image at least 100 pixels wide/high and no larger than 16 megapixels.')
                source.load()
                # Resize before copying/converting; OCR never exceeds 2.88 MP.
                source.thumbnail((1200, 2400))
                gray = ImageOps.grayscale(ImageOps.exif_transpose(source))
                # Light text on dark screenshots becomes dark text on white.
                if gray.resize((1, 1)).getpixel((0, 0)) < 128:
                    gray = ImageOps.invert(gray)
                gray = ImageOps.autocontrast(gray)
                buffer = io.BytesIO()
                gray.save(buffer, format='PNG')
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ScreenshotError('This image could not be read safely. Export a normal screenshot as PNG or JPEG.') from None
    command = executable()
    if not command:
        raise ScreenshotError('Local OCR is not installed. On the Pi run: sudo apt install tesseract-ocr tesseract-ocr-eng', 503)
    try:
        result = subprocess.run([command, 'stdin', 'stdout', '-l', 'eng', '--psm', '11', 'tsv'],
                                input=buffer.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=45, check=False, env={**os.environ, 'OMP_THREAD_LIMIT': '1'},
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode:
            raise ScreenshotError('Local OCR failed. Check that Tesseract and its English language data are installed.', 503)
    except subprocess.TimeoutExpired:
        raise ScreenshotError('Reading took too long. Crop to a smaller group of accounts and try again.', 422) from None
    except OSError:
        raise ScreenshotError('Could not start local OCR. Check the Tesseract installation.', 503) from None
    groups = {}
    for word in csv.DictReader(io.StringIO(result.stdout.decode('utf-8', errors='replace')), delimiter='\t', quoting=csv.QUOTE_NONE):
        if word.get('level') != '5' or not word.get('text', '').strip():
            continue
        key = tuple(word.get(k) for k in ('page_num', 'block_num', 'par_num', 'line_num'))
        row = groups.setdefault(key, {'words': [], 'confidence': [], 'top': int(word['top']), 'height': int(word['height'])})
        row['words'].append({'text': word['text'], 'left': int(word['left']), 'width': int(word['width'])})
        row['confidence'].append(float(word['conf']))
        row['height'] = max(row['height'], int(word['height']))
    return sorted([{'text': ' '.join(w['text'] for w in row['words']), 'words': row['words'],
                    'left': min(w['left'] for w in row['words']),
                    'width': max(w['left'] + w['width'] for w in row['words']) - min(w['left'] for w in row['words']),
                    'confidence': round(min(row['confidence'])), 'top': row['top'], 'height': row['height']}
                   for row in groups.values()], key=lambda line: (line['top'], line['left']))


def positioned_candidates(lines):
    """Snoop carousel: bank logos, GBP amounts, then one/two-line nicknames.

    Use word boxes rather than OCR reading order to keep adjacent cards apart.
    Institution names are never inferred from logos or nicknames.
    """
    output, notices = [], []
    for line in lines:
        matches = list(AMOUNT.finditer(line['text']))
        if not matches:
            continue
        offsets, cursor = [], 0
        for word in line['words']:
            offsets.append((cursor, cursor + len(word['text']), word))
            cursor += len(word['text']) + 1
        for match in matches:
            words = [w for start, end, w in offsets if end > match.start() and start < match.end()]
            left = min(w['left'] for w in words)
            right = max(w['left'] + w['width'] for w in words)
            output.append({'line': line, 'match': match, 'left': left, 'right': right, 'center': (left + right) / 2})
    # Partially clipped cards still delimit neighbouring columns, even though
    # their incomplete amounts must never be offered as balances.
    anchors = list(output)
    for line in lines:
        if not AMOUNT.search(line['text']) and re.search(r'(?:£|GBP)\s*\d', line['text'], re.I):
            anchors.append({'line': line, 'center': line['left'] + line['width'] / 2})
            notices.append('An incomplete or unclear GBP amount was skipped. Include the whole account card in your screenshot.')
    candidates = []
    for amount in output:
        line, match = amount['line'], amount['match']
        peers = [a for a in anchors if abs(a['line']['top'] - line['top']) <= max(line['height'], a['line']['height'])]
        before = [a['center'] for a in peers if a['center'] < amount['center']]
        after = [a['center'] for a in peers if a['center'] > amount['center']]
        lo = (max(before) + amount['center']) / 2 if before else amount['left'] - 45
        hi = (min(after) + amount['center']) / 2 if after else amount['right'] + 45
        below = []
        for other in lines:
            gap = other['top'] - (line['top'] + line['height'])
            if not 0 <= gap <= max(90, line['height'] * 5):
                continue
            chosen = [w['text'] for w in other['words'] if lo <= w['left'] + w['width'] / 2 <= hi]
            text = ' '.join(chosen).strip()
            if text and SUMMARY.search(other['text']):
                # A spending caption can be wider than the amount above it.
                # Keep its full meaning instead of mistaking just "March" for
                # an account nickname when the rest falls outside the column.
                text = other['text']
            if re.search(r'[a-zA-Z]', text) and not AMOUNT.search(text) and (not NO_LABEL.fullmatch(text) or (below and text.lower() == 'account')):
                below.append(text)
        same = AMOUNT.sub('', line['text']).strip(' :|()−–-') if len(list(AMOUNT.finditer(line['text']))) == 1 else ''
        label = same if same and not NO_LABEL.fullmatch(same) else ' '.join(below[:2])
        # Vertical lists sometimes place the account name immediately above.
        if not label:
            above = [other for other in lines if 0 < line['top'] - other['top'] <= max(65, line['height'] * 3)
                     and abs(other['left'] + other['width'] / 2 - amount['center']) < 65
                     and not AMOUNT.search(other['text']) and not NO_LABEL.fullmatch(other['text'])]
            if above:
                label = max(above, key=lambda other: other['top'])['text']
        if SUMMARY.search(label):
            notices.append('An apparent total, budget or spending summary was excluded.')
            continue
        sign = -1 if (match['sign'] + match['after']).strip() else 1
        if '(' in line['text'][:match.start()+1] and ')' in line['text'][match.end():]:
            sign = -1
        balance = Decimal(match['number'].replace(',', '')) * sign
        if abs(balance) > 1_000_000_000:
            continue
        candidates.append({'label': label[:80], 'balance': format(balance, '.2f'),
                           'context': (match.group().strip() + ' | ' + label)[:300], 'confidence': line['confidence']})
    if any(re.search(r'[€$]|\b(EUR|USD)\b', line['text'], re.I) for line in lines):
        notices.append('Non-GBP figures were not imported. This reader supports GBP only.')
    if len(candidates) > 60:
        notices.append('Preview limited to 60 balances. Crop the screenshot for more accounts.')
    if not candidates:
        notices.append('No clear GBP balances found. Try a cropped account overview, or add a row manually.')
    return {'candidates': candidates[:60], 'notices': list(dict.fromkeys(notices)),
            'text': '\n'.join(line['text'] for line in lines)[:20000]}


def interpret(lines):
    return positioned_candidates(lines)
