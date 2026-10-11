# Bloodborne PC

**Bloodborne on Windows 10 and 11, played with a mouse and keyboard the way the PC Souls games are.**

The PlayStation 4 game's own x86-64 code runs directly on your processor: nothing is emulated or
recompiled on the CPU side. Only the graphics are translated, from the PS4's GPU commands and
shaders to Vulkan. Unpack the zip, start `Bloodborne.exe`, choose your game folder and press
**PLAY**.

**[Download](https://github.com/giahoki/bloodborne_pc/releases/latest)** ·
**[Report a problem](https://github.com/giahoki/bloodborne_pc/issues)**

> **No game files are included.** You need your own decrypted dump of Bloodborne (CUSA03173),
> version **1.09** (needed for the frame rate, resolution and effect patches; other versions
> run at 30 FPS). This project is not affiliated with Sony Interactive Entertainment or
> FromSoftware.

## What this version adds

This is a fork of [Supermedo's Bloodborne for Windows](https://github.com/Supermedo/bloodborne_pc),
focused on playing with a mouse and keyboard.

- **Native mouse camera.** The mouse turns the game's camera directly, without going through
  the right stick, so there is no stick acceleration or smoothing. Sensitivity is set in the
  launcher or in the in-game menu and applies at once.
- **Key bindings by action:** Attack, Dodge / run, Lock on, Firearm and so on, not by
  controller button. Each action takes up to two keys or mouse buttons, including the wheel,
  side buttons and Shift / Ctrl / Alt combinations.
- **Keyboard and mouse button prompts in the game** that follow your bindings.
- **Smooth keyboard walking.** Changing direction on the keys no longer stops the character.
- **New launcher** (WebView2) with a Controls page for the bindings. The old window is still
  there as a fallback.
- **Better on 4 GB graphics cards.** The texture cache now stays inside the card's memory
  instead of spilling into system RAM.
- **`build.bat`** builds everything in one step.

## Features

- **Upscaling:** AMD FSR 3.1 and FSR 4, NVIDIA DLSS on GeForce RTX cards, or native TAA.
- **Frame rate:** 30, 60 or 90 FPS, or unlocked with a cap (up to 120).
- **Output resolution** from 720p to 4K, presets from Native AA to Ultra Performance.
- **Game effects** on and off: motion blur, depth of field, chromatic aberration, SSAO,
  dynamic light shadows, screen-space reflections, model detail.
- **Cheats and tweaks:** never die, stealth, silent steps, Rally that never fades, enemy
  control, no camera auto-rotation, camera further away, ragdoll physics and more.
- **Online play (beta):** messages, bloodstains and ghosts through
  [The Hunter's Dream](https://thehuntersdream.com), bells and summons through a shadNet server.
- **Mods and patches** loaded without changing your game files.
- **Gamepads** through SDL3 (DualSense, DualShock 4, Xbox and others), next to the keyboard.
- **In-game settings menu** (Insert, or L3+R3 on a controller), **Add to Steam**, and
  `Play Bloodborne.exe` to start the game straight away with your saved settings.

## Requirements

- Windows 10 (1903 or later) or Windows 11, 64-bit
- A graphics card with Vulkan 1.3 and a current driver; 6 GB of video memory or more is
  recommended
- About 6 GB of free RAM (10 GB for 1440p or 4K output)
- DLSS: GeForce RTX 20 series or newer

## How to play

1. Download the zip from [Releases](https://github.com/giahoki/bloodborne_pc/releases/latest)
   and unpack it anywhere.
2. Start `Bloodborne.exe`.
3. Under **Game & effects**, choose your game folder (the one with `eboot.bin`).
4. Press **PLAY**.

### Default controls

| Action | Key |
|---|---|
| Move | W A S D |
| Camera | Mouse |
| Dodge / run (hold) | Space |
| Jump | Space again while running |
| Attack | Left mouse button |
| Strong attack | Shift + left mouse button, or mouse button 5 |
| Firearm / parry | Right mouse button |
| Transform weapon | Shift + right mouse button, or mouse button 4 |
| Lock on | Q or middle mouse button |
| Interact | E or Enter |
| Blood vial | R |
| Use item | C |
| Switch items (d-pad) | Arrow keys, mouse wheel up / down |
| Menu | Escape |
| Back | Backspace |
| Gestures | G |
| Key items | T |
| L3 (free camera, enemy control cheat) | F |

All of these can be changed in the launcher under **Controls**. The port reserves a few keys:
**Insert** opens the settings menu, **hold left Alt** frees the cursor, **F10** turns the mouse
camera off and on.

## If the game runs slowly

- On graphics cards other than AMD RX 9000, use **FSR 3.1** instead of FSR 4. FSR 4 runs much
  slower on them.
- Use the **Performance** preset and a **60 FPS** cap.
- Turn off motion blur and dynamic light shadows (Game & effects).
- If you only get a black screen, try **Advanced → Clear shader cache**.

When reporting a problem, turn on **Frame statistics in the log** in the launcher, play for a
couple of minutes, and attach `user\last_run.log` with your graphics card, processor and what
happened.

## Known issues

- The character preview on the character creation screen stays empty. The character itself is
  created correctly.
- Some AMD graphics cards crash when the game world loads.
- Online summoning with the bells has not been confirmed to work yet.
- Above about 120 FPS the game's movement slows down (a limit of the game itself).

## How it works

| Part | Language | Where |
|---|---|---|
| Loader and runtime: loads `eboot.bin`, replaces the PS4 system libraries (threads, memory, files, audio, input, saves) | C | `src/` |
| Graphics: PS4 GPU commands and shaders to Vulkan, upscalers, in-game menu | C++ | `gpu/` (based on shadPS4) |
| Game preparation (patches, mods, button prompts) and the launcher | Python | `scripts/`, `launcher/`, `run.py` |
| Launcher interface | HTML / CSS / JS | `launcher/web/` |

Python only prepares files and starts the game. Everything that runs while you play is C and
C++.

## Building from source

You need [MSYS2](https://www.msys2.org) with the CLANG64 packages listed in
[packaging/windows/README.md](packaging/windows/README.md), and Python 3 from python.org.

```bat
build.bat
```

This builds the runtime and packages `dist\bbport-windows\` and `dist\bbport-windows.zip`.
`build.bat launcher` only repackages the launcher. DLSS is built separately with
`packaging/windows/build_dlss.sh`.

## Credits

- [Supermedo](https://github.com/Supermedo) (Mohammed Albarghouthi): the Windows port, its
  launcher, online play and DLSS, which this fork is based on.
- [deadinside28](https://github.com/deadinside28/bloodborne_pc): bbport, the native Linux port
  of Bloodborne that started it all ([original README](docs/original-readme/README.md)).
- The [shadPS4](https://github.com/shadps4-emu/shadPS4) team: the renderer, and the shadNet
  server.
- [shadp2p](https://github.com/Wozzardman/shadp2p) by Wozzardman: network and PSN code for
  online play. [The Hunter's Dream](https://thehuntersdream.com) by droogie and team.
- Game patches by Kyo, Lance McDonald, auser1337, illusion, emoose, Imedved and the Bloodborne
  community.

Also used: [FSR-Vulkan](https://github.com/FireBurn/FSR-Vulkan) and the AMD FidelityFX SDK,
FSR 4 assets from [FireBurn/Q2RTX](https://github.com/FireBurn/Q2RTX), the DLSS bridge from
[IFreemz/shadPS4-Bloodborne-DLSS-FSR](https://github.com/IFreemz/shadPS4-Bloodborne-DLSS-FSR),
the [NVIDIA DLSS SDK](https://github.com/NVIDIA/DLSS) (`nvngx_dlss.dll` under NVIDIA's license),
[LibAtrac9](https://github.com/Thealexbarney/LibAtrac9), [SDL3](https://github.com/libsdl-org/SDL),
[FFmpeg](https://ffmpeg.org), [Dear ImGui](https://github.com/ocornut/imgui),
[sirit](https://github.com/shadps4-emu/sirit), [magic_enum](https://github.com/Neargye/magic_enum),
[miniz](https://github.com/richgel999/miniz), [xbyak](https://github.com/herumi/xbyak),
[wepoll](https://github.com/piscisaureus/wepoll), [cpp-httplib](https://github.com/yhirose/cpp-httplib),
[Protocol Buffers](https://protobuf.dev), [OpenSSL](https://www.openssl.org),
[miniupnpc](https://miniupnp.tuxfamily.org), [JSON for Modern C++](https://github.com/nlohmann/json),
[Vulkan Memory Allocator](https://github.com/GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator),
[pywebview](https://pywebview.flowrl.com), [MSYS2](https://www.msys2.org) / [LLVM](https://llvm.org),
[PyInstaller](https://pyinstaller.org) and [Pillow](https://python-pillow.org).

NVIDIA, GeForce RTX and DLSS are trademarks of NVIDIA Corporation.

## License

GNU GPL v2 or later ([LICENSE](LICENSE)). Third-party components keep their own licenses (see
`licenses\` in the download).
