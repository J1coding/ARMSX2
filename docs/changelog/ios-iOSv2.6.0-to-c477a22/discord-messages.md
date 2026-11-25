===== MESSAGE 1/8 · 1991 chars =====
# ARMSX2 for iOS X.Y.Z

## New

**Report a Problem.** Settings has a new Diagnostics page and the pause menu has a Report a Problem row. They bundle recent logs, settings, crash files, a photo and the paused frame into one report, with sensitive details redacted. After a crash, a freeze or a failed start, the next launch asks once whether you want to send one.

**Automatic Performance Tuning.** A new switch in the emulator settings tries lower resolution, blending accuracy and other options on its own when a game runs slow. It keeps what helps and tells you on screen. It can also lower the emulated CPU clock when the device can't keep up, and changing the clock no longer causes a big pause. It is off by default, and changing one of those settings by hand turns it off for that game.

**Rebuilt pad layout editor.** The old editor is gone, and every entry point now opens the new one: Settings > Virtual Pad > Edit Layout, the pause menu, Per-Game Settings > Pad and the library's game menu. It works with a controller and VoiceOver. You can move, resize and fade pad pieces from 10 percent to full opacity, including the whole D-pad or face button cluster as one piece.

**Floating sticks and L3/R3 in layouts.** Each stick can float or stay put, overriding the global Dynamic Thumbsticks setting, and can have its own touch zone. L3 and R3 buttons can be shown, placed and sized like Select and Start. They start hidden, so your existing layouts play as before.

**iPhone Duo support.** The pause card and in-game panels now lay themselves out around the hinge and fold. Folding or unfolding with the pause card open keeps the item your controller had selected instead of jumping back to Resume. The on-screen pad is refit to the shorter portrait screens, OrbitKeys sizes its keys by window size so the inner screen no longer gets phone-sized keys, and the library, pad editor and menus no longer flip between portrait and landscape when the on-screen keyboard shrinks the window.

===== MESSAGE 2/8 · 1650 chars =====
## Controls and menus

**Held keys keep moving.** Holding an arrow key on a keyboard now keeps moving through menus the way a held D-pad does. In the Use Controller Navigation? alert, Return and space press the highlighted button.

**Resting triggers no longer count as held.** A controller trigger that rests slightly above zero is no longer treated as L2 or R2 held down.

**Haptic Feedback follows the setting.** Turning it off in the middle of a game now stops the rumble right away. Before, the fallback kept tapping until the next game. Controller rumble also follows the setting more reliably.

**Hidden pad stays hidden.** A virtual pad you hid stays hidden after you open and close the menu.

**Speeds apply as saved.** Turbo and slow motion speeds now go live exactly as you saved them, instead of being squeezed into 0.05 to 10. After a trip to the menu, the speed shortcut keeps stepping from the speed the game is really running at.

**Game Library fixes.** Renamed games stay in their sorted place when you favorite or unfavorite them. A saved library theme loads the way it looked. A long press on a card no longer sometimes boots the game after a rotation, and the library now decides portrait or landscape in one place, so card settings, layout and the launch animation agree.

**Right-to-left and VoiceOver.** In languages such as Arabic, the controller focus ring is no longer drawn mirrored away from the control it belongs to. There are also small VoiceOver and layout fixes on every device.

**Version opens About.** The Version row in the Settings list now opens the About page, the same way Licenses and Help open their pages.

===== MESSAGE 3/8 · 1678 chars =====
## Speed

**New VU1 compiler, on by default.** A new whole-program compiler for the PS2's vector unit 1, the chip many games use for 3D geometry, now runs on top of the existing one. It builds its code on a background thread and falls back to the old compiler when it has to. Compiled code is saved per game in one file and kept in memory, so later launches start with less compiling, and slow storage no longer stalls save state loads or quitting. Games that move their routines around in memory no longer trigger endless recompiles. Turning the compiler off clears its saved code.

**Faster vector unit code.** Many small improvements to the recompiled vector unit code and its sync with the main CPU do the same work with fewer instructions. Large lookup tables are also set up only when a game reaches them, so they use less memory.

