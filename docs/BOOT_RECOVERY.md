# Initial Windows boot investigation

This document records successive historical milestones. The current bounded
host result and repeatable scenario are summarized in [HOST_MILESTONE.md](HOST_MILESTONE.md).

The first diagnostic Windows build compiled the actual lifted game and executed XBE entry `0x00187775`. Run logs confirmed thread start wrapper `0x0018625D` with context `0x00187701`, followed by guest file access to the game archives and localisation data. The run stopped at strict unresolved target `0x00028B00`; it did not establish a working menu, Python startup or graphics.

## Reached CFG split

The unresolved reference is emitted from the fragment `sub_00028B11`. The original bytes at `0x00028B00` are the head of a loop inside the function beginning at `0x00028AF0`, not evidence of a separate callee. Discovery split the owner at an internal INT3 into a `call_target` record ending at `0x00028B11` and a weak `cc_boundary` record ending at `0x00028B3D`. The loop's backedge was consequently emitted as a call to an unresolved stub, changing control flow and losing the caller's register/flag context.

`config/scrapland/coalesce_functions.json` records explicit owner bounds and the exact false interior starts. Seven local repairs in this same bounded routine cluster were accepted by the pinned xboxrecomp CFG validator. It requires one backed code section, exact interior census, no independent entry evidence and gap-free decoded CFG coverage. These are structural repairs; runtime coverage is claimed only for paths actually observed.

| Owner | End (exclusive) | False interior start |
|---|---|---|
| `0x00028A90` | `0x00028AE8` | `0x00028AC1` |
| `0x00028AF0` | `0x00028B3D` | `0x00028B11` |
| `0x00028B40` | `0x00028B87` | `0x00028B61` |
| `0x00028B90` | `0x00028BDE` | `0x00028BB2` |
| `0x00028BE0` | `0x00028C77` | `0x00028C15` |
| `0x00028C80` | `0x00028CEC` | `0x00028CB1` |
| `0x00028CF0` | `0x00028DA6` | `0x00028D21` |

The generator consumes this file through its supported `--coalesce-functions` interface. The image configuration and recovery-file hash are part of the codegen manifest; stale recovery inputs block host preparation. Original XBE/assets and donor checkouts are unchanged. No return value or missing function is substituted to bypass the failure.

Game-derived disassembly and raw run logs remain ignored. Local evidence for the first stop is `runs/host/20261119T123131.221460Z/`; the structural validation is saved in `generated/14ecbbcf23613a91/analysis/coalesce-validation.json`. These paths identify local evidence rather than public download links.

## Second execution

After regeneration and rebuild, `0x00028B00` no longer stops the run. Codegen contains 12,915 translated functions and 282 unresolved stubs, versus 12,922 and 297 before the seven boundary repairs. These counts describe generated coverage, not gameplay correctness.

Run `runs/host/20261119T124548.658230Z/` stops at a new reached target, `0x00028FE0`, emitted from fragment `sub_00028FF4`. The next task is to validate the owning range starting at `0x00028FD0`, and inspect related weak fragments around `0x00028F00`; do not add `0x00028FE0` as a new function seed without first classifying the loop/fragment relationship.

The current build has matching EXE/PDB identities in `build/host-workspace/game-build-manifest.json`. No menu, Python initialisation message, game rendering, ARM64 game conformance or console run has been confirmed.

## Validation

Three further ranges passed the same strict CFG validation and were added to the generator configuration:

| Owner | End (exclusive) | False interior starts |
|---|---|---|
| `0x00028F00` | `0x00028FBB` | `0x00028F4D`, `0x00028F74` |
| `0x00028FD0` | `0x0002900B` | `0x00028FF4` |
| `0x00029050` | `0x000290E9` | `0x000290BA` |

Extending the first range to `0x00028FCF` was rejected: its trailing fragment is not covered by the reachable CFG. The accepted bound preserves that fragment as a separate record. The nearby `0x00029040` tail-jump alias is also preserved pending independent-entry analysis.

Run `runs/host/20261119T131013.442933Z/` passed the former loop stop and reached XPP initialisation. It terminated at unresolved `0x00336378`, reached through the direct tail jump at `0x00337044`, called from `0x0002CF70`. Native stack diagnostics now record this path along with guest registers. That generation translated 12,911 functions with zero failures and 278 unresolved targets.

The new stop is an actual function entry: an independent stack-frame prologue and a `ret 8` epilogue delimit `0x00336378..0x003363F1`. An earlier immediate-reference candidate began in data and overlapped this body, hiding its start from discovery. The reached entry is recorded in `config/scrapland/seed_functions.json`; rerun analysis consumes that evidence rather than adding a success stub.

Runtime patch 0004 caches instruction-derived static callback table bounds during repeated coalescence proofs. It still validates table contents against the current function census on every scan, and invalidates bounds when the owner extent or recovered instruction list changes. Three synthetic regression tests cover those cases. Existing coalescence tests retain the same 142 passes and three inherited failures described below.

## USB and interrupt delivery

After seeding the reached XPP table callback `0x00336FB6`, run `runs/host/20261119T132353.228315Z/` initialised the OHCI model, made the guest controller operational and delivered an interrupt to guest ISR `0x0033A1FF`. The driver configured HCCA and periodic descriptors. The next strict stop was `CLI` at `0x0033A2C5` in a USB timer DPC. This proves controller initialisation and ISR entry, not completed enumeration or working gamepad input.

