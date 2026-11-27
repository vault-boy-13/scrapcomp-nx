# Рабочая область scrapcomp-nx

Подготовлена 19 ноября 2026. Платформа входного executable — **Xbox Original (x86/XDK 5849)**. ReXGlue/Xenos и SDK Xbox 360 в этот каркас не включены.

## Что работает

| Компонент | Состояние |
|---|---|
| Native Windows Python | Локальная `.venv`, Python 3.12.10; зависимости закреплены в `config/python-requirements.lock.txt` |
| x86 анализ/codegen | Capstone 5.0.9, Unicorn 2.1.4, xboxrecomp из закреплённого NFSU2; первый анализ и генерация C прошли |
| SDK линии BLACK | Собраны `xbe_symbols.exe` и `xbe_recomp.exe`; Zydis 4.1.1 и закреплённый Zycore |
| Host build | MSVC из Visual Studio 18 Build Tools, native CMake/Ninja; собраны реальные runtime libraries и host probe |
| Switch build | devkitA64 r30-1 / GCC 16.1.0, libnx 4.12.0; собраны реальные runtime libraries, GL renderer и три NRO-пробы |
| deko3d | 0.5.0, debug/release libraries; UAM 1.1.0; DKSH shaders и NRO собираются; Ryubing подтвердил 60 presents в видимом окне |
| OpenGL | Switch Mesa 20.1.0-5, SDL2 2.28.5-4, EGL/glad; NRO подтвердил 60 presents с GL error 0 в Ryubing |
| RenderDoc | Portable 1.47 с официального renderdoc.org; архив закреплён по SHA-256; CLI проверен |
| Ryubing | Локальный 1.3.3; отдельный профиль `.cache/ryubing-workspace`; homebrew NRO загружаются |

Собранные probes проверяют окружение. Они **не являются запуском Scrapland**, игровым renderer или доказательством работоспособности guest kernel на устройстве. Полный NVK SDK в этой области пока отсутствует: он не нужен для первых GL/deko3d probes и должен добавляться отдельно при начале Vulkan backend.

## Команды

Все команды выполнять из корня проекта в PowerShell. RTK применяется к внешним shell-командам. Скрипты не редактируют установленные SDK, исходные референсы или игровые файлы.

```powershell
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File tools/bootstrap.ps1 -WithRenderDoc
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File tools/workspace.ps1 build-host
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File tools/workspace.ps1 build-switch
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File tools/workspace.ps1 check
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File tools/workspace.ps1 stage
```

Bootstrap повторно использует установленный Windows Python, Visual Studio Build Tools и devkitPro. Он создаёт venv, устанавливает точные Python versions, получает закреплённый Zydis и материализует SDK из коммитов локальных референсов. Системные пакеты автоматически не обновляются. Их отсутствие видно через `doctor`.

После клонирования репозитория отдельно восстановить `original/` из своей копии игры и Git-репозитории в `references/<имя>/` по URL и коммитам `config/references.lock.json`. Bootstrap пока не скачивает эти референсы. Для сборки нужны локальные `nfsu2-sw` и `BLACK-NX-PORT`; полный аудит также использует `manhunt1_nx` и `nfsu1-sw`. Для запусков NRO отдельно требуется `emu/Ryubing`. Эти каталоги, зависимости, сборки и захваты исключены из Git; конфигурации, patches, probes, инструменты, документация и компактные отчёты входят в репозиторий. `.gitattributes` сохраняет LF для текстовых файлов, в том числе shell-скриптов и patches.

Для повторного анализа и генерации:

```powershell
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File tools/workspace.ps1 analyze
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File tools/workspace.ps1 scan-xdk
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File tools/workspace.ps1 generate
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File tools/workspace.ps1 doctor
```

`analyze`/`generate` проверяют SHA-256 входного XBE. Code sections заданы в `config/scrapland/image.json`; `.bss_ste` и DOLBY не проходят линейный sweep. Donor summary перечисляет также executable-flagged sections вне sweep; поле `driver_selected_code_sections` явно отмечает реально выбранные sections.

`func_id` — эвристическая классификация, исторически ориентированная в том числе на RenderWare. Её имена и число classifications не являются доказательством наличия RenderWare в Scrapland или истинными именами функций. Seeds по результатам игры добавляются отдельно и с происхождением; текущий список пуст.

## Где лежат результаты