**Faster game code.** Loads and stores in recompiled game code take fewer CPU instructions. Multiplies and divides by constants, multiply-add steps and pairs of shifts compile to fewer instructions, and the main CPU does less work on its per-frame event checks and system calls. Code for the console's I/O processor is compiled more efficiently too. New code also compiles with fewer stalls.

**Less work per draw.** The graphics thread does much less on every frame. Palettes and texture lookups cost fewer CPU cycles, draws reuse the setup of recent similar draws, triangle strips and sprite pairs are processed in bulk, and repeated copy draws are skipped once they have been recorded. Texture heavy scenes gain the most, for example in Burnout 3, Baldur's Gate: Dark Alliance and MotoGP. Call of Duty 3, Sly 3 and Spider-Man 3 gain too.

===== MESSAGE 4/8 · 1937 chars =====
## Speed (cont.)

**Fewer GPU waits.** Games that read the screen back to the CPU, such as Metal Gear Solid 3, SOCOM II and The Punisher, wait less. Several reads now share one trip to the GPU and results are written back a block at a time. Elemental Gelade's depth buffer move stays on the GPU, and draws that hold back alpha bits read their target less often.

**Faster software renderer.** It copies sprites into 16-bit and 32-bit frames straight from memory, which helps games that redraw thousands of small sprites a frame, like Spider-Man 3, Stuntman and Call of Duty 2. It also builds only the colour and fog table entries each row needs.

**Faster sound.** Time stretching and surround expansion run on their own thread, and the sound chip mixer does less work for every voice and sample, using the CPU's vector instructions for interpolation and reverb. Stopping a sound stream no longer waits for queued audio.

**Faster movies and texture packs.** In-game video decoding is quicker, and texture packs decode faster: BC7 textures use vector instructions and JPEG textures decode straight to RGBA.

**Bigger image upload buffers.** Large image uploads used to fill a 9 MB buffer and make the CPU wait on the graphics. The buffers are now 32 MB on devices with 2 GB of RAM or more, and they keep their size when you load a save state.

## Graphics and Metal

**Metal second alpha pass fixed.** Draws that need a second alpha pass could draw internal ID values instead of the picture, and the depth workaround for that pass was wrong. Both are fixed in the Metal renderer.

**Lower resolution scales are exact.** Below 1x, every game image buffer now gets an exact scaled size. Draws are no longer slightly mis-scaled when the scaled size was not a whole number of pixels.

**Screen edges trimmed when upscaling.** At 2x or higher, one native pixel is trimmed from every edge of the picture to hide stray garbage along the border.

===== MESSAGE 5/8 · 1814 chars =====
## Graphics and Metal (cont.)

**Filters fit rotated displays.** With Display Rotation at 90 or 270 degrees, the shader chain, Bilinear (Sharp) and CAS now size themselves to the rotated picture.

**Texture pack fixes.** Replacement textures that finish loading late no longer stay in memory forever, and reloading or cancelling packs no longer collides with the loader. Textures whose alpha is a little off the game's opaque value are now treated as opaque, which helps River King, Sly and Armored Core 3. The pack browser loads its list only from the official ps2ktxpak catalog.

**Hardware renderer tracking fixes.** Several fixes to how the renderer tracks what a game has drawn, covering blends that need two passes, moves between buffers and sprites that leave holes. It also makes fewer needless copies in a render pass.

## Games

**Shadow of the Colossus.** The game counts its shadow volumes in a hidden buffer that depends on exact wraparound. Those draws are now done at native resolution, so the counting stays exact when upscaling.

**Another Century's Episode 3.** It no longer freezes a few seconds into play with a DECI2 Panic error when using the recompiler.

**Stuntman and Driv3r.** Every version now uses Full floating point clamping in its game settings, which fixes the AI drivers leaving their routes.

**Tales of Destiny.** The sky in the opening flight now gets the right fog value. A built-in game fix sets the VU1 clamp mode to Extra for it.

**Game patches updated.** The bundled patches now come straight from the latest PCSX2 patches release, published 2026-11-09, with 4,719 patch files.

## Saves, settings and system

**Save states with threaded VU1.** Loading a save state while VU1 runs on its own thread (MTVU) no longer swaps VU1's memory back to what it held before the load.