The Windows host now initialises the existing OHCI implementation and routes only its owned MMIO faults through the runtime's instruction decoder. It continues to report unrelated memory faults. Runtime patch 0005 implements `CLI/STI` through the scheduler/dispatch gate: repeated CLI is idempotent, IF does not alter IRQL, and a kernel boundary cannot release the guest execution lock while IF is clear. Contention is resolved before disabling interrupts, avoiding the dispatch-lock/guest-lock inversion. STI reopens delivery at subsequent scheduling boundaries; this runtime is not a cycle-accurate interrupt model.

`tools/check_interrupt_execution.py` generates independent x86 test functions, translates and compiles them, then runs a real worker ISR against the runtime's locks. The test covers blocked/pending delivery, repeated CLI, STI, kernel suspension, contention and preservation of IRQL. It passed on Windows; ARM64 equivalence remains to be checked.

Generation with patch 0005 completed: 12,913 functions, zero translation failures, 277 unresolved targets. The updated game code has not yet been compiled or executed. The next verification is a new Windows build/run; the latest game EXE still represents the earlier CLI stop.

## Resumed execution and inline tables

After the user resumed work, run `runs/host/20261119T160356.413139Z/` passed the CLI stop and reached engine animation loading. Two constructor entries were recovered from argument 4 of the verified array constructor helper `0x000115C0`: reached `0x0024BD80` at call site `0x0024C222`, and statically confirmed `0x002393E0` at `0x00239DD7`. Both had been hidden inside overextended preceding records. They are recorded as seeds; runtime coverage is only claimed for reached paths.

Run `runs/host/20261119T161419.964470Z/` stopped on a memory access in `0x0017BA30`, the reached copy routine. Native diagnostics now include the generated C line and a stack walked from the exception context. Linear decoding had interpreted embedded jump-table bytes as instructions. Patch 0007 permits a bounded CFG recovery without deleting interior entries only when the detected extent is unchanged and inline tables are present. Exact CFG coverage accepts single-byte NOP alignment and the table reader's already-supported one-based/signed indexing. Unreached live instructions still fail gap validation. The explicit recovered span is `0x0017BA30..0x0017BD6D`.

Three synthetic inline-table tests pass. `tools/check_memmove_execution.py` also compiles the actual recovered routine in isolation and compares 34,884 copies against native memmove: lengths 0..512, alignment, overlapping/non-overlapping buffers, return value, stack, EBX/ESI/EDI and DF pass. The global EBP slot is frame publication in this donor ABI; it is not asserted to be a preserved architectural EBP value. Generated C and section bytes used by this test remain ignored. The original donor test suite still has its same three inherited formatting failures.

## Native OpenGL and selected-target readback

Patch 0006 makes the shared raw NV2A OpenGL backend available to native MSVC hosts, using the separately fetched and hash-pinned SDL2 package. POSIX/Switch paths retain their optional queue; Windows starts synchronously. The host registers the backend before guest submission, enables real pushbuffer execution and retains strict GL completion diagnostics. This is the existing reference architecture, with no game-specific rendering substitution.

`tools/game_host.py graphics-smoke` maps the input XBE for the normal memory layout but does not execute guest instructions. It submits independently specified NV097 surface/clear commands. The owning render thread reads an existing surface through a capacity-checked API; missing targets and insufficient buffers fail. Run `runs/host/20261119T162634.883566Z/` passed four full 64x64 readbacks alternating `FF3366CC` and `FFCC6633`, plus the two negative cases. All 16,384 pixels matched. This proves clear/readback through NV097 -> OpenGL -> GPU, not game rendering or shader coverage. Clear-only presentation remains the renderer's placeholder; no game frame is claimed.

