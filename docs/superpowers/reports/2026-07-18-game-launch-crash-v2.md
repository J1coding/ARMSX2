# Root Cause: Game-Launch Crash V2 (GS Thread SIGABRT on iOS)

**Date:** 2026-07-18
**Branch:** `fix/game-launch-gs-shmem-v2`
**Plan:** `docs/superpowers/plans/2026-07-18-game-launch-crash-v2.md`
**Tested by:** tester-supplied `.ips` (LiveContainer-2026-07-18-153408.ips)

## 1. Crash report provenance

| Field | Value |
|---|---|
| `.ips` file | `LiveContainer-2026-07-18-153408.ips` |
| Host process | LiveContainer 3.7.14 (`com.kdt.livecontainer.9R842UG8CB`) |
| Device | iPhone18,2 |
| OS | iPhone OS 26.5.1 (23F81), User release |
| Capture time | 2026-07-18 15:34:07.5009 +0200 |
| Launch time | 2026-07-18 15:33:39.9058 +0200 |
| Process lifetime | ~27.595 s |
| Exception | EXC_CRASH / SIGABRT |
| ASI | `abort() called` |
| Faulting thread | index 16, name `GS` |
| ARMSX2 UUID | `5F29F60B-A11F-3D7E-85F5-8F49FF22C9CD` |
| ARMSX2 load | `0x10957C000` |
| ARMSX2 size | 14,598,144 bytes |

The crashing binary was verified to match exactly the experiment IPA produced by the prior task (`/Users/jeenvries/Documents/ARMSX2/platforms/ios/build-ios-xcode/ARMSX2-iOS-unsigned.ipa`, mtime 2026-07-18 15:26:18) via `xcrun dwarfdump --uuid`. The prior Achievements `IsActive()` guard was confirmed compiled in via disassembly at `0x10001b5d4 bl __ZN12Achievements8IsActiveEv` → `tbnz` → `bl __ZN12Achievements10InitializeEv`.

## 2. Fully symbolicated GS-thread ARMSX2iOS stack

| # | Image offset | Runtime addr | Symbol | Offset |
|---|---|---|---|---|
| 3 | `0x0C118CC` | `0x10A18D8CC` | `AbortWithMessage(char const*)` | +28 |
| 4 | `0x088D6B8` | `0x109E096B8` | `pxOnAssertFail` (Assertions.cpp region) | +0 |
| 5 | `0x03C8F98` | `0x109944F98` | `GSLocalMemory::GSLocalMemory()` | +132 |
| 6 | `0x03E3870` | `0x10995F870` | `GSState::GSState()` | +360 |
| 7 | `0x0450ABC` | `0x1099CCABC` | `GSRenderer::GSRenderer()` | +20 |
| 8 | `0x045F190` | `0x1099DB190` | `GSRendererHW::GSRendererHW()` | +36 |
| 9 | `0x03BCB08` | `0x109938B08` | `OpenGSRenderer(GSRendererType, unsigned char*)` | +212 |
| 10 | `0x03BCB84` | `0x109938B84` | `GSopen(Pcsx2Config::GSOptions const&, GSRendererType, unsigned char*, GSVSyncMode, bool)` | +108 |
| 11 | `0x05FF81C` | `0x109B7B81C` | `MTGS::ThreadEntryPoint()` | +248 |
| 12 | `0x089144C` | `0x109E0D44C` | `Threading::Thread::ThreadProc(void*)` | +36 |

System frames `__pthread_kill` / `pthread_kill` / `abort` / `_pthread_start` / `thread_start` omitted.

## 3. Exact assertion (recovered via disassembly)

Disassembly of `GSLocalMemory::GSLocalMemory()` cold path at `0x1003c8f78-0x1003c8f94`:

```
0x1003c8f6c  bl   __Z23GSAllocateWrappedMemorymm
0x1003c8f70  str  x0, [x19]
0x1003c8f74  cbnz x0, 0x1003c8f9c           ; skip abort if non-null
0x1003c8f78  adrp x0, ...                    ; file path literal
0x1003c8f7c  add  x0, x0, #0x97a             ; "/Users/.../pcsx2/GS/GSLocalMemory.cpp"
0x1003c8f84  add  x2, x2, #0x9b7             ; "GSLocalMemory::GSLocalMemory()"
0x1003c8f8c  add  x3, x3, #0x9d6             ; "Failed to allocate GS memory storage."
0x1003c8f90  mov  w1, #0x37                  ; line 0x37 = 55
0x1003c8f94  bl   __Z14pxOnAssertFailPKciS0_S0_
0x1003c8f98  ldr  x0, [x19]                  ; +132 = captured return address
```

- **File:** `pcsx2/GS/GSLocalMemory.cpp:55`
- **Function:** `GSLocalMemory::GSLocalMemory()`
- **Message:** `"Failed to allocate GS memory storage."`
- **Trigger:** `GSAllocateWrappedMemory(m_vmsize = 0x400000 /* 4 MB */, 4)` returned `nullptr`.

