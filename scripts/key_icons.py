#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Keyboard and mouse button prompts in the game: redraws the key-guide icons (KG_*) of the
game's menu/common.tpf.dcx from the current bindings (bbport.ini key_<action>) and writes the
archive as a mod layer for mods.py. The game files are not changed.

The icons are 32x32 BC7 textures stored in PS4 block order (Morton order of the 4x4 blocks).
Each one is drawn with Pillow, encoded as BC7 mode 6 and swizzled back; the TPF keeps its
layout (same sizes), only the DCX is compressed again. The result is cached by the bindings.

Usage: key_icons.py GAME_DIR --out OUT_DIR --config bbport.ini
Prints the mod folder (OUT_DIR/key_icons/<hash>) or nothing when there is nothing to do.
"""
import argparse
import hashlib
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import key_bindings  # noqa: E402

VERSION = 3  # bump when the output changes: invalidates the cache
ARCHIVE = Path('dvdroot_ps4/menu/common.tpf.dcx')

# Which action's first binding each icon shows (several: the first one that is bound).
ICONS = {
    'KG_Cancel': ['interact'],            # the cross button (confirm in this version)
    'KG_OK': ['back', 'dodge_run'],       # the circle button
    'KG_R_L': ['use_item'],               # square
    'KG_R_U': ['blood_vial'],             # triangle
    'KG_L1': ['transform'], 'KG_L2': ['gun'], 'KG_L3': ['jump'],
    'KG_R1': ['attack'], 'KG_R2': ['strong_attack'], 'KG_R3': ['lock_on'],
    'KG_Start': ['menu'], 'KG_TP_L': ['gestures'], 'KG_TP_R': ['key_items'],
    'KG_L_U': ['dpad_up'], 'KG_L_D': ['dpad_down'],
}
DPAD = {'KG_L_LR': ('dpad_left', 'dpad_right'), 'KG_L_UD': ('dpad_up', 'dpad_down'),
        'KG_L_UDLR': ('dpad_up', 'dpad_down', 'dpad_left', 'dpad_right')}
# The prompts in the world ("X Inspect") come from the HUD atlas MENU_Common_00091 (1024x512 BC7):
# 26x26 icons at (661,123) circle, (694,123) cross, (726,123) L3. Each is redrawn in a block-aligned
# rectangle that holds nothing else: (rectangle x0, y0, x1, y1), icon origin, size, actions.
HUD_ATLAS = 'MENU_Common_00091'
HUD = [((660, 120, 688, 152), (661, 123), 26, ['back', 'dodge_run']),
       ((692, 120, 724, 152), (694, 123), 26, ['interact']),
       ((724, 120, 756, 152), (726, 123), 26, ['jump'])]

# ---- archives ------------------------------------------------------------------------------------


def dcx_unpack(data):
    if data[:4] != b'DCX\0' or data[0x28:0x2C] != b'DFLT':
        raise ValueError('expected a DFLT DCX archive')
    i = data.find(b'DCA\0')
    size = struct.unpack('>I', data[i + 4:i + 8])[0]
    return data[:i + size], zlib.decompress(data[i + size:])


def dcx_pack(header, payload, limit):
    """The DCX with `payload` compressed, or None when it does not fit in `limit` bytes: the game
    refuses an archive whose compressed data is larger than the original's (FileTransferTask.cpp
    panic). zlib -9 is about 0.6% too big for common.tpf.dcx; libdeflate level 12 is smaller."""
    try:
        import deflate
        packed = deflate.zlib_compress(payload, 12)
    except ImportError:
        packed = zlib.compress(payload, 9)
    if len(packed) > limit:
        return None
    header = bytearray(header)
    struct.pack_into('>II', header, 0x1C, len(payload), len(packed))
    return bytes(header) + packed


def tpf_textures(data):
    """{name: (data offset, size, width, height, dxgi)} of a PS4 TPF."""
    if data[:4] != b'TPF\0' or data[12] != 4:
        raise ValueError('expected a PS4 TPF')
    count, encoding = struct.unpack_from('<I', data, 8)[0], data[14]
    textures, off = {}, 16
    for _ in range(count):
        data_off, size = struct.unpack_from('<Ii', data, off)
        width, height = struct.unpack_from('<HH', data, off + 12)
        name_off, has_float = struct.unpack_from('<Ii', data, off + 24)
        dxgi, = struct.unpack_from('<i', data, off + 32)
        off += 36
        if has_float == 1:
            off += 8 + struct.unpack_from('<i', data, off + 4)[0]
        if encoding == 1:
            end = name_off
            while data[end:end + 2] != b'\0\0':
                end += 2
            name = data[name_off:end].decode('utf-16-le')
        else:
            name = data[name_off:data.index(b'\0', name_off)].decode('shift_jis', 'replace')
        textures[name] = (data_off, size, width, height, dxgi)
    return textures

# ---- BC7 ------------------------------------------------------------------------------------------


WEIGHTS4 = [0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64]


def bc7_mode6(pixels):
    """One 4x4 block (16 RGBA tuples) as BC7 mode 6: one subset, RGBA 7.7.7.7 + p-bit endpoints,
    4-bit indices. Endpoints span the block along its principal axis."""
    n = len(pixels)
    mean = [sum(p[c] for p in pixels) / n for c in range(4)]
    cov = [[sum((p[a] - mean[a]) * (p[b] - mean[b]) for p in pixels) for b in range(4)] for a in range(4)]
    axis = [1.0, 1.0, 1.0, 1.0]
    for _ in range(12):
        v = [sum(cov[a][b] * axis[b] for b in range(4)) for a in range(4)]
        length = max(abs(x) for x in v)
        if length < 1e-9:
            break
        axis = [x / length for x in v]
    proj = [sum((p[c] - mean[c]) * axis[c] for c in range(4)) for p in pixels]
    lo, hi = min(proj), max(proj)
    norm = sum(a * a for a in axis) or 1.0
    e0 = [min(255, max(0, mean[c] + axis[c] * lo / norm)) for c in range(4)]
    e1 = [min(255, max(0, mean[c] + axis[c] * hi / norm)) for c in range(4)]
    best = None
    for p0 in (0, 1):
        for p1 in (0, 1):
            q0 = [min(127, max(0, round((v - p0) / 2))) for v in e0]
            q1 = [min(127, max(0, round((v - p1) / 2))) for v in e1]
            a = [q * 2 + p0 for q in q0]
            b = [q * 2 + p1 for q in q1]
            palette = [[((64 - w) * a[c] + w * b[c] + 32) >> 6 for c in range(4)] for w in WEIGHTS4]
            indices, error = [], 0
            for p in pixels:
                errs = [sum((p[c] - col[c]) ** 2 for c in range(4)) for col in palette]
                i = min(range(16), key=errs.__getitem__)
                indices.append(i)
                error += errs[i]
            if best is None or error < best[0]:
                best = (error, q0, q1, p0, p1, indices)
    _e, q0, q1, p0, p1, indices = best
    if indices[0] >= 8:  # the anchor index has no top bit: swap the endpoints
        q0, q1, p0, p1 = q1, q0, p1, p0
        indices = [15 - i for i in indices]
    bits, pos = 1 << 6, 7  # mode 6
    for c in range(4):
        for q in (q0[c], q1[c]):
            bits |= q << pos
            pos += 7
    bits |= p0 << pos | p1 << (pos + 1)
    pos += 2
    for k, i in enumerate(indices):
        width = 3 if k == 0 else 4
        bits |= i << pos
        pos += width
    return bits.to_bytes(16, 'little')


def morton(x, y):
    z = 0
    for i in range(8):
        z |= ((x >> i) & 1) << (2 * i) | ((y >> i) & 1) << (2 * i + 1)
    return z


def block_offset(bx, by, width_blocks):
    """Byte offset of a 4x4 block in a PS4 BC7 texture: 8x8-block tiles in rows, Morton order
    inside a tile (a 32x32 texture is one tile)."""
    tile = (by // 8) * (width_blocks // 8) + bx // 8
    return (tile * 64 + morton(bx % 8, by % 8)) * 16


def encode_region(data, width, image, x0, y0):
    """Writes `image` (RGBA, both sides multiples of 4) into the BC7 texture `data` at (x0, y0)."""
    px = image.load()
    for by in range(image.height // 4):
        for bx in range(image.width // 4):
            block = [px[bx * 4 + x, by * 4 + y] for y in range(4) for x in range(4)]
            o = block_offset(x0 // 4 + bx, y0 // 4 + by, width // 4)
            data[o:o + 16] = bc7_mode6(block)


def encode_icon(image):
    """A 32x32 RGBA Pillow image as PS4 BC7."""
    out = bytearray(1024)
    encode_region(out, 32, image, 0, 0)
    return bytes(out)

# ---- drawing ----------------------------------------------------------------------------------------


GOLD = (220, 188, 124, 255)
GOLD_DIM = (150, 126, 84, 255)
CAP = (34, 31, 29, 245)
CAP_RIM = (96, 86, 72, 255)
LIT = (190, 44, 44, 255)
SCALE = 4  # drawn at 128x128, scaled down for smooth edges
FONTS = ('segoeuib.ttf', 'arialbd.ttf', 'verdanab.ttf')
SYMBOL_FONTS = ('seguisym.ttf', 'segoeuib.ttf', 'arial.ttf')
SYMBOLS = {'Space': '␣', 'Return': '↵', 'Keypad Enter': '↵', 'Backspace': '⌫', 'Up': '↑', 'Down': '↓',
           'Left': '←', 'Right': '→', 'Left Shift': '⇧', 'Right Shift': '⇧'}
WORDS = {'Escape': 'Esc', 'Tab': 'Tab', 'Left Ctrl': 'Ctrl', 'Right Ctrl': 'Ctrl', 'Left Alt': 'Alt',
         'Right Alt': 'Alt', 'CapsLock': 'Caps', 'Delete': 'Del', 'Insert': 'Ins', 'PageUp': 'PgUp',
         'PageDown': 'PgDn', 'Home': 'Home', 'End': 'End'}


def font(names, size):
    from PIL import ImageFont
    for name in names:
        for folder in (Path(r'C:\Windows\Fonts'), Path('/usr/share/fonts/truetype/dejavu')):
            path = folder / name
            if path.is_file():
                return ImageFont.truetype(str(path), size)
    try:
        return ImageFont.truetype('DejaVuSans-Bold.ttf', size)
    except OSError:
        return ImageFont.load_default()


def text_center(draw, box, text, names, size, fill):
    x0, y0, x1, y1 = box
    while True:
        f = font(names, size)
        l, t, r, b = draw.textbbox((0, 0), text, font=f)
        if r - l <= (x1 - x0) or size <= 20:
            break
        size -= 4
    draw.text(((x0 + x1 - (r - l)) / 2 - l, (y0 + y1 - (b - t)) / 2 - t), text, font=f, fill=fill)


def keycap(draw, box=(6, 10, 122, 118)):
    draw.rounded_rectangle(box, radius=22, fill=CAP, outline=CAP_RIM, width=5)
    x0, y0, x1, _y1 = box
    draw.line((x0 + 20, y0 + 6, x1 - 20, y0 + 6), fill=(70, 64, 56, 255), width=3)


def mouse(draw, lit=None, box=(30, 6, 98, 122)):
    """A mouse seen from above; lit: 'left', 'right', 'middle', 'wheel' or None."""
    x0, y0, x1, y1 = box
    mid, split = (x0 + x1) // 2, y0 + (y1 - y0) * 0.42
    draw.rounded_rectangle(box, radius=30, fill=CAP, outline=GOLD_DIM, width=5)
    if lit in ('left', 'right'):
        part = (x0 + 5, y0 + 5, mid, split) if lit == 'left' else (mid, y0 + 5, x1 - 5, split)
        draw.rounded_rectangle(part, radius=22, fill=LIT)
    draw.line((mid, y0 + 4, mid, split), fill=GOLD_DIM, width=4)
    draw.line((x0 + 4, split, x1 - 4, split), fill=GOLD_DIM, width=4)
    wheel = (mid - 7, y0 + 18, mid + 7, y0 + 44)
    draw.rounded_rectangle(wheel, radius=7, fill=LIT if lit in ('middle', 'wheel') else GOLD)


def draw_binding(binding, pixels=32):
    """A pixels x pixels RGBA icon for one binding (key, mouse button or wheel, with a modifier)."""
    from PIL import Image, ImageDraw
    image = Image.new('RGBA', (32 * SCALE, 32 * SCALE), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    parts = binding.split('+')
    mods, name = [p for p in parts[:-1] if p in ('Shift', 'Ctrl', 'Alt')], parts[-1]
    if name.startswith('Mouse') or name.startswith('Wheel'):
        lit = {'Mouse1': 'left', 'Mouse2': 'right', 'Mouse3': 'middle', 'WheelUp': 'wheel',
               'WheelDown': 'wheel'}.get(name)
        mouse(d, lit, (40, 10, 104, 120) if mods else (30, 6, 98, 122))
        if name in ('Mouse4', 'Mouse5'):
            text_center(d, (36, 52, 92, 112), name[-1], FONTS, 52, GOLD)
        if name.startswith('Wheel'):
            text_center(d, (36, 60, 92, 118), '↑' if name == 'WheelUp' else '↓', SYMBOL_FONTS, 52, GOLD)
    else:
        keycap(d)
        label = SYMBOLS.get(name) or WORDS.get(name) or (name if len(name) <= 4 else name[:4])
        names = SYMBOL_FONTS if name in SYMBOLS else FONTS
        size = 84 if len(label) == 1 else 60 if len(label) == 2 else 44
        box = (14, 40, 114, 112) if mods else (12, 18, 116, 112)
        text_center(d, box, label, names, size, GOLD)
    if mods:
        badge = {'Shift': '⇧', 'Ctrl': 'Ctrl', 'Alt': 'Alt'}[mods[0]]
        d.rounded_rectangle((0, 0, 58 if badge == '⇧' else 74, 46), radius=12, fill=(120, 20, 24, 255),
                            outline=GOLD, width=3)
        text_center(d, (4, 2, 54 if badge == '⇧' else 70, 44), badge,
                    SYMBOL_FONTS if badge == '⇧' else FONTS, 40 if badge == '⇧' else 26, (250, 236, 210, 255))
    return image.resize((pixels, pixels), Image.LANCZOS)


def draw_text_icon(lines):
    """Several small key labels (WASD, arrow clusters) on one keycap."""
    from PIL import Image, ImageDraw
    image = Image.new('RGBA', (32 * SCALE, 32 * SCALE), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    keycap(d)
    if len(lines) == 1:
        text_center(d, (12, 26, 116, 104), lines[0], SYMBOL_FONTS, 60, GOLD)
    else:
        text_center(d, (12, 16, 116, 62), lines[0], SYMBOL_FONTS, 44, GOLD)
        text_center(d, (12, 60, 116, 110), lines[1], SYMBOL_FONTS, 44, GOLD)
    return image.resize((32, 32), Image.LANCZOS)


def short(binding):
    name = binding.split('+')[-1]
    return SYMBOLS.get(name) or WORDS.get(name) or name[:3]


def icons_for(bindings):
    """{texture name: 32x32 image} for the bindings ({action: [bindings]})."""
    first = {action: values[0] for action, values in bindings.items() if values}
    icons = {}
    for texture, actions in ICONS.items():
        binding = next((first[a] for a in actions if a in first), None)
        if binding:
            icons[texture] = draw_binding(binding)
    for texture, actions in DPAD.items():
        keys = [first.get(a) for a in actions]
        if not all(keys):
            continue
        labels = [short(k) for k in keys]
        if texture == 'KG_L_UDLR':
            icons[texture] = draw_text_icon([labels[0], labels[2] + labels[1] + labels[3]])
        else:
            icons[texture] = draw_text_icon([''.join(labels)])
    move = [first.get(a) for a in ('move_forward', 'move_left', 'move_back', 'move_right')]
    if all(move):
        labels = [short(k) for k in move]
        icons['KG_LS'] = draw_text_icon([labels[0], ''.join(labels[1:])])
    from PIL import Image, ImageDraw
    image = Image.new('RGBA', (32 * SCALE, 32 * SCALE), (0, 0, 0, 0))
    mouse(ImageDraw.Draw(image))
    icons['KG_RS'] = image.resize((32, 32), Image.LANCZOS)  # the camera is the mouse
    return icons

def patch_hud(payload, textures, bindings):
    """The world prompts in the HUD atlas; returns how many icons were drawn."""
    from PIL import Image
    if HUD_ATLAS not in textures:
        return 0
    offset, size, width, height, dxgi = textures[HUD_ATLAS]
    if (width, height, dxgi) != (1024, 512, 98) or size < width * height:
        return 0
    first = {action: values[0] for action, values in bindings.items() if values}
    atlas = bytearray(payload[offset:offset + width * height])
    drawn = 0
    for (x0, y0, x1, y1), (ix, iy), icon_size, actions in HUD:
        binding = next((first[a] for a in actions if a in first), None)
        if not binding:
            continue
        region = Image.new('RGBA', (x1 - x0, y1 - y0), (0, 0, 0, 0))
        region.alpha_composite(draw_binding(binding, icon_size).convert('RGBA'), (ix - x0, iy - y0))
        encode_region(atlas, width, region, x0, y0)
        drawn += 1
    payload[offset:offset + width * height] = atlas
    return drawn

# ---- main -------------------------------------------------------------------------------------------


def build(game, out, config):
    source = Path(game) / ARCHIVE
    if not source.is_file():
        return None
    bindings = key_bindings.load(config)
    stat = source.stat()
    key = hashlib.sha256(repr((VERSION, sorted(bindings.items()), stat.st_size, int(stat.st_mtime))).encode())
    folder = Path(out) / 'key_icons' / key.hexdigest()[:16]
    target = folder / ARCHIVE
    if target.is_file():
        return folder
    try:
        import PIL  # noqa: F401
    except ImportError:
        print('Key icons: Pillow is missing; the game shows the gamepad buttons', file=sys.stderr)
        return None
    original = source.read_bytes()
    header, payload = dcx_unpack(original)
    limit = len(original) - len(header)
    original_payload = payload
    payload = bytearray(payload)
    textures = tpf_textures(payload)
    replaced = 0
    for name, image in icons_for(bindings).items():
        if name not in textures:
            continue
        offset, size, width, height, dxgi = textures[name]
        if (width, height, dxgi) != (32, 32, 98) or size < 1024:
            continue
        if image.size != (32, 32):
            continue
        payload[offset:offset + 1024] = encode_icon(image.convert('RGBA'))
        replaced += 1
    replaced += patch_hud(payload, textures, bindings)
    # Older caches are dropped: only the current bindings are kept.
    if folder.parent.is_dir():
        import shutil
        for old in folder.parent.iterdir():
            if old != folder:
                shutil.rmtree(old, ignore_errors=True)
    if len(payload) != len(original_payload):
        raise ValueError('the archive layout changed; nothing written')
    packed = dcx_pack(header, bytes(payload), limit)
    if packed is None:
        print('Key icons: the archive does not compress below the original size (install the "deflate" '
              'module); the game shows the gamepad buttons', file=sys.stderr)
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix('.part')
    part.write_bytes(packed)
    part.replace(target)
    print(f'Key icons: {replaced} button prompts drawn for the keyboard and mouse', file=sys.stderr)
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('game', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--preview', type=Path, help='also write the icons as one PNG sheet')
    args = parser.parse_args()
    if not key_bindings.flag(args.config, 'key_icons'):
        return
    if args.preview:
        from PIL import Image
        icons = icons_for(key_bindings.load(args.config))
        sheet = Image.new('RGBA', (len(icons) * 136, 136), (24, 22, 22, 255))
        for i, (_name, image) in enumerate(sorted(icons.items())):
            sheet.alpha_composite(image.resize((128, 128), Image.NEAREST), (i * 136 + 4, 4))
        sheet.save(args.preview)
    folder = build(args.game, args.out, args.config)
    if folder:
        print(folder)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, struct.error, zlib.error) as error:
        print(f'Key icons: {error}', file=sys.stderr)
