# SPDX-License-Identifier: GPL-2.0-or-later
"""The Windows launcher's window as a web page (pywebview on WebView2): launcher/web/.

bbport_launcher_win.py keeps everything the launcher does (settings files, the game process,
mods, updates, Steam); this module only exposes it to the page. The pages are described here as
data (describe()), so every label, hint and translation stays in Python with the rest of the
launcher's texts, and the page draws them. Without pywebview or WebView2 the Tkinter window of
bbport_launcher_win.py opens instead.
"""
import base64
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import webbrowser

import bbport_launcher_win as core
from bbport_launcher_win import _

WEB_DIR = (Path(sys._MEIPASS) / 'web') if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS') \
    else Path(__file__).resolve().parent / 'web'
MOUSE_RANGE = (0.1, 5.0)


def options(pairs):
    return [[value, _(*text)] for value, text in pairs]


class Api:
    """Called from the page (window.pywebview.api.*), each call on its own thread."""

    def __init__(self):
        self._window = None
        self._lock = threading.RLock()
        self.app = {**core.APP_DEFAULTS, **core.load_json(core.CONFIG_FILE, {})}
        self.ini, self.ini_lines = core.load_ini()
        self._process = self._job = None
        self._log = queue.Queue()
        self.status_text = ''
        self.gpu_text = _('• Checking the graphics card…', '• Проверка видеокарты…')
        self.update = None          # (version, url, page) when a newer release exists
        self.update_state = ''
        self.fsr4_busy = False
        self.mod_order, self.mod_enabled, self.patch_enabled = [], {}, {}
        threading.Thread(target=self.detect_gpu, daemon=True).start()
        if self.app.get('check_updates', True) and not core.COOP_TEST:
            threading.Thread(target=self.find_update, daemon=True).start()

    # ---- settings ------------------------------------------------------------------------------
    def value(self, key, store):
        if store == 'ini':
            value = self.ini.get(key, core.INI_DEFAULTS.get(key, ''))
            if key in core.INI_FLAGS:
                return value == '1'
            if key in ('sharpness', 'mouse_sensitivity'):
                try:
                    return float(value)
                except ValueError:
                    return float(core.INI_DEFAULTS[key])
            return value
        return self.app.get(key, core.APP_DEFAULTS.get(key))

    def set(self, key, store, value):
        with self._lock:
            if store == 'ini':
                if key in core.INI_FLAGS:
                    self.ini[key] = '1' if value else '0'
                elif key in ('sharpness', 'mouse_sensitivity'):
                    self.ini[key] = f'{float(value):.2f}'
                else:
                    self.ini[key] = str(value)
            else:
                self.app[key] = value
            # Enemy control and the free camera share their buttons: one at a time.
            changed = {}
            if key == 'cheat_enemy_control' and value:
                self.ini['debug_camera'] = '0'
                changed['ini:debug_camera'] = False
            elif key == 'debug_camera' and value:
                self.ini['cheat_enemy_control'] = '0'
                changed['ini:cheat_enemy_control'] = False
            self.save()
            if key == 'ui_language':
                # Every text comes from Python: the page is drawn again in the new language.
                core.LANG = value or core.windows_language()
                return {'reload': True}
        return {'changed': changed, 'state': self.state()}

    def save(self):
        """settings.json, bbport.ini, mods.json and patches.json."""
        with self._lock:
            core.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            core.CONFIG_FILE.write_text(json.dumps(self.app, indent=2, ensure_ascii=False), encoding='utf-8')
            core.save_ini({key: self.ini.get(key, core.INI_DEFAULTS[key]) for key in core.INI_DEFAULTS},
                          self.ini_lines)
            self.ini, self.ini_lines = core.load_ini()
            if self.mod_order:
                (core.DATA_DIR / 'mods.json').write_text(json.dumps(
                    {'order': self.mod_order, 'disabled': [n for n in self.mod_order if not self.mod_enabled.get(n, True)]},
                    indent=2), encoding='utf-8')
            if self.patch_enabled:
                chosen = core.load_json(core.DATA_DIR / 'patches.json', {})
                shown = set(self.patch_enabled)
                enabled = {k for k in chosen.get('enabled', []) if k not in shown} | \
                    {k for k, on in self.patch_enabled.items() if on}
                disabled = {k for k in chosen.get('disabled', []) if k not in shown} | \
                    {k for k, on in self.patch_enabled.items() if not on}
                (core.DATA_DIR / 'patches.json').write_text(json.dumps(
                    {'enabled': sorted(enabled), 'disabled': sorted(disabled)}, indent=2), encoding='utf-8')

    # ---- what the page shows -------------------------------------------------------------------
    def init(self):
        values = {}
        for page in self.describe():
            for item in page['items']:
                if 'key' in item:
                    values[f"{item['store']}:{item['key']}"] = self.value(item['key'], item['store'])
                for group in item.get('groups', []):
                    for action in group['actions']:
                        values[f"ini:{action['key']}"] = self.value(action['key'], 'ini')
        for key in ('fps_mode', 'upscaler', 'preset', 'output_res', 'fullscreen', 'online'):
            store = 'app' if key in core.APP_DEFAULTS else 'ini'
            values[f'{store}:{key}'] = self.value(key, store)
        return {
            'version': core.VERSION, 'lang': core.LANG, 'pages': self.describe(), 'values': values,
            'quick': self.quick(), 'state': self.state(), 'art': self.cover_art(),
            'text': {
                'play': _('PLAY', 'ИГРАТЬ'), 'stop': _('Stop', 'Остановить'),
                'by': _('by giahoki'), 'subtitle': _('native port · Windows', 'нативный порт · Windows'),
                'insert': _("In the game: Insert opens the port's menu\n(gamepad: press both sticks).",
                            'В игре: Insert открывает меню порта\n(геймпад: нажать оба стика).'),
                'ready': _('Ready check', 'Проверка'), 'quick': _('Quick settings', 'Основное'),
                'copy': _('Copy', 'Копировать'), 'clear': _('Clear', 'Очистить'),
                'browse': _('Browse…', 'Обзор…'), 'open': _('Open', 'Открыть'),
                'update': _('Update', 'Обновить'), 'whatsnew': _("What's new", 'Что нового'),
                'refresh': _('Refresh', 'Обновить'), 'checking': _('Checking…'),
                'later_note': _('Lower in the list loads later and wins conflicts.',
                                'Ниже в списке — загружается позже и перекрывает.'),
            },
        }

    def quick(self):
        return [
            {'t': 'choice', 'key': 'fps_mode', 'store': 'app', 'label': _('Frame rate', 'Частота кадров'),
             'options': options(core.FPS_MODES)},
            {'t': 'choice', 'key': 'upscaler', 'store': 'ini', 'label': _('Upscaler', 'Апскейлер'),
             'options': options(core.UPSCALERS)},
            {'t': 'choice', 'key': 'preset', 'store': 'ini', 'label': _('Preset', 'Пресет'),
             'options': options(core.PRESETS)},
            {'t': 'choice', 'key': 'output_res', 'store': 'ini', 'label': _('Output', 'Разрешение'),
             'options': options(core.OUTPUTS)},
            {'t': 'slider', 'key': 'mouse_sensitivity', 'store': 'ini', 'label': _('Mouse', 'Мышь'),
             'min': MOUSE_RANGE[0], 'max': MOUSE_RANGE[1], 'step': 0.05},
            {'t': 'check', 'key': 'fullscreen', 'store': 'app', 'label': _('Fullscreen', 'Полный экран')},
            {'t': 'check', 'key': 'online', 'store': 'app', 'label': _('Play online')},
        ]

    def describe(self):
        def choice(key, store, label, pairs, hint=None):
            return {'t': 'choice', 'key': key, 'store': store, 'label': label, 'options': options(pairs), 'hint': hint}

        def check(key, store, label, hint=None):
            return {'t': 'check', 'key': key, 'store': store, 'label': label, 'hint': hint}

        def entry(key, label, hint=None, secret=False):
            return {'t': 'entry', 'key': key, 'store': 'app', 'label': label, 'hint': hint, 'secret': secret}

        def folder(key, label, hint=None):
            return {'t': 'folder', 'key': key, 'store': 'app', 'label': label, 'hint': hint}

        def section(label):
            return {'t': 'section', 'label': label}

        def note(text):
            return {'t': 'note', 'text': text}

        def buttons(*items):
            return {'t': 'buttons', 'items': [[label, action] for label, action in items]}

        warn = {'t': 'warn'}
        D = core.DATA_DIR
        pages = [
            {'id': 'graphics', 'title': _('Graphics', 'Графика'),
             'subtitle': _('Stored in bbport.ini; the in-game menu (Insert) changes the same values.',
                           'Хранится в bbport.ini; в игре меняется через меню (Insert).'),
             'items': [
                 section(_('Upscaling', 'Апскейлинг')),
                 choice('upscaler', 'ini', _('Upscaler', 'Апскейлер'), core.UPSCALERS,
                        _("Temporal upscaling with the game's own motion vectors. FSR 4 needs its assets (below) and "
                          'a GPU with INT8 dot products; otherwise the game falls back to FSR 3.1 by itself.',
                          'Временной апскейлинг с векторами движения игры. FSR 4 нужны ассеты (ниже) и GPU с INT8; '
                          'иначе игра сама переключится на FSR 3.1.')),
                 choice('preset', 'ini', _('Quality preset', 'Пресет'), core.PRESETS,
                        _('Render scale per axis: Quality renders at 1/1.5 of the output size.',
                          'Масштаб рендера по каждой оси: Quality рисует в 1/1.5 размера вывода.')),
                 choice('output_res', 'ini', _('Output resolution', 'Разрешение вывода'), core.OUTPUTS,
                        _('What the upscaler produces; the HUD is drawn at this size too.',
                          'Что выдаёт апскейлер; интерфейс рисуется в этом же размере.')),
                 choice('live_resolution', 'ini', _('Live resolution changes', 'Смена разрешения на лету'), core.LIVE,
                        _('Off: outputs other than 1080p are set by a patch at start (fastest; changing them in the '
                          'game restarts it). On: change output and preset in the game without a restart, at a cost.',
                          'Выкл.: разрешения кроме 1080p задаются патчем при запуске (быстрее). Вкл.: менять в игре '
                          'без перезапуска, но медленнее.')),
                 check('sharpen', 'ini', _('Sharpening (RCAS)', 'Резкость (RCAS)')),
                 {'t': 'slider', 'key': 'sharpness', 'store': 'ini', 'label': _('Sharpness', 'Сила резкости'),
                  'min': 0.0, 'max': 2.0, 'step': 0.05},
                 check('object_motion', 'ini', _('Object motion vectors', 'Векторы движения объектов'),
                       _('Less ghosting on characters, cloth and weapons; costs about 10% FPS.',
                         'Меньше гостинга на персонажах и одежде; стоит около 10% FPS.')),
                 section(_('FSR 4 assets', 'Ассеты FSR 4')),
                 {'t': 'fsr4', 'label': _('Download FSR 4 assets', 'Скачать ассеты FSR 4')},
                 note(_("From FireBurn/Q2RTX on GitHub (built from AMD's MIT-licensed FidelityFX source), "
                        'about 30 MB, into the fsr4_shaders folder of the port.',
                        'С GitHub FireBurn/Q2RTX (собраны из MIT-исходников AMD FidelityFX), около 30 МБ, '
                        'в папку fsr4_shaders порта.')),
                 section(_('Detail', 'Детализация')),
                 choice('model_lod', 'ini', _('Model detail (LOD)', 'Детализация моделей'), core.LODS,
                        _('A game patch (game version 1.09).', 'Патч игры (версия 1.09).')),
                 check('show_fps', 'ini', _('Show the FPS counter', 'Показывать FPS')),
             ]},
            {'id': 'display', 'title': _('Display & FPS', 'Экран и FPS'),
             'subtitle': _('Applied when the game starts.', 'Применяется при запуске игры.'),
             'items': [
                 warn,
                 section(_('Frame rate', 'Частота кадров')),
                 choice('fps_mode', 'app', _('Frame rate', 'Режим'), core.FPS_MODES,
                        _("Community patches for game version 1.09. Unlocked makes the game use the real frame time. "
                          'Other game versions always run at 30 FPS (the patches would corrupt them).',
                          'Патчи сообщества для версии 1.09. «Без ограничения» — игра использует реальное время кадра. '
                          'Другие версии всегда работают в 30 FPS.')),
                 choice('frame_cap', 'app', _('Frame cap (unlocked mode)', 'Ограничение FPS (режим без ограничения)'),
                        core.FRAME_CAPS,
                        _("Above about 120 FPS the game's movement timing breaks (running and rolling get slower, "
                          'physics and animations can glitch): higher caps are at your own risk.',
                          'Выше ~120 FPS ломается тайминг движения игры (бег и перекаты замедляются, возможны '
                          'сбои физики и анимаций): более высокие значения — на ваш риск.')),
                 choice('frames_ahead', 'app', _('Frames ahead of the GPU', 'Кадров впереди GPU'), core.FRAMES_AHEAD,
                        _('1 keeps frame pacing even; more can raise FPS when the graphics card is the limit.',
                          '1 — ровная подача кадров; больше может поднять FPS, если упирается в видеокарту.')),
                 section(_('Window', 'Окно')),
                 check('fullscreen', 'app', _('Fullscreen', 'Полноэкранный режим')),
                 choice('present_mode', 'app', _('Presentation', 'Режим показа кадров'), core.PRESENT_MODES),
                 check('hdr', 'app', _('Allow HDR output', 'Разрешить HDR'),
                       _('When HDR is on in Windows and the display supports it.',
                         'Если HDR включён в Windows и монитор его поддерживает.')),
             ]},
            {'id': 'controls', 'title': _('Controls', 'Управление'),
             'subtitle': _('Mouse and keyboard. The in-game menu (Insert) changes the mouse speed too.',
                           'Мышь и клавиатура. Скорость мыши меняется и в меню игры (Insert).'),
             'items': [
                 section(_('Mouse', 'Мышь')),
                 {'t': 'slider', 'key': 'mouse_sensitivity', 'store': 'ini',
                  'label': _('Mouse sensitivity', 'Чувствительность мыши'),
                  'min': MOUSE_RANGE[0], 'max': MOUSE_RANGE[1], 'step': 0.05,
                  'hint': _('The mouse turns the camera directly, without the stick\'s acceleration.',
                            'Мышь поворачивает камеру напрямую, без ускорения стика.')},
                 section(_('Cursor and port keys', 'Курсор и клавиши порта')),
                 {'t': 'keys', 'rows': [
                     [_('Left Alt (hold)', 'Левый Alt (удерживать)'),
                      _('Shows the mouse cursor and lets it leave the game window; release to aim again.',
                        'Показывает курсор мыши, им можно выйти из окна игры; отпустите — и снова управляете камерой.')],
                     ['F10', _('Turns the mouse camera off and on (the cursor stays free while it is off).',
                               'Выключает и включает камеру мышью (пока выключена, курсор свободен).')],
                     ['Insert', _('Opens the port\'s settings menu in the game (gamepad: press both sticks).',
                                  'Открывает меню настроек порта в игре (геймпад: нажать оба стика).')],
                 ]},
                 section(_('Keyboard and mouse', 'Клавиатура и мышь')),
                 check('key_icons', 'ini', _("Keyboard and mouse keys in the game's button prompts",
                                             'Клавиши клавиатуры и мыши в подсказках игры'),
                       _('Instead of the gamepad buttons (cross, circle, …) the game shows your bindings. Drawn '
                         'when the game starts; turn it off if you play with a gamepad.',
                         'Вместо кнопок геймпада (крестик, кружок, …) игра показывает ваши клавиши. Рисуются '
                         'при запуске игры; выключите, если играете на геймпаде.')),
                 note(_('Click a box and press a key or a mouse button; hold Shift, Ctrl or Alt for a combination. '
                        'Each action takes two bindings; a binding with Shift wins over the same button alone. '
                        'Changes apply at once, also while the game runs.',
                        'Нажмите на поле и затем клавишу или кнопку мыши; с Shift, Ctrl или Alt получится сочетание. '
                        'У каждого действия две привязки; привязка с Shift важнее той же кнопки без него. '
                        'Изменения применяются сразу, даже во время игры.')),
                 {'t': 'bindings', 'groups': [
                     {'title': _(*group), 'actions': [
                         {'key': f'key_{action}', 'label': _(*label), 'default': default}
                         for action, label, default in items]}
                     for group, items in core.KEY_BINDINGS]},
                 buttons((_('Reset to defaults', 'Сбросить по умолчанию'), 'reset_keys')),
                 note(_('Left Alt, F10, Insert and F9 are taken by the port and cannot be bound. A connected '
                        'gamepad keeps working next to the keyboard.',
                        'Левый Alt, F10, Insert и F9 заняты портом, назначить их нельзя. Подключённый геймпад '
                        'работает вместе с клавиатурой.')),
             ]},
            {'id': 'game', 'title': _('Game & effects', 'Игра и эффекты'),
             'subtitle': _('Your game dump, saves and the game patches.', 'Дамп игры, сохранения и патчи игры.'),
             'items': [
                 section(_('Game', 'Игра')),
                 folder('game_dir', _('Game folder', 'Папка игры'),
                        _('Your own dump of CUSA03173 (eboot.bin, sce_module, sce_sys, dvdroot_ps4); version 1.09 '
                          'for the community patches.', 'Ваш дамп CUSA03173 (eboot.bin, sce_module, sce_sys, '
                          'dvdroot_ps4); версия 1.09 для патчей сообщества.')),
                 folder('user_dir', _('Saves folder', 'Папка сохранений'),
                        _('Empty: {} (shader caches are kept there too).',
                          'Пусто: {} (там же кэш шейдеров).').format(D / 'user')),
                 choice('language', 'app', _('Game language', 'Язык игры'), core.LANGUAGES),
                 entry('player_name', _('Player name', 'Имя игрока'),
                       _('Where the game shows the PSN name; empty: the default.', 'Где игра показывает имя PSN; пусто — по умолчанию.')),
                 section(_('Effects', 'Эффекты')),
                 warn,
                 *[check(key, 'ini', _(*title)) for key, title, _on in core.EFFECTS],
                 section(_('Extras', 'Дополнительно')),
                 *[check(key, 'ini', _(*title)) for key, title, _on in core.EXTRAS],
                 note(_('Effects and extras are game patches for version 1.09, applied at start.',
                        'Эффекты и дополнения — патчи игры для версии 1.09, применяются при запуске.')),
             ]},
            {'id': 'cheats', 'title': _('Cheats', 'Читы'),
             'subtitle': _('Game patches for version 1.09, applied at start. Leave them off for a normal '
                           'play-through.', 'Патчи игры для версии 1.09, применяются при запуске. Для обычного '
                           'прохождения оставьте их выключенными.'),
             'items': [
                 warn,
                 section(_('Cheats', 'Читы')),
                 *[check(key, 'ini', _(*title)) for key, title, _on in core.CHEATS],
                 section(_('Gameplay tweaks', 'Изменения игрового процесса')),
                 *[check(key, 'ini', _(*title)) for key, title, _on in core.TWEAKS],
             ]},
            {'id': 'online', 'title': _('Online co-op'),
             'subtitle': _("Messages, bloodstains and ghosts come from The Hunter's Dream; bells and summons "
                           'go through a shadNet server.'),
             'items': [
                 check('online', 'app', _('Play online'), _('Off: the game stays offline, as before.')),
                 section(_('Game server (messages, bloodstains, ghosts)')),
                 entry('online_community', _('Game server'),
                       _('The Hunter\'s Dream by default. Only the name is needed; the game picks the ports.')),
                 section(_('Co-op server (bells and summons)')),
                 entry('online_server', _('Server address'),
                       _('srv.shadps4.net:31313 is the public shadPS4 server. For a private server, enter '
                         'host:port from the person who runs it.')),
                 entry('online_webapi', _('WebAPI address'),
                       _('Of the shadNet server, not the game server. Leave empty: the server address with '
                         'port 31315 is used.')),
                 section(_('Account')),
                 entry('online_npid', _('Online ID (NPID)'),
                       _('Your shadNet account name, not your email. Register one at shadnet.shadps4.net, or ask the '
                         'owner of a private server.')),
                 entry('online_password', _('Password'), _('Saved on this PC with the other launcher settings.'),
                       secret=True),
                 section(_('Connection')),
                 check('online_upnp', 'app', _('UPnP (open a port on the router automatically)'),
                       _('Turn it off on Tailscale or another VPN.')),
                 {'t': 'online_test', 'label': _('Test connection')},
                 note(_('Everyone in a session needs the same game version (1.09) and the same server. '
                        'Cheats change the game for the other players too: turn them off when you play together.')),
             ]},
            {'id': 'mods', 'title': _('Mods & patches', 'Моды и патчи'),
             'subtitle': _('The game files are never changed: mods are layered over them at start.',
                           'Файлы игры не меняются: моды накладываются при запуске.'),
             'items': [
                 section(_('Mods', 'Моды')),
                 check('mods_enabled', 'app', _('Load mods', 'Загружать моды'),
                       _('Loose-file mods, each in its own folder (with dvdroot_ps4, or chr\\, parts\\ … directly).',
                         'Моды из файлов, каждый в своей папке (с dvdroot_ps4 или chr\\, parts\\ … напрямую).')),
                 folder('mods_dir', _('Mods folder', 'Папка модов'), _('Empty: {}', 'Пусто: {}').format(D / 'mods')),
                 {'t': 'mods'},
                 section(_('Third-party patches', 'Сторонние патчи')),
                 folder('patches_dir', _('Patches folder', 'Папка патчей'),
                        _('shadPS4/GoldHEN XML patch files for version 1.09. Empty: {}',
                          'XML-патчи shadPS4/GoldHEN для версии 1.09. Пусто: {}').format(D / 'patches')),
                 {'t': 'patches'},
             ]},
            {'id': 'advanced', 'title': _('Advanced', 'Дополнительно'),
             'subtitle': _('Launcher options, performance switches and diagnostics.',
                           'Настройки лаунчера, производительность и диагностика.'),
             'items': [
                 section(_('Launcher', 'Лаунчер')),
                 choice('ui_language', 'app', _('Launcher language', 'Язык лаунчера'), core.UI_LANGUAGES),
                 check('close_on_play', 'app', _('Close the launcher when the game starts', 'Закрывать лаунчер при запуске игры')),
                 check('check_updates', 'app', _('Check for updates when the launcher opens',
                                                 'Проверять обновления при открытии лаунчера')),
                 buttons((_('Desktop shortcut', 'Ярлык на рабочем столе'), 'shortcut'), (_('Add to Steam'), 'steam'),
                         (_('Port folder', 'Папка порта'), 'port_folder'), ('bbport.ini', 'ini')),
                 buttons((_('Check for updates', 'Проверить обновления'), 'check_update'),
                         (_('Clear shader cache', 'Очистить кэш шейдеров'), 'clear_cache')),
                 note(_('If the game only shows a black screen, clearing the shader cache usually helps.',
                        'Если игра показывает только чёрный экран, обычно помогает очистка кэша шейдеров.')),
                 section(_('Performance', 'Производительность')),
                 choice('draw_pipe', 'app', _('Two-stage GPU pipeline', 'Двухстадийный конвейер GPU'), core.DRAW_PIPE,
                        _('20–30% faster; switch it off if the game is unstable.', 'Быстрее на 20–30%; при нестабильности выключите.')),
                 choice('readbacks', 'app', _('GPU readbacks', 'Чтение данных GPU'), core.READBACKS,
                        _('How exactly data the GPU writes is copied back for the game.',
                          'Насколько точно данные, записанные GPU, возвращаются игре.')),
                 section(_('Diagnostics', 'Для разработчика')),
                 check('frame_stats', 'app', _('Frame statistics in the log (every 5 s)', 'Статистика кадров в журнале (раз в 5 с)')),
                 check('gpu_profile', 'app', _('GPU time per pass in the log', 'Профиль GPU в журнале')),
                 check('vk_validation', 'app', _('Vulkan validation layers (needs the Vulkan SDK; much slower)',
                                                 'Слои валидации Vulkan (нужен Vulkan SDK; сильно замедляет)')),
                 entry('extra_env', _('Extra variables', 'Доп. переменные'),
                       _('NAME=value pairs separated by spaces (README lists them).', 'Пары ИМЯ=значение через пробел (список в README).')),
             ]},
        ]
        return pages

    def nav(self):
        return [['play', _('Play', 'Играть')]] + [[p['id'], p['title']] for p in self.describe()] + \
            [['log', _('Log', 'Журнал')]]

    # ---- status ----------------------------------------------------------------------------------
    def state(self):
        info = core.game_info(self.app['game_dir'])
        if not info:
            game = ('bad', _('No eboot.bin in the game folder (Game & effects)', 'В папке игры нет eboot.bin («Игра и эффекты»)'))
        elif info[1] == core.PATCH_VERSION:
            game = ('ok', _('Game version {}: every patch available', 'Версия игры {}: доступны все патчи').format(info[1]))
        else:
            game = ('warn', _('Game version {}: runs at 30 FPS without the community patches (they are for 1.09)',
                              'Версия игры {}: 30 FPS без патчей сообщества (они для 1.09)').format(info[1]))
        user = Path(self.app.get('user_dir') or core.DATA_DIR / 'user')
        saves = list((user / 'savedata').glob('*/*/SPRJ*')) if (user / 'savedata').is_dir() else []
        save = ('ok', _('Saves found in {}', 'Найдены сохранения в {}').format(user)) if saves else \
            ('info', _('No saves yet: the game creates them in {}', 'Сохранений пока нет: игра создаст их в {}').format(user))
        missing = core.fsr4_missing()
        fsr4 = ('ok', _('FSR 4 assets installed', 'Ассеты FSR 4 установлены')) if not missing else \
            ('info', _('FSR 4 assets missing (Graphics); FSR 3.1 is used meanwhile',
                       'Нет ассетов FSR 4 («Графика»); пока используется FSR 3.1'))
        gpu_kind = 'ok' if self.gpu_text.startswith('✓') else 'bad' if self.gpu_text.startswith('✗') else 'info'
        gpu = (gpu_kind, self.gpu_text.lstrip('✓✗• ').strip())
        warning = _('Your game is version {}: these options are patches for 1.09 and are not applied; the game runs '
                    'at 30 FPS. Update the dump to 1.09 to use them.',
                    'Ваша игра версии {}: эти настройки — патчи для 1.09 и не применяются; игра работает в 30 FPS. '
                    'Обновите дамп до 1.09, чтобы их использовать.').format(info[1]) \
            if info and info[1] != core.PATCH_VERSION else ''
        total = len(core.fsr4_files())
        fsr4_text = (_('Installed: {} files in {}.', 'Установлены: {} файлов в {}.').format(total, core.PORT_DIR / 'fsr4_shaders')
                     if not missing else _('{} of {} files missing in {}.', 'Нет {} из {} файлов в {}.').format(
                         len(missing), total, core.PORT_DIR / 'fsr4_shaders'))
        running = self._process is not None
        if running:
            status = self.status_text or _('Preparing the game; it opens in its own window…',
                                           'Подготовка игры; она откроется в своём окне…')
        elif not info:
            status = _('Choose the game folder first.', 'Сначала выберите папку игры.')
        else:
            status = self.summary(info)
        return {
            'checks': [game, save, gpu, fsr4], 'warning': warning, 'running': running, 'can_play': bool(info),
            'status': status, 'fsr4': {'text': fsr4_text, 'done': total - len(missing), 'total': total,
                                       'busy': self.fsr4_busy},
            'update': {'version': self.update[0], 'state': self.update_state} if self.update else None,
            'game': (_('CUSA03173 · game version {}', 'CUSA03173 · версия игры {}').format(info[1]) if info
                     else _('Game folder not set', 'Папка игры не выбрана')),
            'nav': self.nav(),
        }

    def summary(self, info):
        fps = dict(core.FPS_MODES).get(self.app['fps_mode'], ('?',))
        if info and info[1] != core.PATCH_VERSION:
            fps = ('30 FPS',)
        upscaler = dict(core.UPSCALERS).get(self.ini.get('upscaler'), ('?',))[0].split(' (')[0]
        output = self.ini.get('output_res', '').replace('x', ' × ')
        online = _('Online') if self.app.get('online') else _('Offline')
        return f'{_(*fps)}   ·   {upscaler}   ·   {output}   ·   {online}'

    def cover_art(self):
        """The dump's own cover (sce_sys/pic1.png) as a data URL, or None."""
        art = Path(self.app.get('game_dir') or '.') / 'sce_sys' / 'pic1.png'
        try:
            return 'data:image/png;base64,' + base64.b64encode(art.read_bytes()).decode('ascii')
        except OSError:
            return None

    def detect_gpu(self):
        exe = core.PORT_DIR / 'bin' / 'bb-gpu-capabilities.exe'
        if not exe.is_file():
            exe = core.PORT_DIR / 'out' / 'bb-gpu-capabilities.exe'
        env = dict(os.environ)
        if not (exe.parent / 'SDL3.dll').is_file():
            clang64 = Path(os.environ.get('MSYS2_ROOT', r'C:\msys64')) / 'clang64' / 'bin'
            env['PATH'] = f'{clang64}{os.pathsep}{env.get("PATH", "")}'
        text = _('• Graphics card: not checked', '• Видеокарта: не проверена')
        try:
            result = subprocess.run([str(exe), '--live-resolution'], capture_output=True, text=True, timeout=30,
                                    env=env, creationflags=core.NO_WINDOW)
            names = [line[5:].split(':')[0] for line in result.stderr.splitlines() if line.startswith('GPU: ')]
            if names:
                text = _('✓ Graphics card: {}', '✓ Видеокарта: {}').format(names[0].split(',')[0])
            elif result.returncode:
                text = _('✗ No Vulkan 1.3 graphics card found (update the driver)',
                         '✗ Не найдена видеокарта с Vulkan 1.3 (обновите драйвер)')
        except (OSError, subprocess.TimeoutExpired):
            pass
        self.gpu_text = text

    # ---- actions ---------------------------------------------------------------------------------
    def browse(self, key):
        import webview
        start = self.app.get(key) or str(core.PORT_DIR)
        chosen = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=start)
        if chosen:
            path = str(Path(chosen[0] if isinstance(chosen, (list, tuple)) else chosen))
            self.set(key, 'app', path)
            return {'value': path, 'art': self.cover_art() if key == 'game_dir' else None, 'state': self.state()}
        return None

    def open_path(self, key):
        defaults = {'user_dir': core.DATA_DIR / 'user', 'mods_dir': core.DATA_DIR / 'mods',
                    'patches_dir': core.DATA_DIR / 'patches'}
        if key == 'ini':
            self.save()
            path = core.ini_path()
        elif key == 'port_folder':
            path = core.DATA_DIR
        else:
            path = Path(self.app.get(key) or defaults.get(key, core.DATA_DIR))
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))

    def action(self, name):
        """Buttons of the Advanced page: a message for the page to show, or None."""
        if name in ('ini', 'port_folder'):
            self.open_path(name)
        elif name == 'shortcut':
            return self.shortcut()
        elif name == 'steam':
            return self.add_to_steam()
        elif name == 'check_update':
            return self.find_update(manual=True)
        elif name == 'reset_keys':
            with self._lock:
                self.ini.update(core.KEY_DEFAULTS)
                self.save()
            return {'values': {f'ini:{key}': value for key, value in core.KEY_DEFAULTS.items()},
                    'info': _('Controls reset to the defaults.', 'Управление сброшено по умолчанию.')}
        elif name == 'clear_cache':
            if self._process:
                return {'error': _('Close the game first.', 'Сначала закройте игру.')}
            import shutil
            shutil.rmtree(Path(self.app.get('user_dir') or core.DATA_DIR / 'user') / 'cache', ignore_errors=True)
            return {'info': _('Shader cache cleared. The next start stutters for a few minutes while it is rebuilt.',
                              'Кэш шейдеров очищен. Следующий запуск несколько минут будет подтормаживать, пока кэш '
                              'собирается заново.')}
        return None

    def confirm(self, text):
        return bool(self._window.create_confirmation_dialog('Bloodborne', text))

    def shortcut(self):
        if core.FROZEN:
            target, arguments, icon = sys.executable, '', f'{sys.executable},0'
        else:
            pythonw = Path(sys.executable).with_name('pythonw.exe')
            target = str(pythonw if pythonw.exists() else sys.executable)
            arguments = Path(core.__file__).resolve()
            icon = core.PORT_DIR / 'launcher' / 'bloodborne.ico'
        script = ('$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath("Desktop")'
                  '+"\\Bloodborne.lnk");'
                  f'$s.TargetPath="{target}";$s.WorkingDirectory="{core.PORT_DIR}";$s.IconLocation="{icon}";'
                  + (f"$s.Arguments='\"{arguments}\"';" if arguments else '') + '$s.Save()')
        result = subprocess.run(['powershell', '-NoProfile', '-Command', script], capture_output=True,
                                creationflags=core.NO_WINDOW)
        if result.returncode == 0:
            return {'info': _('Shortcut created on the desktop.', 'Ярлык создан на рабочем столе.')}
        return {'error': result.stderr.decode(errors='replace')[:400]}

    def add_to_steam(self):
        import time
        import bbport_steam
        steam = bbport_steam.steam_folder()
        configs = bbport_steam.user_configs(steam) if steam else []
        if not configs:
            return {'error': _('Steam was not found on this PC (or nobody has signed in to it yet).')}
        if core.FROZEN:
            exe, opts = core.PORT_DIR / 'Play Bloodborne.exe', ''
        else:
            pythonw = Path(sys.executable).with_name('pythonw.exe')
            exe, opts = (pythonw if pythonw.exists() else Path(sys.executable)), f'"{Path(core.__file__).resolve()}" --play'
        self.save()
        restart = False
        if bbport_steam.steam_running():
            if not self.confirm(_('Steam has to close while the game is added; it starts again afterwards. Close Steam now?')):
                return None
            subprocess.Popen([str(steam / 'steam.exe'), '-shutdown'], creationflags=core.NO_WINDOW)
            for _i in range(60):
                time.sleep(0.5)
                if not bbport_steam.steam_running():
                    break
            else:
                return {'error': _('Steam did not close. Close it yourself and try again.')}
            time.sleep(1)
            restart = True
        try:
            for config in configs:
                bbport_steam.add_shortcut(config / 'shortcuts.vdf', 'Bloodborne', str(exe), str(core.PORT_DIR),
                                          str(exe), opts)
        except (OSError, ValueError) as error:
            return {'error': _('Could not add the game to Steam: {}').format(error)}
        if restart:
            os.startfile('steam://open/games')
        return {'info': _('Bloodborne is in your Steam library. It starts with the settings saved in this launcher.')}

    def test_connection(self):
        values = {key: self.app.get(key, '') for key in ('online_server', 'online_webapi', 'online_community')}
        address = str(values['online_server']).strip() or core.APP_DEFAULTS['online_server']
        webapi, game = core.webapi_setting(values), core.community_address(values['online_community'])
        text = core.server_check(address, webapi, game)
        if str(values['online_webapi']).strip() and str(values['online_webapi']).strip() != webapi:
            text += '\n' + _('The WebAPI box holds the game server address; it is ignored.')
        if not self.app.get('online'):
            text += '\n' + _('"Play online" is off: the game starts offline.')
        return text

    def download_fsr4(self):
        if self.fsr4_busy:
            return None
        self.fsr4_busy = True
        folder = core.PORT_DIR / 'fsr4_shaders'
        import urllib.request
        try:
            folder.mkdir(parents=True, exist_ok=True)
            for name in core.fsr4_missing():
                part = folder / (name + '.part')
                with urllib.request.urlopen(f'{core.FSR4_BASE}/{name}', timeout=60) as response:
                    part.write_bytes(response.read())
                part.replace(folder / name)
        except OSError as error:
            return {'error': _('Download failed: {}', 'Не удалось скачать: {}').format(error)}
        finally:
            self.fsr4_busy = False
        return None

    def lists(self):
        """Mods (in load order) and the third-party patches for 1.09."""
        from mods import discover
        from patches import external_patches
        root = Path(self.app.get('mods_dir') or core.DATA_DIR / 'mods')
        profile = core.load_json(core.DATA_DIR / 'mods.json', {})
        available = discover(root)
        if set(self.mod_order) != set(available):
            known = [n for n in profile.get('order', []) if n in available]
            self.mod_order = known + [n for n in available if n not in known]
        for name in self.mod_order:
            self.mod_enabled.setdefault(name, name not in profile.get('disabled', []))
        chosen = core.load_json(core.DATA_DIR / 'patches.json', {})
        found = external_patches(Path(self.app.get('patches_dir') or core.DATA_DIR / 'patches'), core.PATCH_VERSION)
        patches = []
        for key, _path, meta in found:
            on = key in chosen.get('enabled', []) or (key not in chosen.get('disabled', []) and
                                                      meta.get('isEnabled', 'false').lower() == 'true')
            self.patch_enabled.setdefault(key, on)
            patches.append({'key': key, 'author': meta.get('Author') or '', 'on': self.patch_enabled[key]})
        return {
            'mods': [{'name': n, 'on': self.mod_enabled.get(n, True)} for n in self.mod_order],
            'patches': patches,
            'no_mods': _('No mods in {} yet.', 'В {} пока нет модов.').format(root),
            'no_patches': _('No patch files for version 1.09 yet.', 'Пока нет патчей для версии 1.09.'),
        }

    def set_mod(self, name, on):
        self.mod_enabled[name] = bool(on)
        self.save()

    def move_mod(self, index, step):
        other = index + step
        if 0 <= index < len(self.mod_order) and 0 <= other < len(self.mod_order):
            self.mod_order[index], self.mod_order[other] = self.mod_order[other], self.mod_order[index]
            self.save()
        return self.lists()

    def set_patch(self, key, on):
        self.patch_enabled[key] = bool(on)
        self.save()

    # ---- the game --------------------------------------------------------------------------------
    def play(self):
        if self._process:
            return None
        npid = str(self.app.get('online_npid', '')).strip()
        if not self.app.get('online') and npid:
            if self.confirm(_('An online account is filled in, but "Play online" is off.\n\nPlay online?',
                              'Онлайн-аккаунт заполнен, но «Играть онлайн» выключено.\n\nИграть онлайн?')):
                self.app['online'] = True
        if self.app.get('online') and '@' in npid:
            return {'error': _('The Online ID is the account name (NPID) you registered on the server, '
                               'not your email address.'), 'page': 'online'}
        self.save()
        if not core.game_info(self.app['game_dir']):
            return {'error': _('Choose the game folder with eboot.bin (CUSA03173).',
                               'Выберите папку игры с eboot.bin (CUSA03173).'), 'page': 'game'}
        try:
            self._process = subprocess.Popen(core.run_command(), cwd=core.PORT_DIR, env=core.game_environment(self.app),
                                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, creationflags=core.NO_WINDOW)
        except OSError as error:
            self._process = None
            return {'error': _('Could not start: {}', 'Не удалось запустить: {}').format(error)}
        self._job = core.GameJob(self._process)
        self.status_text = ''
        threading.Thread(target=self.read_output, args=(self._process,), daemon=True).start()
        if self.app.get('close_on_play'):
            threading.Timer(5.0, lambda: self._window.destroy()).start()
        return {'state': self.state()}

    def read_output(self, process):
        log = None
        try:
            log_dir = Path(self.app.get('user_dir') or core.DATA_DIR / 'user')
            log_dir.mkdir(parents=True, exist_ok=True)
            log = open(log_dir / 'last_run.log', 'w', encoding='utf-8', buffering=1)
        except OSError:
            pass
        for raw in iter(process.stdout.readline, b''):
            text = raw.decode('utf-8', errors='replace')
            if 'Entering original x86-64 code' in text:
                self.status_text = _('The game is running.', 'Игра запущена.')
            elif 'restarting through run.py' in text:
                self.status_text = _('Restarting with the new settings…', 'Перезапуск с новыми настройками…')
            self._log.put(text)
            if log:
                log.write(text.replace('\r\n', '\n'))
        if log:
            log.close()
        code = process.wait()
        self._log.put(_('\n— the game exited (code {}) —\n', '\n— игра завершилась (код {}) —\n').format(code))
        self._process = None
        if self._job:
            self._job.close()
            self._job = None

    def stop(self):
        if self._job:
            self._job.terminate()

    def poll(self):
        """New log text and the current state, about four times a second."""
        chunks = []
        try:
            for _i in range(2000):
                chunks.append(self._log.get_nowait())
        except queue.Empty:
            pass
        return {'log': ''.join(chunks), 'state': self.state()}

    # ---- updates ---------------------------------------------------------------------------------
    def find_update(self, manual=False):
        try:
            version, url, page = core.latest_release()
        except (OSError, ValueError, KeyError) as failure:
            if manual:
                return {'error': _('Could not check for updates: {}', 'Не удалось проверить обновления: {}').format(failure)}
            return None
        if core.version_tuple(version) > core.version_tuple(core.VERSION):
            self.update = (version, url, page)
            self.update_state = _('Version {} is available.', 'Доступна версия {}.').format(version)
            return {'info': self.update_state} if manual else None
        if manual:
            return {'info': _('You have the latest version ({}).', 'У вас последняя версия ({}).').format(core.VERSION)}
        return None

    def whats_new(self):
        if self.update:
            webbrowser.open(self.update[2])

    def install_update(self):
        if not self.update:
            return None
        version, url, page = self.update
        if self._process:
            return {'error': _('Close the game before updating.', 'Закройте игру перед обновлением.')}
        if not core.FROZEN or not url:
            webbrowser.open(page)
            return None
        if not self.confirm(_('Install version {} now? The launcher closes, installs it and opens again. Saves and '
                              'settings are kept.', 'Установить версию {} сейчас? Лаунчер закроется, установит её и '
                              'откроется снова. Сохранения и настройки останутся.').format(version)):
            return None
        import shutil
        import urllib.request
        import zipfile
        try:
            shutil.rmtree(core.UPDATE_DIR, ignore_errors=True)
            core.UPDATE_DIR.mkdir(parents=True, exist_ok=True)
            archive = core.UPDATE_DIR / 'update.zip'
            request = urllib.request.Request(url, headers={'User-Agent': 'bbport-launcher'})
            with urllib.request.urlopen(request, timeout=60) as response, open(archive, 'wb') as out:
                total, done = int(response.headers.get('Content-Length') or 0), 0
                while chunk := response.read(1 << 20):
                    out.write(chunk)
                    done += len(chunk)
                    self.update_state = _('Downloading version {}… {}%', 'Загрузка версии {}… {}%').format(
                        version, done * 100 // total if total else 0)
            with zipfile.ZipFile(archive) as package:
                package.extractall(core.UPDATE_DIR / 'new')
            archive.unlink()
            new = next((p.parent for p in (core.UPDATE_DIR / 'new').rglob('Bloodborne.exe')), None)
            if not new:
                raise OSError('Bloodborne.exe is missing from the download')
            subprocess.Popen([str(new / 'Bloodborne.exe'), '--install-update', str(core.PORT_DIR), str(os.getpid())],
                             cwd=str(new), stdin=subprocess.DEVNULL, creationflags=core.NO_WINDOW)
            self._window.destroy()
        except (OSError, zipfile.BadZipFile) as failure:
            self.update_state = _('Version {} is available.', 'Доступна версия {}.').format(version)
            return {'error': _('Update failed: {}', 'Не удалось обновить: {}').format(failure)}
        return None

    def open_url(self, url):
        if url.startswith(('https://', 'http://')):
            webbrowser.open(url)

    def closing(self):
        try:
            self.save()
        except Exception:  # never keep the window open over a settings problem
            pass


def available():
    """pywebview and the WebView2 runtime (part of Windows 11 and current Windows 10)."""
    try:
        import webview  # noqa: F401
        from webview.platforms.winforms import _is_chromium
        return bool(_is_chromium())
    except Exception:
        try:
            import webview  # noqa: F401,F811
            return (WEB_DIR / 'index.html').is_file()
        except Exception:
            return False


def run(lang):
    """lang: the language main() chose. This module imports bbport_launcher_win by name, a
    second copy when the launcher runs as __main__, so the language is passed in."""
    import webview
    core.LANG = lang
    api = Api()
    window = webview.create_window(
        'Bloodborne — bbport', url=str(WEB_DIR / 'index.html'), js_api=api, width=1240, height=780,
        min_size=(1040, 680), background_color='#07050a', text_select=False)
    api._window = window
    window.events.closing += api.closing
    webview.start(gui='edgechromium', debug=bool(os.environ.get('BB_LAUNCHER_DEBUG')),
                  private_mode=False, storage_path=str(core.CONFIG_DIR / 'webview'))