### Диагностический host target игры

Для первого исполнения lifted-кода добавлен Windows console target `scrapcomp_host`. Он использует ту же pinned xboxrecomp ABI и реальные сгенерированные функции; Switch и Ryubing в этом пути не участвуют. Это этап загрузки и диагностики, а не готовая игровая сборка.

```powershell
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File tools/workspace.ps1 boot-report
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File tools/workspace.ps1 build-game-host
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File tools/workspace.ps1 run-game-host
```

Если analysis/codegen отсутствуют или не соответствуют текущей конфигурации, сначала выполнить `analyze`, затем `generate`. `boot-report` сохраняет статические кандидаты вызовов, callbacks и Python string references в `generated/<image-prefix>/analysis/boot-path.json`; наличие ребра или строки не доказывает достижение при исполнении.

`build-game-host` проверяет XBE SHA-256, manifest generated-файлов и patch lock, собирает и запускает числовой SSE probe, затем компилирует игровой `.exe` в один поток с отладочными символами. Неявные объявления функций считаются ошибкой компиляции. Header-only исправления runtime можно синхронизировать без повторного lifting: предыдущий manifest сохраняется, hash нового runtime header и patches записываются явно; тела игровых C-функций при этом не редактируются.

Generated unresolved stubs заменяются в отдельном локальном `host-strict/unresolved.c` обработчиками, завершающими процесс при достижении адреса. Неизвестный ICALL, указатель вне кода и UNIMPL тоже останавливают исполнение. Это предотвращает принятие пустого возврата за успешную инициализацию. Первый проход всё ещё содержит неподтверждённые границы функций и возможные data-as-code участки: разбирать достигнутые случаи по реальным bytes/callers.

`run-game-host` проверяет соответствие EXE/PDB и исходных manifests, выполняет ограниченный 15-секундный запуск и сохраняет лог/manifest в `runs/host/<UTC-run-id>/`. Для другого лимита: `rtk proxy .venv\Scripts\python.exe -B tools/game_host.py run --seconds 30`. Внешние `RECOMP_*` overrides не наследуются: текущий diagnostic runner задаёт собственные параметры GIL/log/watchdog. Игровые файлы берутся из `original/`, путь сохранений задаётся внутри run-каталога. Сам `.exe` также проверяет SHA-256 XBE до mapping; без аргументов ищет `original/Default.xbe` относительно рабочего каталога.

При остановке guest команда возвращает ненулевой exit code, при timeout — `124`; фактический Windows process status также сохраняется в manifest. Текущий результат и доказательства CFG repair описаны в [BOOT_RECOVERY.md](BOOT_RECOVERY.md). Независимую поведенческую проверку восстановления цикла можно выполнить через `rtk proxy .venv\Scripts\python.exe -B tools/check_cfg_execution.py`.

Exe находится в `build/host-workspace/scrapcomp_host.exe`, matching symbols — `scrapcomp_host.pdb`, identity — `game-build-manifest.json`. Для crash использовать symbols именно этой сборки. Возврат XBE entry, завершение по timeout и успешное создание памяти не являются доказательством меню или gameplay.

Windows execution evidence сохраняется отдельно в локальном `reports/game-host-validation.json`. Старый `workspace-validation.json` относится к окружению и NRO-пробам. Runner запускает процесс с рабочим каталогом внутри `runs/host/<run-id>/`, включая автоматический `xbox_kernel.log`; при ручном запуске из корня этот default log также исключён из Git.

### Игровой NRO в Ryubing

После подготовки runtime и генерации C из проверенного XBE соберите отдельную
цель ARM64 и запустите её в изолированном профиле.

```powershell
rtk proxy .venv\Scripts\python.exe -B tools/workspace.py prepare
rtk proxy .venv\Scripts\python.exe -B tools/workspace.py build-game-switch
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File tools/run-ryubing.ps1 -Probe scrapcomp_switch -ShowWindow -Seconds 80
```

Сборка создаёт NRO, ELF, карту линковки и манифест в `build/switch-game/`.
Архив с совпадающими хешами хранится в `artifacts/switch-game/`. Launcher
проверяет этот архив и копирует диск в виртуальную SD. Каталог
`sdmc:/switch/scrapcomp-nx/game` содержит копию входных файлов, а отдельный
`sdmc:/switch/scrapcomp-nx/saves` используется для сохранений.