## 4. Root cause (distinguishing cause from symptom)

The abort is the **symptom**: `pxFailRel` fires because `m_vm8` is null. The **root cause** is upstream: `GSAllocateWrappedMemory()` (`pcsx2/GS/GS.cpp`, non-Windows branch) returned `nullptr` because its `shm_open("/GS.mem", O_RDWR|O_CREAT|O_EXCL, 0600)` call failed.

### Why `shm_open` fails on iOS

iOS sandboxed processes (including apps hosted inside LiveContainer's app-group container) are not permitted to create named POSIX shared memory in the system-wide namespace. The `shm_open` call returns `-1` with `errno` set (typically `EPERM`/`EACCES`/`ENOSYS` depending on iOS version). The function then prints `"Failed to open /GS.mem due to <errno>"` to stderr and returns `nullptr`.

### Why the rest of the codebase works on iOS

The codebase already has an iOS-aware shared-memory creator: `HostSys::CreateSharedMemory` (`common/Linux/LnxHostSys.cpp:136`), which on iOS device enters a file-backed fallback (`CreateIOSFileBackedSharedMemory`, `common/Linux/LnxHostSys.cpp:81-133`) that creates a `armsx2_<name>_<pid>_<attempt>.mem` file in `TMPDIR`, sets `FD_CLOEXEC`, `ftruncate`s it, and `unlink`s the path while keeping the descriptor open. The EE/IOP memory allocator at `pcsx2/Memory.cpp:98` uses this helper — that is why the app reaches the GS thread before aborting.

`GSAllocateWrappedMemory` was the **only production caller** that bypassed `HostSys::CreateSharedMemory` and called `shm_open` directly. This was the latent iOS-specific bug; the prior Achievements abort (different stack, different binary UUID, fixed by the `IsActive()` guard) masked it by aborting earlier in `CPUThreadInitialize`.

### Why the Achievements fix did not cause this

The Achievements `IsActive()` guard at `pcsx2/VMManager.cpp:435-436` is correct for the observed single-threaded login→launch sequence (verified by Task 8 of the plan — a theoretical check-then-act race exists but has never been observed and is out of scope for this fix). The guard did not introduce the GS abort; it simply allowed execution to progress far enough to reach it.

## 5. Comparison with the prior crash

| Dimension | Previous crash | New crash |
|---|---|---|
| Binary UUID | `4283F6F7-...` | `5F29F60B-...` |
| Build | Pre-guard | Guard present (verified by disassembly) |
| Faulting thread | `CPU Thread` | `GS` |
| Process lifetime | ~4.31 s | ~27.595 s |
| ARMSX2iOS frames | 5 | 10 |
| Top application frame | `Achievements::Initialize()` | `GSLocalMemory::GSLocalMemory()` |
| Assertion | `pcsx2/Achievements.cpp:681` `"No client and downloader"` | `pcsx2/GS/GSLocalMemory.cpp:55` `"Failed to allocate GS memory storage."` |
| Trigger | `s_client` non-null at second init | `GSAllocateWrappedMemory` returned `nullptr` |
| Subsystem | RetroAchievements lifecycle | GS VRAM allocation (iOS shmem sandbox) |
| iOS beta implicated | No | No |
| LiveContainer implicated | No | No |
| Same root cause? | **No** — distinct subsystems |

## 6. Fix

**File:** `pcsx2/GS/GS.cpp`
**Function:** POSIX branch of `GSAllocateWrappedMemory` and `GSFreeWrappedMemory`.
**Change:** Delegate fd creation to `HostSys::CreateSharedMemory` and fd release to `HostSys::DestroySharedMemory`. The `MAP_SHARED` repeat-mirroring `mmap` loop (4×4 MB contiguous mirrors of the same backing fd) is preserved unchanged. The Windows branch is untouched.

### Why this addresses the originating condition

`HostSys::CreateSharedMemory` is the same path the EE/IOP memory allocator (`pcsx2/Memory.cpp:98`) already uses successfully on iOS. By routing through it, the GS allocator inherits the iOS TMPDIR file-backed fallback automatically. The function returns a real fd instead of `nullptr`, so `m_vm8` is non-null and the `pxFailRel` at `GSLocalMemory.cpp:55` is not reached.

### Caller-visible contract preserved

- Success: returns a pointer to a `size * repeat` byte region backed by the same fd mapped `repeat` times. Unchanged.
- Failure: returns `nullptr`. The caller (`GSLocalMemory::GSLocalMemory()`) handles the abort via `pxFailRel`. Unchanged.
- The `pxAssert(s_shm_fd == -1)` invariant and the `s_shm_fd` global are preserved.

## 7. Verification performed

| Check | Result |
|---|---|
| Binary UUID match (test build vs `.ips`) | `5F29F60B-A11F-3D7E-85F5-8F49FF22C9CD` exact match |
| Achievements guard still compiled in | disassembly at `0x10001b5d4` confirmed |
| Full GS stack symbolication | 10 ARMSX2iOS frames resolved (table in §2) |
| Assertion source location recovered | `GSLocalMemory.cpp:55` from cold-path literal pool |
| Fix compiled into new binary | new UUID `215AA09D-1030-3AB2-B216-34A331B813B1`; disassembly at `0x1003be640 bl __ZN7HostSys18GetFileMappingNameEPKc` and `0x1003be65c bl __ZN7HostSys18CreateSharedMemoryEPKcm` |
| No `shm_open` reference remains in the new binary | `nm` returns no matches; the linker eliminated the unused stub |
| Static regression tests | 8 tests in `test_gs_wrapped_memory_ios_shmem.py`, all pass |
| Full iOS Python regression | 10 tests, 9 pass; 1 pre-existing unrelated failure (`test_ios_metal_barriers`, path bug documented in the plan) |
| Build warnings | none new |

## 8. Tests and commands run

```bash
# Build the fix
cd "/Users/jeenvries/Documents/ARMSX2-work game-launch-v2"
./platforms/ios/scripts/build-ios-ipa.sh

# Verify UUID
xcrun dwarfdump --uuid /tmp/armsx2-v2-exp/Payload/ARMSX2iOS.app/ARMSX2iOS
# expected: 215AA09D-1030-3AB2-B216-34A331B813B1

# Confirm refactor in binary disassembly
BIN=/tmp/armsx2-v2-exp/Payload/ARMSX2iOS.app/ARMSX2iOS
xcrun otool -arch arm64 -tV "$BIN" 2>/dev/null | awk '/^00000001003be6[0-9a-f]+/' | head -20

# Run regression tests
python3 -m unittest platforms.ios.scripts.tests.test_gs_wrapped_memory_ios_shmem -v
python3 -m unittest discover -s platforms/ios/scripts/tests -p 'test_*.py' -v
```

## 9. Remaining uncertainties

- **Exact `errno` value from `shm_open` on the device** was not captured during this fix (Task 4 deferred to tester). The fix is correct regardless of which sandbox-related errno iOS returned (`EPERM`, `EACCES`, `ENOSYS`, or `ENOENT`) because the iOS TMPDIR file-backed fallback is the path actually taken after the fix.
- **Residual Achievements `IsActive()` race** (Task 8): theoretical, not observed. Scheduled for a follow-up. Not blocking.
- **On-device verification matrix** (Task 14): tester-driven, not executed in this implementation session. Must be run on the same LiveContainer environment that produced the crash, plus a non-LiveContainer install if practical.

## 10. Environment-specific behavior

- **LiveContainer:** host process only; not implicated. The iOS sandbox restriction on named POSIX shared memory applies equally to ordinary installs.
- **iOS 26.5.1 vs 27.0 beta:** the fix does not depend on OS version. The prior crash was on 27.0 beta; the new crash is on 26.5.1 User release. Both exhibit the same sandbox restriction on `shm_open`.
- **iPhone18,1 vs iPhone18,2:** both are iPhone 16 family; not implicated.

## 11. Final diff summary

```
 pcsx2/GS/GS.cpp                                               | 41 ++--
 platforms/ios/scripts/tests/test_gs_wrapped_memory_ios_shmem.py | 169 +++++++++++
 2 files changed, 185 insertions(+), 25 deletions(-)
```

Three commits on branch `fix/game-launch-gs-shmem-v2`:
- `43d73c031 test(gs): add failing regression for iOS GS shmem allocation`
- `6959e6a11 fix(gs/iOS): route GSAllocateWrappedMemory through HostSys::CreateSharedMemory`
- `5b39781aa test(gs): extend iOS shmem regression with lifecycle invariants`

## 12. Lifecycle contract for GSAllocateWrappedMemory (final)

- **Owner:** GS thread (`MTGS::ThreadEntryPoint`) allocates; same thread (via `GSFreeWrappedMemory`) frees. No cross-thread access.
- **Static state:** `static int s_shm_fd = -1` (file-scope in `pcsx2/GS/GS.cpp`, non-Windows branch only).
- **Backwards compatibility:** caller-visible signature unchanged. Returns `nullptr` on failure; caller's `pxFailRel` aborts.
- **Mirroring:** the `repeat` parameter maps the same backing fd N times at consecutive virtual addresses. Required for PS2 GS VRAM address-wrap semantics. Preserved exactly.
- **Shared-memory name:** now PID-qualified via `HostSys::GetFileMappingName("GS.mem")` (was the fixed name `"/GS.mem"` before the fix). Matches the EE/IOP allocator's pattern.

## 13. IPA produced

- **Path:** `/Users/jeenvries/Documents/ARMSX2-iOS-gs-shmem-fix-v2.ipa` (also at `platforms/ios/build-ios-xcode/ARMSX2-iOS-unsigned.ipa` in the worktree)
- **Binary UUID:** `215AA09D-1030-3AB2-B216-34A331B813B1`
- **Build timestamp:** 2026-07-18 16:33
- **Branch HEAD at build:** `6959e6a11`
- **No visible UI marker** (preserves prior credential-entry cleanup; the binary UUID is the identifier).
