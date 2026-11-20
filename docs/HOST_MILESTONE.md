# Native host milestone — 2026-11-21

The original Xbox executable has been statically translated to C and compiled
into a native Windows diagnostic program. It reaches the menu and a visible,
controllable first scene. The repeated ten-minute route completed without the
previous DirectSound hang or DSP sample-order corruption. This completes the
bounded native-host bring-up milestone, not the Nintendo Switch port or a
complete playthrough.

## Recorded validation

The final run was `20261120T221227.047659Z`, with these matching artifacts:

| Input/artifact | SHA-256 |
|---|---|
| Original XBE | `14ecbbcf23613a916a5b3c8c45eb3448aee7693763a6dd1c70a3cb5493aefb3c` |
| Host EXE | `6fbad5fc57f7a90d2696a6c377fbb4eda999ddcacaf3831a589288c94ae10292` |
| Matching PDB | `9186594fb60c387da2f5d96f12d74e1c741ee3ed84c73213a8352bba01476fdb` |

- All 32 scripted input steps were delivered. Inspected captures showed the
  first scene after the requested resumes and a changed camera near the end.
- Audio and 3D presentations continued to the diagnostic deadline. The
  watchdog stopped execution with code 3; this is not a normal game return.
- The 593.58-second continuous recording contained no host PCM processing
  mismatches, clipped input samples, output underruns or dropped blocks.
- Periodic DSP DMA observations verified 273 complete EP channel blocks in
  38 windows without stale-slice ordering. Ambiguous or silent payloads remain
  outside that verification.
- Independent intro-source alignment showed that the two additional XMV
  packet-starvation gaps disappeared after optimizing the decoder translation
  unit. Existing linear resampling means source PCM is not bit-identical to
  FFmpeg's independently resampled reference.
- Observed scene presentation intervals: p95 34.25 ms, p99 34.95 ms,
  maximum 73.10 ms. These measurements do not establish simulation FPS or
  console performance.
- The 58 original input files remained unchanged.

The game, generated C, EXE/PDB, raw logs, captures and audio recordings are
local ignored artifacts. Only the integration sources, patches, configuration,
tools, standalone fixtures and documentation belong in this source milestone.
See [third-party notices](../THIRD_PARTY_NOTICES.md) for component licences.

## Repeating the check

The existing [workspace procedures](WORKSPACE.md) prepare and build the host.
With that matching build and separately supplied inputs, the recorded route is
available without private Codex files:

```powershell
rtk proxy .venv\Scripts\python.exe -B tools/run_host_stability.py
```

The scenario is [host-stability.json](../config/scrapland/host-stability.json).
The runner reports its new `runs/host/<stamp>/` directory. Its nonzero status
for watchdog termination is expected diagnostic behavior; verify the final
manifest and run the independent checkers before calling a run successful:

```powershell
rtk proxy .venv\Scripts\python.exe -B tools/validate_host_stability.py runs/host/<stamp>
rtk proxy .venv\Scripts\python.exe -B tools/analyze_audio_stream.py runs/host/<stamp>
rtk proxy .venv\Scripts\python.exe -B tools/inspect_dsp_dma.py runs/host/<stamp> --summary
```

Inspect actual frames and the recorded route as well: counters alone cannot
distinguish a working scene from a pause menu. The [boot investigation](BOOT_RECOVERY.md)
records the fixes, instrumentation and narrower test scopes.

## Remaining scope

There are still 197 unresolved guest targets that terminate visibly if reached;
their presence is not equivalent to a failure on the verified route. Full-game
coverage, saves beyond the tested scenario, normal window-close lifecycle,
additional effects and materials, and physical audio-device fidelity require
further validation. No playable Switch game build or hardware performance
claim follows from this PC milestone.