The same build's game run `runs/host/20261119T162639.885116Z/` passed the copy failure and stopped on actual `OUT DX,AL` at `0x002AC384`, port `0x80C0`, during D3D initialisation. Always map VAs through their actual sections: this address is in `D3D`, not `.text`. Applying the `.text` VA/file delta here decodes the wrong bytes. MCPX GPIO behavior was checked against [xemu's pinned implementation](https://github.com/xemu-project/xemu/blob/711b416840c2a528cb989621b6456a72bd02d768/hw/xbox/acpi_xbox.c). Patch 0008 routes scalar OUT with correct operand width to an independent guest device model, retaining the reached GPIO output latch and diagnosing all unsupported ports/widths. Six real x86 encodings pass the lifter test; flags remain preserved. The OUT fix passed in run `20261119T163447.603156Z`, reaching WBINVD at `0x002AA6D4`.

Patch 0009 maps WBINVD to a full compiler/CPU publication fence over coherent guest RAM (`src/runtime/cache.c`), without issuing privileged instructions on the host. Its native x64 assembly contains MFENCE. Run `20261119T164222.133669Z` passed this point and the initial GPU exchange, then stopped on missing D3D state handler `0x002A47E0`. Two explicit seeds recover the missing setters at `0x002A47E0` and `0x002A5650` in the same 30-entry state table; the second has static evidence only.

A subsequent build audit found that CMake had misdecoded localized MSVC /showIncludes output and Ninja stored zero header dependencies. Native CMake now probes that output explicitly as UTF-8 and sets the actual include prefix. A clean rebuild is required for old build trees; earlier executable hashes remain historical evidence, not proof of this repaired dependency tracking.

The GPIO input fix passed in run `20261119T165625.004084Z`, exposing an XPP driver-add callback at `0x00338316`. Three explicit seeds recover the missing add/remove callbacks in the three verified XPP driver records. Run `20261119T170235.288496Z` then loaded resources and looked for the opening `Enlight.xmv`, but stalled on a GPU software-method interrupt, NOP(40).

Native sampler evidence in `runs/host/20261119T170626.092966Z/threads.log` identifies the cycle: the main thread polls a fence in `0x002AAFA0`; the GPU waits for its trap handler; the timer/ISR thread waits for the guest execution lock. MSVC's `RECOMP_SPIN_HINT` only paused the CPU, whereas the POSIX path also yields. Patch 0011 adds a contention check every 64 poll turns and uses the existing preemption guard, preserving CLI and dispatch exclusions. The extended `tools/check_interrupt_execution.py` constructs an x86 poll that announces entry before the worker contends, preventing entry-point preemption from hiding the defect. It timed out with the old MSVC macro, then passed with the fix, alongside the prior CLI/STI/IRQL checks. The native sampler observes only the explicitly selected EXE process and briefly suspends/resumes its threads; it does not skip guest work.

- Actual MSVC SSE conversion helper: ties-to-even, truncation, int32 bounds and NaN/Inf checks pass.
- Real x86 control/debug-register move tests: unsupported paths are diagnosed, ordinary register `mov` remains translated; both tests pass.
- `tools/check_cfg_execution.py` translates an independently constructed x86 loop with a false INT3 split, compiles it with MSVC, and executes four inputs. Loop result, flags/backedge behaviour, ESP and callee-saved registers pass. This fixture contains no game code.
- The pinned donor's coalescence suite reports 142 passed and 3 failed in both the unmodified reference checkout and the patched working SDK. The three failures assert exact C substrings that no longer match register-localisation spill/reload wrappers. They are recorded as inherited test failures, not reported as a fully passing suite.
- All 58 original input files matched the initial full SHA-256 inventory after first execution. A same-size modified XBE was separately rejected by the `.exe` before mapping or guest entry.


The title now uses three bounded integration wrappers in src/runtime/d3d_hooks.c, scanned by the donor --exclude-manual mechanism. All original bodies are emitted as sub_X_gen; no game function is excluded. The BlockOnTime wrapper registers the real semaphore from device+0x30 before the original kickoff/wait. VBlank and PGRAPH wrappers serialize handlers and report actual flip retires, with exact trap acknowledgment. An independent fixture using the real scheduler/executor passed (build/tests/d3d-hooks/manifest.json). Run 20261119T172247.068136Z passed the previous fence wait, created the video worker and stopped at missing XPP report-conversion callback 0x003378B1. Its configuration record and adjacent counterpart supply two additional explicit seeds, eleven total. The first GL clear/swap remains a placeholder, not a rendered menu or gameplay result.
## PVIDEO intro-movie milestone

The Windows host now displays actual guest-decoded XMV intro frames. Runtime
patch 0012 installs a bounded NV2A polling callback on the thread that owns the
OpenGL context and adds an overlay presentation entry. The independent
`src/runtime/pvideo.c` model handles the reached packed YUY2 layout, range checks,
full-frame scaling and STOP/BUFFER state. Unsupported modes remain visible
errors. Existing generated video decoding and original D3D bodies execute.

The register behavior was checked against xemu commit
`711b416840c2a528cb989621b6456a72bd02d768`, specifically
`hw/xbox/nv2a/pvideo.c` and `hw/xbox/nv2a/pgraph/gl/display.c`; no xemu source was
copied into the independent model. Refresh presents may repeat a frame and do
not measure decoding or game frame rate.

The synthetic `pvideo-smoke` mode uses the same EXE/GL context without executing
the game. Run `20261119T174239.313913Z` passed two GPU readbacks of a 2x2 YUY2
fixture (black, white, red, red), followed by a STOP acknowledgment. Actual game
run `20261119T174329.178615Z` separately captured the animated Enlight sequence
and its final logo. The following distributor movie begins, then repeats the
same frame. Run `20261119T174644.582201Z` confirms that VBlank still advances:
driver count 0x5E0 versus last overlay submission 0x592 at the sampled instant.
Investigate the XMV decoder/timer state; these runs establish movie rendering,
not a working menu or controllable game scene. Captures and lifted code remain
ignored local artifacts.

The second-movie stall was diagnosed by a read-only wrapper around generated
XMV routine 0x30EDC7. Run `20261119T175710.158261Z` showed the final audio packet
remaining at status 0x8000000A while video was finished. The host now connects
the pinned MCPX APU through the DSOUND section's lifted MMIO accessors.
On Windows, RECOMP_AC97_READY=1 also activates the donor's AC97 reset write
handler: XDK routine 0x2E14C1 reads once into CL and then polls that register, so
an asynchronous reset acknowledgment cannot satisfy it.

Run `20261119T180228.186345Z` completed successive logo movies and continued
into the animated introduction. EXE SHA256:
`78418494a4cea31ab7683ddfd73d2c9f43b17c6f2ab5d39d164e7334705f69f8`.
This establishes progress and audio-packet completion, not audible fidelity.
The pinned APU's GP/EP effects processing remains stubbed; no DSP command
auto-acknowledgment or forced packet completion is enabled by this project.

## Real DSP and device-memory copying

The later game-host path replaces the donor's GP/EP effects stub with the
pinned xemu DSP interpreter and DMA. `config/xemu-dsp.lock.json` records the
separately obtained sources, hashes and licences; `src/audio/` contains the
standalone adapters. Patch 0013 adds conditional GP/EP memory windows and
lifecycle integration. DSP commands complete by executing guest DSP programs.
The model retains xemu's approximate timing and reports unsupported peripheral
write side effects with DSP-LIMIT; unknown peripheral reads remain errors.

A synthetic DSP program passed bootstrap, actual decoded peripheral writes,
bidirectional DMA and a program-issued halt. The first actual real-DSP run
passed the former command-word wait and reached a bulk read of GP effect
parameters. Patch 0014 then fixed the MMIO rewrite: REP MOVS block-copy fast
paths now use bus accesses if either span reaches a device. Ordinary RAM keeps
its fast path. A separate native fixture passed 402 translated byte/word/dword
MOVS/STOS cases with inaccessible device backing, including direction, overlap,
zero count, flags and register checks. The 11 existing rewrite tests pass.

Run `20261119T183024.593043Z` passed that bulk read and stopped at PUSHFD in
the standard CPUID-availability query, 0x19F1C0. Its sole identified caller,
0x192EBB, uses only the Boolean AL result and subsequently replaces the flags.
This bounded query is now a host hook answering the original Xbox's CPU
capability; other PUSHFD/POPFD sites remain strict. Original subsequent MMX and
family checks still execute. Patch 0015 routes their CPUID leaf 1 to the fixed
Pentium III model (family 6, model 8, stepping 10), independent of the host.
Unknown leaves stop visibly. A synthetic fixture passed 1,001 translated calls,
comparison-flag preservation and unsupported-leaf rejection. These changes do
not yet establish a working menu or playable scene.

## Python execution and additional loop owners

Run `20261119T185322.715906Z` passed CPU initialization and reached Python engine
callbacks. A captured 640x480 game-drawn title/legal screen was visually checked
after the videos; its artwork and Russian text were correct. Execution then
stopped at unresolved target 0x2B484, another false backedge split.

The validated owners 0x2B470..0x2B564 and 0x2B570..0x2B676 now recover 105 and
111 instructions. Each includes six false starts. Four starts were classified
as tail aliases by the earlier split; their only references are owner-local
jumps, with no absolute pointers anywhere in the image. Patch 0016 adds explicit
local-alias configuration and conservative reference checks. External branches,
calls, pointers, prologues, protected entries or other independent evidence
still reject a merge. This does not remove default strong-entry protection.

Patch 0017 retains weak continuations immediately after a conditionally targeted
INT3, while a reached non-slide breakpoint is a strict stop. It does not turn
assertions into successful returns. Synthetic tests cover rejected external
entries, 100 native recovered-loop executions and both the valid assertion path
and its strict child-process stop. All 17 runtime patches applied to a fresh
pinned source archive and reversed back to exactly the original files.

The relevant upstream coalescence test subset has 23 passing tests and three
exact-C-text assertion failures; the same three failures were reproduced in
the pristine donor. Game menu and interactive scene validation remain pending.

## Python exception diagnosis and x87 LAHF

The next runs passed the recovered loops but requested the Xbox dashboard through
the engine's fatal handler. Their native exit status was zero; this was not a
successful boot. Patch 0018 adds an optional read-only firmware-return observer,
allowing the host to record the engine journal and native stack before exit.

The journal identified a failed Python module execution. Pending interpreter
state narrowed it to `ZeroDivisionError: float division`, in a weapon script at
line 20. The actual lifted float-divide routine contained FCOMI/FUCOMI followed
by LAHF and a parity test. LAHF was emitted as a comment because the generic
flag reconstruction could not provide a signed condition for x87 compares.
Consequently the zero-divisor test read stale AH.

Patch 0019 reconstructs AH from the x87 comparison result, including unordered
NaN flags and cleared SF/AF. A standalone synthetic fixture executed 65,536
translated compare/LAHF/parity cases: four instruction variants, positive and
negative values, signed zeros, infinities, NaN and all 256 prior AH values.
The negative control reproducing the old omission fails as expected. These are
native Windows CPU checks; the next actual game run is still required. All 19
runtime patches also passed clean application and exact reverse restoration.

The subsequent run `20261119T194453.987220Z` passed the former Python exception
and reached a new strict unresolved direct target, `0x0001B921` (exit 74).
The title/legal framebuffer remains visually correct. Menu and interactive
scene validation are still pending. Work paused at the user's request after
this check; classify the new target before adding any function seed.

## Resumed control-flow recovery

On resumption, `0x1B921` was confirmed as a loop backedge under owner `0x1B900`.
The 51-instruction extent through `0x1B97E` now owns its false `0x1B937`
continuation; the separate tail entry at `0x1B97E` remains intact. The next actual
run passed that stop and reached `0x2B14D`, an original forward branch across
another breakpoint split. The validated owner `0x2AF70..0x2B1FF` contains 192
instructions and seven false interior starts. Two local aliases pass the
existing conservative reference proof. Four further split-backedge owners
passed the same boundary/coverage checks and have no interior pointer matches.

One raw byte match for interior `0x2B01B` was independently decoded as the
relative displacement of `CALL 0x24BE90` at `0x220E70`, rather than an absolute
pointer. This distinction was checked before proceeding with that merge.

A separate early host fault was localized to AMD's OpenGL ICD during pixel
format selection. The Windows EXE now exports NVIDIA's documented
`NvOptimusEnablement` preference; system driver profiles remain untouched.
A synthetic readback and the subsequent actual guest boot used the RTX 3070.
The preference and these runs do not yet establish repeatable driver stability.

The next run passed the Python imports and reached the input polling routine,
stopping at internal target `0x33121`. Its restored owner `0x33060..0x334A0`
contains 377 instructions and 23 false interior entries. Two refinements keep
this recovery conservative: patch 0016 can classify a raw address-byte match
inside one reachable instruction in an independently called function, while
actual immediate/memory references and uncertain data remain disqualifying;
patch 0017 also retains unsplit fallback instructions immediately after an
actually conditionally targeted INT3. Reaching the trap still stops execution.
Fourteen local-entry tests and four assertion-continuation tests pass, along
with the existing native loop and strict-breakpoint fixtures. The updated
19-patch stack applies cleanly and reverses to the exact pinned source tree.

## First 3D workload and preserved secondary entries

Three confirmed missing qsort comparator entries and a reached virtual method
were added as seeds. A separate constructor-store analysis established four
further missing methods; their static evidence is recorded separately from
runtime coverage. Later runs submitted hundreds of textured 3D triangles, but
stopped before a completed scene frame. This is workload coverage, not a visual
or playable-scene pass.

Patch 0020 adds G8B8 decoding, retaining its unsigned lane replication and
distinction from V8U8. It handles swizzled and linear layouts. The actual renderer
decoder passed 65,552 exact texel checks, a non-square Morton layout, row padding
and unknown-format rejection. The format mapping was checked against the pinned
xemu register definitions and GL format map; research files were verified against
their Git blob identities. Bump shader mode correctness remains a separate task.

A later owner (`0xFC0C0..0xFCAF8`) contains a secondary entry whose address also
occurs in the unclassified DOLBY material. Rather than discard that reference,
the recovery now supports `retained_entries`: both guest symbols call one static
recompiled CFG, selecting the original instruction at entry. Guest stack state
is unchanged by this host-side selection. Entries requiring unrepresented
incoming flags or their own prologues are rejected. Two synthetic native
fixtures passed 4,000 executions through both entries, including stack/register
checks; the breakpoint child still exits strictly with 77. All 37 project unit
tests pass, and all 20 runtime patches apply and reverse exactly.

## First interactive menu and level loading

Two native runs on 2026-11-20 rendered the actual profile and main menus.
Scripted guest button presses created the D-Tritus profile, accepted it and
selected single-player. The second run displayed the first level's loading
screen and progress bar. Menu text is readable, but the animated background is
visibly overbright. Correct scene rendering and controllable gameplay are still
unproven.

The first run stopped advancing frames while the main thread waited in the
original D3D fence routine; this did not repeat before the second run reached
its next strict stop. The native sampler now records hardware GET/PUT, trapped
methods, the event and the exact fence records to diagnose a recurrence.

The next reached missing virtual method is `0x00146A10`, in the actual object's
table at `0x0035FC00`. The entry follows the prior method's six-pointer switch
table and twelve byte indices. Linear sweep had decoded those bytes across the
real entry. The analysis driver now passes explicitly observed seeds through
the donor's existing realignment guard and includes the full seed metadata in
its input identity. Speculative seeds retain the donor's checks.

Patch 0021 extends the existing guest USB input script with left/right stick
directions. A native fixture checks all 256 direction masks with and without a
connected host pad, buttons, expiry, report bounds and the second pad's shared
clock. These are synthetic input checks, not gameplay proof. All 21 runtime
patches apply to pristine pinned sources and reverse exactly.

The first profile creation exposed a donor path rule that mapped HDD
`Partition1/UDATA` to the disc directory. All 58 baseline input files retained
their original hashes; nine newly created profile files were preserved in the
run evidence and moved out of the input directory. Patch 0022 routes HDD
UDATA/TDATA and guest links to the save root. Native path checks cover directory
roots, links, case, disc asset paths and similarly named sibling directories.
The runner now records a full input inventory before and after every run and
reports changes as a failed verification. All 22 patches apply and reverse
exactly; original input inventory is restored to the 58 baseline files.

## Audio and frame pacing investigation

The user reported unstable frame rate, noise and distorted audio. These remain
acceptance issues. Patch 0023 adds an optional synchronous read-only observer of
host PCM before/after the existing volume/limiter and of the output queue. The
host can capture a bounded interval into RAM and then save two stereo WAVs.
An independent synthetic fixture verifies 192,000 exact PCM values, partial
block skipping, dropped-block exclusion and WAV metadata.

`tools/game_host.py --profile` records audio queue health and presentation times,
distinguishing PVIDEO refresh from 3D presents. `tools/analyze_host_run.py`
summarizes intervals within continuous segments; neither counts as simulation
FPS. The first actual capture recorded six queue underruns over about 166 seconds,
without dropped blocks or clipped input samples. This does not yet identify the
noise source. A separate comparison of the donor's ADPCM decoder with FFmpeg on
the first movie did not support changing the block's initial sample offset.

Strict GPU diagnostics call glFinish after every operation. The runner's
`--gpu-sync deferred` option selects normal donor submission and is now the
default; `--gpu-sync strict` explicitly enables the diagnostic waits. The mode is recorded in the run
manifest. Changing the mode alone is not proof of renderer correctness or a
completed performance fix.

Two runs of the same executable with the same corrected input script both
reached the same strict CPU stop during level loading. In menu windows at
80–110 seconds, strict synchronization recorded median presentation intervals
around 50–51 ms, versus about 17 ms with deferred submission. The latter still
had roughly 34–35 ms p95 intervals. This isolates a substantial diagnostic
synchronization cost; it does not establish simulation speed or GPU ownership
correctness. The deferred run recorded no output queue underruns, dropped
blocks or clipped input samples, while the user-reported sound defects remain
unresolved.

An independent FFT alignment of one second of the first intro's FFmpeg-decoded
audio with captured PCM found correlations above 0.996 in both channels. This
supports that particular movie segment, not all audio. Candidate menu music
and ambience searches have not identified the actual source. The optional
`--apu-trace` runner flag exposes the donor's voice/register diagnostics for
that investigation; traced runs must not be treated as clean performance runs.

The next recovered level-loading function spans `0x1221A0..0x122C7B`. Its
immediate-reference entry at `0x122C40` remains independently dispatchable,
using the existing shared CFG mechanism. Recovery preserves its address
reference rather than discarding it. Entries with their own prologue or
unrepresented incoming flag requirements remain rejected. Three new unit
cases and 4,000 native executions cover the added entry category.

That recovery allowed one run to load the first level and respond to pause
input, but its world was black behind the HUD. The executor inferred surface
pixel size from pitch divided by scissor width. Narrowing the scissor therefore
changed the apparent allocation and caused GL to recreate and clear its target.
Patch 0024 derives pixel size from the NV097 colour-format field. The GPU smoke
check now narrows and offsets the clip, binds without clearing, and verifies
that all 4,096 existing pixels and the 64×64 allocation survive.

A subsequent run reproduced the intermittent fence wait in the menu, with
GET equal to PUT and no pending PGRAPH source. A status-acknowledgement pass
could snapshot the interrupt hold as zero, then clear a newly published trap.
Patch 0025 serializes hold transitions with the acknowledgement pass. The
native `tools/check_nv2a_ack_race.py` fixture forces this overlap in the actual
extracted routines: the pinned baseline loses the interrupt in all 32 cases,
while the fixed version preserves it in all 32 and continues acknowledging
unrelated status. This is a concurrency proof for that interleaving; repeated
game execution is still required to establish stability.

## Captured first scene and fixed-function lighting

The Windows host now supports optional process-local RenderDoc capture through
`--renderdoc-at`. The synthetic clear capture was replayed independently and
all 4,096 pixels matched the known 64×64 target. `tools/renderdoc_host_replay.py`
replays an owned capture, exports color targets, and optionally records pixel
history, fragment GLSL and uniform values. Saved GL target PNGs are vertically
inverted relative to the game's BMP dumps. This proves host capture/replay;
the Ryubing capture path remains a separate unverified milestone.

The actual first-scene capture isolated a draw that turned the character white.
Its fixed-function vertex shader passed the generic white diffuse attribute
without evaluating the enabled lighting state. Bounded `--gpu-state-at` snapshots
confirmed ambient, directional and spot lights, inverse normals, local-eye and
separate specular state. Patch 0028 adds this lighting calculation to the GL
fixed-function path, using cached uniforms. Vulkan retains its earlier path;
vertex skinning remains unsupported and reports a diagnostic if reached.

`tools/check_ffp_lighting.py` verifies 56 known float GPU outputs, including cone
boundaries, attenuation/range, inverse normals, material sources and specular.
The unlit control fails the known ambient check. The rebuilt game reaches the
first scene with the character's blue and orange materials visible, and retains
those colors during scripted movement and camera input. That removes the white
character defect; it does not certify every material or the unresolved audio.

## APU clock and source-buffer observations

Patch 0029 changes `NV_PAPU_XGSCNT` from host 100ns ticks to the processed
48kHz sample count, following [xemu's upstream correction](https://github.com/xemu-project/xemu/pull/2945).
The XPP code in this image reads that counter when aligning USB and audio time.
`tools/check_apu_sample_clock.py` executes the actual extracted MMIO reader with
deterministic clocks: 24 combinations verify frame-based increments, wall-clock
independence and 32-bit wrap, plus ordinary register reads. The pinned baseline
fails. Actual menu execution confirms the corrected reader is reached, but an
audio improvement has not been established.

`--apu-ring-stats` exposes the donor's existing counters. A zero-sized reported
sample population is inconclusive because mostly static loops are excluded.
`tools/host_audio_snapshot.py` builds a separate read-only probe and can snapshot
a selected non-streaming PCM voice from a running, explicitly owned host. It
resolves the actual APU state and source scatter/gather pages through matching
symbols, limits each buffer to 2MiB and records artifact identities. It does not
suspend the process: a live refill may change between page reads.

## DMA source corruption and DirectSound pool alignment

Actual buffer snapshots identified the persistent audio noise: ordinary low
guest memory and a separate contiguous allocation had the same numeric physical
offset. The APU selected the contiguous window and read unrelated live graphics
data. The low buffer contained valid music matching independently decoded
`Epic.ogg`; the guest decoder was producing correct samples.

Patch 0030 reserves explicit physical page aliases for ordinary guest pages and
publishes a shared resolver used by APU, NV2A and OHCI. Static image addresses
below the contiguous arena keep their existing identities. The native
`tools/check_dma_alias.py` check covers colliding storage, byte offsets, device
routes and concurrent lookups. Its allocator fixture alone does not establish
correct interaction with every allocation made by the game.

The first game checks exposed a regression: the real GP DSP overwrote a live
DirectSound list node. A page-write watch and native stack traced the write to
scratch scatter/gather DMA. Its unaligned page base crossed into a different
physical allocation when the DSP added an offset. The kernel bridge aligned
every pool allocation to 16 bytes. Patch 0031 restores page alignment for pool
requests of at least 4096 bytes in both allocation bridges, consistent with the
[whole-page pool contract](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/nf-wdm-exallocatepool).
`tools/check_pool_alignment.py` executes the actual bridges across 16,386
requests; the unchanged donor fails the page-alignment check at 4096 bytes.

With both fixes, the menu remains active and the first scene again responds to
movement, camera and pause/resume. The previously noisy looping voice reads an
all-zero buffer. Several captured voice fragments match independently decoded
music with correlation 0.994–0.998 and the correct elapsed time. A five-minute
game check showed no further underruns after the initial startup event, and no
dropped blocks or clipping. These are host observations, not Switch validation
or proof of every scene, material and audio effect.

Patch 0032 addresses the remaining early XAudio2 queue starvation: the source
voice starts after its normal queue headroom is filled. The real-device silent
PCM test `tools/check_audio_priming.py` verifies prefill, playback, a deliberately
forced underrun and clean reinitialization; the unchanged donor drains the
initial block prematurely. The test still requires real starvation to be
reported. The SDL backend is unchanged.

For diagnostic comparison, `--watch-address` enables the existing bounded
guest-dword write watch. It affects timing. For a cleaner pacing measurement,
`--quiet-gpu --dump-every 0` removes verbose GPU/periodic logs and BMP readback;
errors and profile counters remain visible. The runner permits bounded checks
up to 900 seconds. Native stack sampling also perturbs timing and must be
accounted for when interpreting frame-time outliers.

## Independent Xbox thread identity and longer gameplay checks

A longer check exposed another audio-list race after the earlier DMA fixes.
The lifted XAPI thread-ID reader loads the object at `fs:[0x28]`, then its
identity at offset `0x12C`. Each worker inherited the same zero-filled object
from the main TIB. Read-only observation confirmed that both the main thread
and the audio worker reported ID zero. The game's audio frontend compares
these IDs to recognize worker reentry and skip a critical section; this made
ordinary main-thread calls bypass that protection too.

Patch 0033 gives each TIB a separate thread record, binds the actual native
thread ID before guest execution, and keeps the kernel thread/handle mapping
consistent with that object. It preserves the existing TLS and loader fields;
it does not implement every field of an Xbox KTHREAD. The main, spawned,
timer and OHCI threads all receive identities. `tools/check_thread_identity.py`
executes the actual lifted XAPI reader on eight native workers and main, and
checks independent records, stable IDs and preserved TLS/template data. The
unchanged donor fails the ID check.

The rebuilt game was observed with different nonzero main/audio IDs and
completed a ten-minute scripted first-scene check, including repeated movement,
camera and pause/resume, beyond the prior failure point. Audio delivery tracked
48,000 samples per second, with zero underruns, dropped blocks or clipping.
Observed scene presentation intervals had p95 34.0ms and p99 34.7ms. These
intervals include the diagnostic observer and occasional BMP readback; they
are not a simulation-FPS or fixed-60-FPS claim.

`tools/validate_host_stability.py` checks continued audio and nonempty 3D
presentations through the bounded deadline, input preservation, audio counters,
device-clock continuity and presentation pacing. It rejects the prior hung
run even though its audio error counters remained zero. The expected watchdog
exit code 3 is recorded as a diagnostic stop, not relabelled as a normal game
exit. Captured pixels and scripted controls remain separate evidence from
this log-based check. Full-game and Switch validation remain outstanding.

A matched follow-up with `--gpu-sync strict` kept rendering and guest execution
alive but recorded three audio underruns and scene p95 51.6ms. That mode adds a
`glFinish` after each GPU operation for fault localization. Normal deferred
submission is now the runner default; strict remains an explicit diagnostic
option. The implemented GPU interrupt/fence handling remains in use. The
strict run is retained as a failed audio/pacing comparison, alongside the
passing normal-mode check, rather than included in the stable-run results.

## DSP phase and periodic metallic distortion

Zero queue errors did not establish correct sound: metallic distortion remained
audible. Aligned stage captures exposed one stale 32-sample slice in each
256-sample EP output block. Seven slices matched the expected stereo downmix;
the remaining slice matched samples 512 positions older. Actual DMA payloads
confirmed the same ordering error before conversion to host PCM.

The APU worker advanced `ep_frame_div` in its software-output path while the
guest APU was off. GP did not execute in that path. Setup time after a DSP
reset therefore shifted EP's eight-frame cadence relative to the newly started
GP program. A fixed phase adjustment cannot correct that variable offset.

Patch 0034 separates software-output pacing from the guest DSP clock. Inactive
output and test tones keep their own counter and preserve any pending hardware
block. The hardware counter advances with actual APU frames. The GP/EP
interpreter and its original scheduling condition remain in use; no voices,
effects or source samples are replaced.

`tools/check_apu_clock.py` executes the actual worker and DSP orchestration
against a tagged double-buffer/bootstrap model, with 32 inactive durations and
three resets each. It checks 24,576 active frames, consecutive EP samples and
preservation of a pending block across software output. The unchanged donor
fails. This model verifies the scheduling contract, not DSP instruction
semantics or real-device timing.

In the first rebuilt menu check, all six fully observed EP channel blocks
contained consecutive GP payloads; the preceding build failed all six. Captured
dry-mix-to-EP anchors correlated above 0.99999998 after alignment and the expected
center-channel downmix, compared with approximately 0.84–0.89 before the fix.
Personal listening and the longer gameplay check are separate acceptance steps;
these measurements alone do not certify all sounds or the whole game.

For bounded stage observation, use `tools/game_host.py run --dsp-capture 65,2`
with the normal run parameters. The first number skips active APU seconds; the
duration is limited to 1–10 seconds. Capturing changes timing. Outputs remain
inside the ignored run directory:

- `dsp-stages.bin`: fixed 5,440-byte records. Sixteen little-endian `uint32`
  header words precede 32×32 bin-major input floats, 2×32 GP mixbuffer words
  (24 significant bits), and the 256×2 signed-16 monitor buffer. Header words
  0–9 are magic `0x31505344`, record size, frame low/high words, EP frame
  counter, GP reset register, EP reset register, EP FIFO-write counter,
  GP cycles and EP cycles; the remaining words are reserved. The GP mixbuffer
  is an input observation, not a substitute for final GP effect output.
  EP monitor data is new only when its FIFO-write counter changes.
- `dsp-dma.bin`: the first 32 captured APU frames' scratch transfers. Each
  record has six little-endian words: magic `0x31414D44`, frame, GP flag,
  write flag, scratch offset and payload byte count, followed by that payload.
- `dsp-gp-fifo.bin`: optional actual GP FIFO writes. A record contains four
  words (magic `0x31465047`, frame, FIFO index, byte count) and its payload.
  Its absence means no such writes were observed; the reached Scrapland
  program transfers its output through scratch DMA instead.

`tools/inspect_dsp_dma.py <run-directory>` matches observed EP slices byte for
byte with prior GP writes. It returns 1 for a known ordering error, 2 when no
complete block can be verified, and 0 when observed complete blocks pass.
Silence, ambiguous repeated payloads and reads before the observation window
remain explicitly unverified. Its report is evidence about the reached
128/1024-byte transfer shape, not a universal DSP or perceptual audio test.

For coverage across transitions, `--dsp-dma-period 15` appends a 32-frame DMA
observation window every 15 active APU seconds, for at most 900 seconds.
`tools/inspect_dsp_dma.py <run-directory> --summary` records both verified
window coverage and ordering errors. This avoids relying on one music excerpt.

`--audio-stream 900` records submitted stereo PCM continuously from the first
audio block into `audio-stream-input.wav` and `audio-stream-output.wav`.
It uses buffered file output and checkpoints valid WAV sizes every second.
After abrupt termination, the last fraction of a second may be outside the
checkpointed size; earlier PCM remains readable. Normal audio shutdown
finalizes the exact partial length. Existing bounded `--audio-capture` can run
alongside it as an independent byte-for-byte window check.

`tools/check_audio_stream.py` checks exact PCM, periodic durable headers,
partial finalization, bounds, dropped-block exclusion and reinitialization.
`tools/analyze_audio_stream.py <completed-run-directory>` checks all recorded
pre/post PCM samples against the actual host volume/limiter implementation and
compares the bounded capture with the corresponding stream interval. It also
records per-second signal statistics. These checks verify the host output
transformation; they do not by themselves prove DSP effects, codec fidelity or
perceptual quality.

The runner writes `launch-manifest.json` before guest execution, with build
identity and requested observations. A separate final `manifest.json` records
the actual process status and post-run input inventory. A launch record without
a completion record is an interrupted or otherwise incomplete check, even if
its last audio counters were clean.

## Broader audio coverage and XMV packet starvation

The next completed ten-minute check recorded 593.58 seconds of continuous
pre/post PCM, covering 56,983,552 individual sample values without a host
postprocessing mismatch. Periodic DMA observations verified 216 complete EP
channel blocks in 37 separate windows without the old stale-slice ordering.
These results extend coverage beyond one menu excerpt, but do not establish
correct source playback merely from clean output counters.

Independent source alignment found two additional all-zero gaps in the first
intro. They occurred at XMV audio packet boundaries near source times 5.866
and 7.560 seconds; their lengths varied between launches. A native stack sample
showed the video worker executing the lifted XMV/MMX decoder while the APU
continued consuming audio normally. The decoder compiled with `/Od` could not
prepare subsequent packets before playback exhausted the available data.

The host build now locates the generated translation unit containing
`sub_0030EDC7_gen` and compiles it with `/O2 /fp:strict`. The current chunk also
contains adjacent library functions; this is a translation-unit compile policy,
not a replacement for the guest decoder. All generated bodies and the codegen
identity remain unchanged, and the other generated chunks retain `/Od`.
Configuration fails if the expected translation unit cannot be uniquely found.

In the first optimized intro check, 52 source anchors across 0.8–11.0 seconds
had an offset range below 0.5 ms, replacing the preceding accumulated jumps
of approximately 1.07 seconds. Fractional sample alignment affects waveform
correlation and must be distinguished from a discontinuity. Longer gameplay,
source fidelity and perceptual acceptance require their own evidence.

`tools/check_xmv_mmx.py` compares the actual integer helpers used by this
translation unit with SSE2 hardware operations at both `/Od` and `/O2`, including
signed multiply-add overflow, saturation, unpacking and oversized shifts.
It does not establish complete decoder equivalence or ARM64 correctness.

The optimized build then completed the repeated ten-minute host scenario
(`20261120T221227.047659Z`, EXE prefix `6fbad5fc57f7a90d`). All 32 input steps
were observed, and inspected captures showed gameplay after each requested
resume and a changed camera at about 575 seconds. Audio and 3D progress reached
the diagnostic deadline; the watchdog stopped the process with code 3, rather
than a normal game return. The 58 original input files remained unchanged.

This run recorded another 593.58 seconds of continuous PCM with zero host
postprocessing mismatches, input clipping, output underruns or dropped blocks.
Periodic DMA checks verified 273 complete EP channel blocks in 38 windows with
no stale-slice ordering. Source alignment across the intro had a delay range
below 0.5 ms; twelve native-rate anchors, including both former gap boundaries,
correlated approximately 0.989–1.000 after fractional alignment. The existing
linear resampler differs from FFmpeg's reference resampling, so this is not a
claim of identical source PCM. The MMX fixture passed 680,000 hardware
comparisons in each compile mode. Observed scene presentation intervals had
p95 34.25 ms, p99 34.95 ms and a 73.10 ms maximum; these are presentation
measurements rather than simulation FPS or Switch performance.

Matching EXE/PDB, dependency/build identities, reports and short WAV samples
are preserved under ignored `artifacts/host-stability-20261121/`. The full
recordings remain under the corresponding ignored run directory. This verifies
the bounded native menu/first-scene route. Complete game coverage, normal
window-close lifecycle and Nintendo Switch execution remain separate work.
