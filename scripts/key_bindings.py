# SPDX-License-Identifier: GPL-2.0-or-later
"""Default keyboard and mouse bindings by action (bbport.ini key_<action>), shared by the launcher
and key_icons.py. src/runtime_pad.c holds the same table (actions[]): keep them in step.

A binding is an SDL key name ("Space", "Return", "Left Shift", "F"), Mouse1..Mouse5 or
WheelUp/WheelDown, optionally after Shift+, Ctrl+ or Alt+; '|' separates the bindings of one
action."""
from pathlib import Path

DEFAULTS = {
    'move_forward': 'W', 'move_back': 'S', 'move_left': 'A', 'move_right': 'D',
    'dodge_run': 'Space', 'jump': 'F',
    'attack': 'Mouse1', 'strong_attack': 'Shift+Mouse1|Mouse5', 'gun': 'Mouse2',
    'transform': 'Shift+Mouse2|Mouse4', 'lock_on': 'Q|Mouse3',
    'blood_vial': 'R', 'use_item': 'C',
    'dpad_up': 'Up|WheelUp', 'dpad_down': 'Down|WheelDown', 'dpad_left': 'Left', 'dpad_right': 'Right',
    'interact': 'E|Return', 'back': 'Backspace', 'menu': 'Escape', 'gestures': 'G', 'key_items': 'T',
    'camera_up': '', 'camera_down': '', 'camera_left': '', 'camera_right': '',
}


def load(ini):
    """{action: [bindings]} from the defaults and the key_<action> lines of `ini`."""
    values = dict(DEFAULTS)
    try:
        for line in Path(ini).read_text(encoding='utf-8', errors='replace').splitlines():
            key, sep, value = line.partition('=')
            if sep and key.startswith('key_') and key[4:] in values:
                values[key[4:]] = value.strip()
    except OSError:
        pass
    return {action: [b.strip() for b in value.split('|') if b.strip()] for action, value in values.items()}


def flag(ini, key, default='1'):
    """A 0/1 setting of bbport.ini."""
    try:
        for line in Path(ini).read_text(encoding='utf-8', errors='replace').splitlines():
            name, sep, value = line.partition('=')
            if sep and name.strip() == key:
                return value.strip() == '1'
    except OSError:
        pass
    return default == '1'