Можно передать `-GuestDiagnostics <файл>` с параметрами runtime в строках
`имя=значение`. Для ускорения поиска точки остановки используйте
`RECOMP_WATCHDOG_SECS=65`. Пример выборочного чтения кадров NV2A и записи
первых восьми секунд PCM, принятого звуковым выходом.

```text
RECOMP_GL_DUMP=sdmc:/switch/scrapcomp-nx/diag/frame-,120
RECOMP_AUDIO_DUMP=sdmc:/switch/scrapcomp-nx/diag/audio.pcm,0,8
RECOMP_AUDIO_METRICS=1
```

После ограниченного по времени запуска в `runs/ryubing/<run-id>/` остаются
логи эмулятора и гостя, манифесты входов и записанные файлы из `diag/`.

### Каталоги

```text
runtime/xboxrecomp/                         рабочий SDK из pinned NFSU2, локальные patches
.deps/XboxXBE-Recomp/                       SDK/host tools из pinned BLACK
.deps/zydis/                               Zydis + закреплённый Zycore
.deps/tomlplusplus/                         библиотека из pinned BLACK
.deps/RenderDoc_1.47_64/                    portable RenderDoc
build/host-workspace/                       Windows tools, probes и runtime .lib
build/switch-workspace/                     NRO + соответствующие ELF/map, runtime .a
build/switch-game/                          игровой NRO, ELF/map, manifest
build/logs/                                подробные логи отдельных команд
generated/14ecbbcf23613a91/analysis/         disasm, func_id, ABI и HLE scanner output
generated/14ecbbcf23613a91/c/                предварительный generated C
generated/14ecbbcf23613a91/lift-report/      unresolved/UNIMPL и сводка lifter
switch_sd/switch/scrapland-workspace/       комплект probes, ELF/map и manifest
artifacts/<build-id>/                       архив согласованных артефактов probes
.cache/ryubing-workspace/                   отдельный профиль эмулятора и виртуальная SD
runs/ryubing/<run-id>/                      stdout/stderr и manifest запуска
```

`config/dependencies.lock.json` фиксирует materialized source trees после patches, коммиты, версии установленных devkit-пакетов и хеши ключевых binaries. `config/renderdoc.lock.json` фиксирует официальный URL и hash архива RenderDoc. Восстановление SDK использует именно коммиты `config/references.lock.json`, даже если checkout референса впоследствии переключён на другую ветку.