===== MESSAGE 6/8 · 1797 chars =====
## Saves, settings and system (cont.)

**Memory card fixes.** A game no longer reports a good save as damaged when its save loading runs ahead of the memory card service. On folder memory cards, several cases where saves could be lost, written to the wrong file or read back blank are fixed, including save files the device would not open for writing. Saving also skips pointless rewrites when nothing has changed.

**JIT starts on more devices.** A12 to A14 devices on iOS 26 no longer need to wait for the StikDebug handshake. On Dopamine 2.1 and later, the app asks to be marked as debugged at launch. The app also runs a tiny test routine from JIT memory before relying on it, so a device that can't run its own generated code is caught early instead of crashing in the first game block. Settings shows JIT Off while the interpreter is running, instead of JIT Access Detected.

**Clearer BIOS errors.** A BIOS that is missing, unreadable, empty or not a PS2 BIOS now says which problem it is, instead of always asking for a BIOS. A PlayStation 1 BIOS, such as one copied from a PS3, is named as one and skipped by the BIOS search.

**Enable Cheats stays in sync.** Turning on a cheat, importing a cheat file or merging cheat lists now flips the Enable Cheats toggle right away. Before, it stayed off until the next launch.

**Remove Disc Link works again.** The disc link panel can clear a linked disc again. Before, a linked disc could be changed but never removed.

**Startup and reconnect fixes.** Several problems when the app's scene reconnects while a game is running are fixed, including a lost game picture and a boot request that could start the game twice. Startup also reads and writes the settings file more safely, so a settings change can no longer be overwritten by an old copy.

===== MESSAGE 7/8 · 1860 chars =====
## Saves, settings and system (cont.)

**Launch and DNS crashes.** The app now opens on the iPad 6th and 7th generation, which crashed at launch on iPadOS 17.7. Swiping away an Internal DNS host no longer crashes the app when that row's text field was still selected, and deleted hosts no longer leave an empty entry behind.

## Accuracy

**CPU timing follows a real console.** The emulated CPU now charges time using a model of how the real console issues pairs of instructions, checked against timings measured on a real SCPH-30001 console. Divides, square roots, integer math, register moves, loads and stores now cost what they cost on hardware.

**Rare vector unit cases match the console.** VU1 now behaves like the real thing in branches in delay slots, in code that runs or loads past the end of its memory, after two writes to the same register, and in a read that must wait for a load. An instruction that writes no fields no longer changes registers on the recompiler, and VU0 programs that reach VU1's registers stay correct when saved code is reused.

**Software renderer and image uploads.** The software renderer treats extreme texture coordinate values the way the console does, based on measurements from an SCPH-30001. 4-bit image uploads with an odd width or an odd starting position now land where the console puts them.

## Fixes

**Rare crashes.** Fixed rare out-of-range memory reads and writes in USB microphone setup, in-game video decoding and texture pack loading, a buffer wrap bug in multithreaded VU mode, and a crash at the start of a new game when MTVU was on. A game reading an empty VIF1 queue no longer aborts a release build and gets zeroes instead, as on the console. Changing settings from several places at once no longer risks a crash. When a game jumps to a bad address, the recompilers now stop with an accurate error.

===== MESSAGE 8/8 · 967 chars =====
## Fixes (cont.)

**Software renderer glitches.** It no longer refills a texture while a queued draw still reads it, and no longer splits a draw across workers when its frame and depth buffers share memory pages. Both could produce wrong pixels. A wrong decision about drawing sprites on the CPU, taken from the previous draw's leftover state, is fixed too.

**Graphics memory leak.** Resetting the graphics draw buffers now frees the old ones, which fixes a leak of about 2.2 MiB on every reset. Very large vertex buffers also fail with a clear error instead of wrapping around.

**Audio fixes.** A rare timing problem between the emulation and audio threads is fixed, and a stray leftover value no longer leaks into the audio of games that put the sound chip in bypass mode.

**Under the hood.** The app's code was split into smaller files and tidied throughout, and Metal's vertex colour input and the file pickers were modernised. Nothing to notice while playing.

