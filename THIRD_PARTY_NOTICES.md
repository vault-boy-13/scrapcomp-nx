# Third-party notices

This repository publishes development tools, standalone probes and portability patches. It does not include Scrapland's executable, assets, original source code or lifted game code. Rights to the game remain with its respective rights holders.

## Patch provenance

| Published files | Upstream material | Licence notice |
|---|---|---|
| `patches/runtime/0001-native-windows-executor-portability.patch` | Context and modified lines from `xboxrecomp/src/kernel/nv2a_pb_exec.c` in [NFSU2](https://github.com/antoxa2584x/nfsu2-sw/tree/d3bbc3094f8e1ad3b34593eabd431f7d251b14cb/xboxrecomp), commit `d3bbc3094f8e1ad3b34593eabd431f7d251b14cb` | [MIT — xboxrecomp](LICENSES/MIT-xboxrecomp.txt), Copyright (c) 2026 sp00nz |
| `patches/hle-tools/0001-msvc-format-attribute.patch`, `0002-msvc-format-attributes-remaining.patch` | Context and modified lines from `XboxXBE-Recomp/tools/recomp/codegen*.cpp` in [BLACK-NX-PORT](https://github.com/gerisson1996/BLACK-NX-PORT/tree/d7611d14f89179cbbf8113edee0f52b2b5f52bf5/XboxXBE-Recomp), commit `d7611d14f89179cbbf8113edee0f52b2b5f52bf5` | [MIT — XboxXBE-Recomp](LICENSES/MIT-XboxXBE-Recomp.txt), Copyright (c) 2026 TGP482 |

The corresponding MIT texts are retained for the upstream material in these patches. These notices do not assign a blanket licence to the game's materials or to every dependency.

## Dependencies obtained separately

The source dependencies and installed development tools are not vendored in this publication. Exact donor commits and dependency identities are recorded in `config/references.lock.json` and `config/dependencies.lock.json`. Preserve each component's own licence, copyright and attribution when obtaining, modifying or redistributing it.

In particular, xboxrecomp contains LGPL-2.1-or-later components derived from xemu in addition to its MIT portions. Consult its pinned `NOTICE` and `LICENSES/` for the file-level scope. A future binary distribution that links those components must be reviewed against their licence requirements; the MIT notices above do not cover those components. This initial source publication includes no built NROs or runtime libraries.

The standalone deko3d probe identifies the public devkitPro example and Primer used for API guidance in its source header. Game resources and extracted shaders are not used by the probes; the triangle shaders are standalone test inputs.