В публичном lock-файле пути к проектным binaries относительные, а внешние инструменты обозначены именами файлов; фактические пути определяются через `paths()` и локальные overrides. Каталог `reports/` содержит локальные отчёты анализа, окружения и запусков и исключён из Git. Выводы по старым сборкам не подтверждают заново собранные артефакты. Лицензии и происхождение контекстных фрагментов в patches перечислены в [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

Команда `lock-dependencies` явно переписывает снимок окружения; не использовать её для маскировки неожиданного изменения tools. После сознательного изменения dependencies сначала провести проверки, затем обновить lock и повторить stage. Bootstrap не подменяет существующий materialized SDK с другой identity.

## Изолированный Ryubing и захват кадров

```powershell
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File tools/run-ryubing.ps1 -Probe runtime_probe -Seconds 15
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File tools/run-ryubing.ps1 -Probe deko_probe -Seconds 20 -ShowWindow
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File tools/run-ryubing.ps1 -Probe gl_probe -ShowWindow -Capture
```

Для проверки transfers deko3d можно передать `-Probe deko_game_frame`
и `-FrameInput <снимок>`. Снимок должен содержать 720×540 пикселей BGRA
без заголовка. Его можно получить параметром
`RECOMP_PVIDEO_DUMP=sdmc:/switch/scrapcomp-nx/diag/pvideo-119.argb` в
диагностической конфигурации игры. После проверки launcher сохраняет
побайтовый результат и лог deko3d рядом с хешами сборки и входа.

Первый запуск копирует только уже установленные system prerequisites из пользовательского профиля Ryujinx в локальный профиль проекта. Savedata, game profiles и исходная SD не копируются. Рабочие saves/logs/cache располагаются внутри проекта. Значения ключей не печатаются и не попадают в отчёты/пакеты. Исходный emulator executable и пользовательская конфигурация не меняются.

`-Seconds N` ограничивает обычный probe-запуск; закрывается только PID, запущенный этой командой. При `-Seconds 0` приложение остаётся открытым для ручной работы. `-ShowWindow` нужен для проверки presentation: в скрытом режиме на этом стенде первый deko3d present возвращается, а следующие кадры не подтверждаются; видимое окно подтвердило 60 presents той же сборки. Скрытый запуск пригоден для коротких проверок boot/SD, его FPS не оценивать.

`-Capture` запускает Ryubing через portable RenderDoc. Vulkan layer path задаётся только для запуска, без глобальной регистрации в Windows. Для захвата использовать стандартную клавишу F12 или подключение из RenderDoc UI; файлы направлены в run-каталог. Timed termination в режиме capture намеренно не реализовано: сессию закрывать через окно эмулятора. Фактическое получение и replay `.rdc` пока не подтверждены; `capture_requested` и `capture_validated` в manifest различаются.

Частота кадров эмулятора не определяет частоты или скорость Switch. Homebrew boots и service stubs эмулятора также не заменяют проверки memory aliases, unaligned atomics, IPC и scheduling на устройстве.

## Подтверждённые проверки и текущий предел

- `workspace_probe.exe`: native compile/link и 65 536 spread/compact checks реального swizzle helper прошли.
- 24 tests и 2 subtests выбранных donor tests прошли: atomics/MMIO/fallthrough/XMM/x87 classification/runtime helpers. x87 fixture действительно компилируется и исполняется native C compiler.
- `d3d8_smoke`: format mapping, swizzle, DXT, conversions и FVF прошли. `d3d8_states_smoke`: 0 failures на D3D11 software device.
- `runtime_probe.nro`: Ryubing загрузил homebrew, NRO записал и прочитал контрольный файл на собственной SD. Отдельные pthread/4GB-reservation результаты новая проба сохраняет в `runtime-probe-results.json`.
- `deko_probe.nro`: созданы device, DKSH shaders, swapchain; в видимом окне подтверждены 60 presents. Это ещё не pixel/readback proof картинки и не NV2A backend.
- `gl_probe.nro`: в видимом окне подтверждены 60 presents, GL error 0. `.rdc` capture/replay пока отдельно не подтверждены.
- Первый XDK scanner pass: 145/238 entries функций базы и 11/12 entries data найдены. Не все записи базы нужны игре; matches ещё требуют ABI/caller проверки.
- Первый xboxrecomp pass: 12 958 предполагаемых functions в discovery, 12 922 translated, 0 translation failures, около 2 млн строк C. Есть 297 unresolved stubs и список UNIMPL. Нулевое число failed translation не означает корректный или исполняемый порт.

Числа из первого прохода относятся к начальной разметке XBE. Текущий
`scrapcomp_switch` собирает lifted C для ARM64 и проходит до управляемой
сцены в Ryubing. В актуальной строгой сборке 197 неразрешённых переходов
останавливают выполнение при первом обращении.

Машиночитаемая итоговая сводка сохраняется локально в `reports/workspace-validation.json` и не публикуется. Её можно пересобрать из существующих результатов командой `rtk proxy .venv\Scripts\python.exe tools/summarize_workspace.py`; это проверка наличия доказательств, а не повторный запуск тестов.

## Локальные исправления и происхождение

`patches/hle-tools/0001` и `0002` сохраняют GNU format diagnostics на GCC/Clang и позволяют собрать host tools через MSVC. Генерируемую семантику не меняют.

`patches/runtime/0001` заменяет GNU range initializer эквивалентной стандартной C-инициализацией dirty flags и добавляет Windows QPC для diagnostic timing в executor. Путь Switch сохраняет `clock_gettime`. Изменения применяются к materialized SDK, исходный NFSU2 не меняется.

`cmake/switch-toolchain.cmake` нормализует путь на границе native Windows RTK/MSYS2 CMake/native devkitA64 GCC. Установленный devkitPro toolchain не патчится. Компиляторы, SDK headers и generated code не смешиваются между donor snapshots.

Для deko3d smoke API usage сверялось с установленным devkitPro `deko_basic` и официальным [primer](https://github.com/devkitPro/deko3d/blob/master/Primer.md). Python versions соответствуют закреплённым tools из Manhunt. RenderDoc получен с [официальной страницы релиза](https://github.com/baldurk/renderdoc/releases/tag/v1.47).
