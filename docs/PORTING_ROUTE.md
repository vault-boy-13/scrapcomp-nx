# Маршрут статической рекомпиляции Scrapland

Дата исследования: 19 ноября 2026. Основание — исходный код и инженерные отчёты четырёх локальных референсов, чтение XBE и каталогов архивов Scrapland. Исполнение Scrapland, полный disassembly, полное сопоставление XDK-сигнатур и сборка NRO в этой работе не выполнялись.

Это состояние первичного исследования. Затем подготовлена и проверена рабочая область, выполнены первые analysis/codegen/signature passes и собраны диагностические NRO. Текущее состояние и команды находятся в [WORKSPACE.md](WORKSPACE.md); запуск самой игры ещё не подтверждён.

## 1. Выбор основы

**Основной маршрут: xboxrecomp, переносимый runtime из NFSU2, сохранение игрового XDK-кода там, где это необходимо, обработка NV2A pushbuffer и отрисовка raw batches на GPU.** Для первого корректного меню и 3D-сцены использовать OpenGL как доступную контрольную реализацию. Deko3d и Vulkan/NVK остаются кандидатами конечного backend. Отдельный небольшой deko3d-прототип допустим раньше полной игровой сцены: он проверяет жизнеспособность инструментов и выбранных shader/resource paths, но не устанавливает преимущество производительности.

Это выбор по рискам интеграции и полноте доступных компонентов. Он не доказывает, что OpenGL будет быстрее Vulkan или что Scrapland заработает без разгона. Быстродействие разных игр нельзя ранжировать по требуемым частотам: различаются игровые циклы, NPC, материалы, число draw calls, XDK и аудионагрузка.

Единого проекта, который стоит целиком объявить эталоном, здесь нет. Полезная комбинация:

| Область | Предпочтительный донор | Причина и ограничение |
|---|---|---|
| CPU lifter, kernel, Horizon memory/files/threads | NFSU2 | Полноценные host/Switch цели, исправления аппаратных проблем, профилирование; 112/112 импортов нашего XBE имеют статические маршруты. Это не доказательство корректности реализаций |
| Экономия обработки pushbuffer и загрузок | NFSU1 | Пакетная обработка constants/indices, меньше лишнего состояния, прямые вершины, работа со swizzle. Переносить после проверки различий с NFSU2 |
| FFP lighting на GPU, packed attributes, GL rings/UBO/state cache | Manhunt | Конкретные исправления CPU-затрат и диагностические режимы. Согласовать общий raw-batch ABI, executor и shader generator; копирования каталога renderer недостаточно |
| Разделение HLE D3D8/DirectSound и backend, Switch Vulkan/audio host | BLACK | Полезная альтернативная граница абстракции; XDK 5849 совпадает с Scrapland. Набор API и поведение pushbuffer имеют существенные ограничения |
| Фиксация входов/версий, отдельные результаты испытаний | Manhunt как пример процесса, с исправлением его слабых мест | Хеши, patch series, диагностические флаги полезны. Чистая сборка и host parity должны стать обязательными проверками нашего проекта |

Исходные данные, CPU/runtime, GPU backend и игровые hooks должны быть раздельными. На первом этапе оставляем игровую логику, скриптовую VM, AI, декодеры и таймеры в исходном поведении. Оптимизации вводим с возможностью сравнить исходный и новый путь.

## 2. Что фактически показали референсы

Точные коммиты и состояние tracked-файлов записаны в [references.lock.json](../config/references.lock.json). Все четыре checkout при аудите были без tracked-изменений. Vendored SDK внутри BLACK и NFS — часть этих снимков; описание upstream-коммита в README не заменяет проверку локальных изменений.

### Manhunt — ценный донор GL и диагностики, с ограниченной областью подтверждения

Изученный commit: `c1374107df26adc69d6b6bc122480bd24211fc61`. README сообщает рабочее начало первой миссии и высокую частоту flip в отдельных прогонах, но отдельно отмечает непроверенные поздние уровни, сохранения и длительную стабильность. Более поздние внутренние отчёты описывают чёрный экран/сбой появления NPC, просадку FPS и проблемы возврата в меню. Это история записанных испытаний; по ней нельзя объявить текущий бинарник заведомо сломанным или полностью проверенным.

Существенные детали кода:

- Рабочая графика — `game/src/nv2a_gl/`, заимствованная и расширенная из Burnout 3. Эксперимент deko3d принимал ограниченное подмножество draws, остальные уходили в CPU rasterizer; около 1 flip/s в уровне характеризует именно этот неполный путь.
- `MANHUNT_GL_SYNC=gpu` сохраняет surfaces на GPU. Он не публикует отрисованные пиксели в guest RAM и не подхватывает CPU-записи в поверхность. `strict`/`fenced` существуют для сравнения и заметно медленнее. Этот режим нельзя считать корректным для Scrapland до изучения readback/CPU writes/render-to-texture.
- В отчёте 11 ноября есть замеры при 1020/307 MHz и наблюдение примерно 25 против 15 FPS в тяжёлых сценах, но маршруты игрока и workload различались. Авторы прямо не принимают это как контролируемое доказательство ускорения.
- APU мог занимать значительную часть CPU и испытывать underruns. Полезны его точные математические/HRTF-оптимизации, а также перенос fixed-function lighting и CMP decode на GPU.
- README говорит о 23 patches; фактический каталог имеет более позднюю серию вплоть до 0036, с пропуском 0029. Собирать нужно по реальному manifest, без предположения о числе patches.
- Host target в проверенном `game/CMakeLists.txt` не включает GL renderer так же, как Switch target. Отчёт о host reproduction дополнительно описывает boot crash. Для Scrapland одинаковый GPU-путь на host и Switch необходимо обеспечить с начала.

Источники: [README](https://github.com/baezahuertaelias/manhunt1_nx/blob/c1374107df26adc69d6b6bc122480bd24211fc61/README.md), [Switch runs](https://github.com/baezahuertaelias/manhunt1_nx/blob/c1374107df26adc69d6b6bc122480bd24211fc61/reports/SWITCH_RUN_2026-11-11.md), [GPU results](https://github.com/baezahuertaelias/manhunt1_nx/blob/c1374107df26adc69d6b6bc122480bd24211fc61/reports/GPU_OFFLOAD_RESULTS.md), [deko3d feasibility](https://github.com/baezahuertaelias/manhunt1_nx/blob/c1374107df26adc69d6b6bc122480bd24211fc61/reports/DEKO3D_FEASIBILITY.md), [GL ownership modes](https://github.com/baezahuertaelias/manhunt1_nx/blob/c1374107df26adc69d6b6bc122480bd24211fc61/game/src/nv2a_gl/nv2a_gl.c), [CMake](https://github.com/baezahuertaelias/manhunt1_nx/blob/c1374107df26adc69d6b6bc122480bd24211fc61/game/CMakeLists.txt).

### NFSU2 — наиболее полезная основа runtime

Изученный commit: `d3bbc3094f8e1ad3b34593eabd431f7d251b14cb`. Его сильная сторона — реализация и описание реальных проблем Horizon: alias views RAM, code memory, bounce buffers для SD IPC, unaligned atomics ARM64, закрытие directory handles, guest scheduling и IRQ/DPC/fence ordering. Это уменьшает риск повторить уже найденные аппаратные дефекты.

В lifter уже есть локальные guest-регистры и локальный x87 top вместо постоянных обращений к TLS; у renderer — прямые вершины, compressed DXT, shader cache и threaded GL submission. Для каждого переносимого механизма нужны его контракты и тесты; адреса NFS-функций переносить нельзя.

Первая версия Vulkan давала примерно ту же скорость, что GL: основное время занимали guest/executor. Это прямой пример, почему выбор API без профиля не решает CPU bottleneck.

Слабые места как шаблона: абсолютные `/root/nfsu2x` пути, разрозненные старые notes, game-specific оптимизации и defaults, недостаточно отделённые от общего слоя. Переносим компоненты в собственную структуру с одной закреплённой версией runtime.

Источники: [engineering notes](https://github.com/antoxa2584x/nfsu2-sw/blob/d3bbc3094f8e1ad3b34593eabd431f7d251b14cb/CLAUDE.md), [performance](https://github.com/antoxa2584x/nfsu2-sw/blob/d3bbc3094f8e1ad3b34593eabd431f7d251b14cb/PERF_NOTES.md), [Vulkan](https://github.com/antoxa2584x/nfsu2-sw/blob/d3bbc3094f8e1ad3b34593eabd431f7d251b14cb/VULKAN_NOTES.md), [regen](https://github.com/antoxa2584x/nfsu2-sw/blob/d3bbc3094f8e1ad3b34593eabd431f7d251b14cb/tools/regen.sh), [CMake](https://github.com/antoxa2584x/nfsu2-sw/blob/d3bbc3094f8e1ad3b34593eabd431f7d251b14cb/CMakeLists.txt).

### NFSU1 — полезная последующая оптимизация общего NV2A пути

Изученный commit: `d597e08f88e3f415eb44366b22e75054f2dfd15d`. В notes есть конкретный профиль: значительная доля executor приходилась на разбор constants/indices, а часто меняющаяся палеточная текстура тратила время на swizzle. Последующие оптимизации соответствуют этим измерениям. Записанный результат 30 FPS получен с повышенными частотами и конкретным scale; он не определяет потребности Scrapland.

NFSU1 не является просто тем же runtime, что NFSU2: проверенные файлы lifter/types/kernel/GL/VK различаются. Нельзя взять генератор одного checkout и `recomp_types.h` другого. Нельзя переносить NFS-specific culling, frame-lag wrapper, widescreen адреса или отключение render passes.

Источник: [engineering notes](https://github.com/antoxa2584x/nfsu1-sw/blob/d597e08f88e3f415eb44366b22e75054f2dfd15d/CLAUDE.md).

### BLACK — реальная HLE-альтернатива, но отдельная архитектура

Изученный commit: `d7611d14f89179cbbf8113edee0f52b2b5f52bf5`. Здесь используется TGP482 XboxXBE-Recomp: x86 → C++, явный `X86Context`, замена XDK API и Vulkan backend из Black-Android. В xboxrecomp другой ABI с guest-регистрами и сгенерированными C-функциями. Их generated code, контексты и hooks не взаимозаменяемы.

Потенциальный выигрыш HLE — исключить исполнение частей XDK, большой объём NV2A command decoding и MCPX APU там, где достаточно API-контрактов. Это сильная идея для CPU Switch, но покрытие конкретной игры важнее теоретической экономии.

В локальном `Black-Android/src/d3d/d3d8.cpp` `LoadVertexShader` и `SelectVertexShader` сообщают `not supported`; `Begin` тоже сообщает отсутствие поддержки. Walk/EndPush обрабатывают ограниченные формы аппаратных команд. В sound mixer поддержаны PCM/Xbox ADPCM, другие format tags отдельно диагностируются. Это не доказывает, что Scrapland использует отсутствующие возможности, но требует проверки до принятия HLE как базы.

Для ранней оценки HLE запустить настоящий `xbe_symbols` на нашем XBE, проверить D3D globals/ABI и проверить достигнутые вызовы. Если путь игры укладывается в покрытие, допустим отдельный ограниченный прототип. Оснований сразу поддерживать два полноценных порта сейчас нет. При выборе HLE надо переходить на его согласованные codegen/runtime целиком либо писать явные адаптеры отдельных API в xboxrecomp; «склеить» оба SDK нельзя.

Источники: [BLACK architecture](https://github.com/gerisson1996/BLACK-NX-PORT/blob/d7611d14f89179cbbf8113edee0f52b2b5f52bf5/README.en.md), [migration](https://github.com/gerisson1996/BLACK-NX-PORT/blob/d7611d14f89179cbbf8113edee0f52b2b5f52bf5/MIGRACAO.md), [D3D HLE](https://github.com/gerisson1996/BLACK-NX-PORT/blob/d7611d14f89179cbbf8113edee0f52b2b5f52bf5/Black-Android/src/d3d/d3d8.cpp), [sound mixer](https://github.com/gerisson1996/BLACK-NX-PORT/blob/d7611d14f89179cbbf8113edee0f52b2b5f52bf5/Black-Android/src/sound/mixer.cpp), [Switch build](https://github.com/gerisson1996/BLACK-NX-PORT/blob/d7611d14f89179cbbf8113edee0f52b2b5f52bf5/switch/CMakeLists.txt), [X86Context](https://github.com/gerisson1996/BLACK-NX-PORT/blob/d7611d14f89179cbbf8113edee0f52b2b5f52bf5/XboxXBE-Recomp/runtime/cpu/x86_context.h).

## 3. Что установлено о нашей копии Scrapland

Полные машиночитаемые результаты сохраняются локально в `reports/input-audit.json` и не публикуются. Для повторения: `rtk proxy python -B tools/audit_inputs.py`.

| Параметр | Значение |
|---|---|
| XBE | `original/Default.xbe`, 3 866 624 байта |
| SHA-256 | `14ecbbcf23613a916a5b3c8c45eb3448aee7693763a6dd1c70a3cb5493aefb3c` |
| Title ID | `0x454C0001` |
| Entry point | `0x00187775` |
| Kernel thunk table | `0x0033C500` |
| XDK | XAPILIB/LIBC/D3D8/D3DX8/XGRAPHC/XBOXKRNL/DSOUND/XMV, все 5849 |
| Sections | 16; `.text`, D3D, D3DX, XGRPH, DSOUND, WMADEC, XMV, XPP, data и служебные sections |
| Kernel imports | 112; статический audit runtime NFSU2 нашёл маршруты для всех 112 |
| `.XTLID` с базой HLE 5849 | 38 сопоставленных functions и 3 data symbols только по export IDs |
| Распакованный диск | 58 файлов, 1 015 685 586 байт, включая 11 XMV и 36 внешних Ogg |
| BFPK catalogs | Data: 8371 записи; English: 1888; Stream: 27 |
| Скрипты внутри Data | 325 `.py` + 312 `.pyc`; есть `scripts/init.pyc`, menu/savegame/AI-related подсистемы |

**Что эти числа не доказывают:** kernel routing не равен семантическому покрытию; 38 `.XTLID` совпадений не являются полным signature matching и не означают 38/238 совместимых API. Для 138 function entries в базе нет XTLID ID, остальные могут находиться по машинным сигнатурам. Точные границы functions, callers и ABI ещё предстоит проверить. Среди data-совпадений есть `D3D_Device`, `D3D_pDevice`, `XPP_GamepadType`.

Не считать все sections с EXECUTABLE настоящим кодом. Наши `.rdata`, `.data`, `.bss_ste` помечены X. Разбирать `.bss_ste` с четырьмя raw bytes как functions нельзя. Начальный явный whitelist кода: `.text`, `D3D`, `D3DX`, `XGRPH`, `DSOUND`, `WMADEC`, `XMV`, `XPP`. `DOLBY` сначала отдельно классифицировать. В обычном loader xboxrecomp нестандартное имя `.bss_ste` не входит в стандартные data exclusions, поэтому фильтрация нужна до full discovery.

### Скриптовый runtime — отдельный важный риск и будущая точка оптимизации

В XBE есть строки инициализации Python и путь `PyInterface/PythonInit.cpp`. Все прочитанные `.pyc` имеют magic `994e0d0a`, то есть 20121 + CR/LF. Это совпадает с [CPython 1.5.2 import.c](https://github.com/python/cpython/blob/v1.5.2/Python/import.c); точную версию и модификации игрового интерпретатора по одному magic установить нельзя.

Первый порт должен рекомпилировать исходный x86-интерпретатор вместе с движком и читать имеющиеся скрипты. Такой путь сохраняет игровые API и 32-битные объекты. Наличие интерпретатора скриптов внутри игры не препятствует статической рекомпиляции её x86 executable.

Таблицы opcode handlers, Python builtins, type methods и callbacks повышают важность ICALL discovery и точного unwind. Современный Python 3 не является заменой этому runtime. Даже native-сборка старого Python на ARM64 потребует проверки размеров объектов, указателей и связи с guest-движком. Рассматривать её только после профиля и отдельного доказательства совместимости; guest scheduling lock xboxrecomp и Python GIL — разные механизмы.

### Проверка целостности данных

Чтение каталогов BFPK выполнено без распаковки. В Data последняя запись `sounds/stream/park_takeoff.ogg` заявляет offset 546 882 849, размер 50 319, конец 546 933 168. Фактический EOF — 546 930 522: разница **2646 байт**. Начало payload действительно `OggS`. Остальные прочитанные диапазоны трёх архивов укладываются в файлы.

Это подтверждённое несоответствие записанного диапазона и длины файла при прочитанной структуре каталога. Причина — усечение файла, ошибочная длина записи или модификация архива — не установлена. Сверить с рабочей копией/повторным извлечением и поведением оригинала до приёмки контента. Не дополнять файл нулями, не менять offsets и не скрывать short read в runtime.

Region/media flags широкие, подпись XBE не проверялась. Эти признаки не позволяют объявить дамп неизменённым retail. Текущий hash — идентификатор наших входных данных, а не свидетельство их происхождения.

## 4. Предлагаемая структура проекта

Ниже целевая структура игрового проекта. При первичном исследовании существовали только документы и audit; затем добавлены рабочие SDK, инструменты, CMake и probes, описанные в [WORKSPACE.md](WORKSPACE.md). Игровые stubs, скрывающие незавершённый runtime, не добавлялись.

```text
original/                     локальные неизменяемые входные данные
references/                   локальные внешние проекты для чтения
config/
  references.lock.json         версии изученных доноров
  dependencies.lock.json       будущие версии toolchain/runtime/Mesa/glslang
  scrapland/                   image metadata, seeds, ABI, hooks, code/data ranges
src/
  app/                         единый boot/lifecycle и конфигурация
  game/                        только доказанные hooks Scrapland
  platform/host/               PC bring-up
  platform/switch/             libnx, SD, pad, audio sink, crash/watchdog
  gpu/common/                  ресурсы, lifetime, diagnostics, backend contract
  gpu/gl/                      первый рабочий backend
  gpu/vulkan/                  при обоснованном выборе и приёмке
runtime/                       один закреплённый xboxrecomp snapshot
patches/runtime/               проверяемые локальные изменения с происхождением
tools/                         audit, discovery, regen, build, package, symbolization
tests/                         CPU conformance и важные runtime/GPU contracts
docs/                          решения, реестр рисков и протоколы измерения
reports/                       небольшие проверяемые сводки и метаданные
generated/<image>/<variant>/   производный C и analysis DB; не хранить в Git
build/<platform>/<variant>/    out-of-source сборки
artifacts/<build-id>/          NRO + соответствующий ELF/map + build manifest
runs/<run-id>/                логи, конфигурация, сцена, частоты, captures
```

Runtime либо vendored один раз, либо материализуется из закреплённой версии и patches; два параллельных «главных» runtime недопустимы. References не являются рабочими деревьями для правок. Генерация не пишет output внутрь donor SDK: output/cache должны быть привязаны к image hash и размещены в нашем `generated/`.

На SD: `/switch/scrapland/scrapland.nro`, `game/`, `save/`, `cache/`, `logs/`, `scrapland.env`. Guest `D:` отображать на неизменяемый `game/`; UDATA/TDATA/cache partitions — на отдельное изменяемое состояние с правильными guest paths. Имеющиеся в дампе UDATA/TDATA сначала инвентаризировать и использовать как fixtures, если игра требует их; новые сохранения не должны переписывать контрольные входы. Logger буферизовать и ограничивать, crash-handler должен выгружать хвост без постоянного синхронного SD I/O.

Каждый hook: имя, image SHA, VA, ABI, причина, доказательства определения и способ выключить. Каждый build manifest: image hash, commits/tree hashes, patch hashes, toolchain/Mesa versions, codegen flags, compile/link flags, config hash, NRO и ELF hashes. Изменение runtime types или codegen invalidates generated cache. Нельзя соединять заголовок одного SDK с C другого или редактировать generated C вручную.

## 5. Дальнейшие действия и критерии перехода

| Этап | Работа | Условие перехода |
|---|---|---|
| M0 — входы | Сверить спорный диапазон BFPK; закрепить рабочую версию XBE/данных; проверить host/devkitA64 и зависимости | Нет необъяснённого изменения входов; проблема архивной записи разрешена или явно локализована для контентных испытаний |
| M1 — анализ | Discovery/CFG с явными code sections; классификация CRT/XDK/Python; indirect tables, SEH; настоящий XDK signature scan; inventory оставшихся CPU/MMIO/IO gaps | Воспроизводимый analysis DB и список рисков. Нельзя считать данные кодом или подавлять неизвестные инструкции |
| M2 — host | Один согласованный lifter/types/runtime; boot исходного интерпретатора, загрузка scripts/init, меню, input, первая 3D-сцена; оригинальные чтения BFPK | Меню управляется, сцена меняется, нет достигнутых unresolved ICALL/UNIMPL; GUI и GPU errors наблюдаемы |
| M2a — NRO в Ryubing | По мере готовности Switch runtime: минимальные memory/file/thread/input/audio probes, затем тот же игровой NRO; локальная SD и RenderDoc capture | NRO исполняется в эмуляторе; boot milestones и GPU/resource errors доступны в логах; захват кадра с данным backend проверен отдельным smoke test |
| M3 — первый Switch NRO | Сначала memory/thread/file/input/audio/lifecycle probes; затем та же игровая сцена и тот же GL path; title takeover | Реальная консоль: boot, управление, стабильный render и audio; crash/watchdog даёт guest VA и host stack с точным ELF |
| M4 — корректность игры | Ходьба/NPC/бой, превращения, полёт/корабль, streaming переходов, save/load, FMV, возврат в меню, sleep/resume | Повторяемый набор сцен; 30–60 минут без corruption/leak/hang. Сохранения проверены после перезапуска |
| M5 — производительность | Профиль guest/Python/kernel/executor/driver/GPU/APU/waits; целевые A/B и выбор GL/VK; hot hooks только по доказательствам | Работа на выбранных номинальных частотах оценена по нескольким сценам; visuals/game time/audio сохраняются |
| M6 — пакет | Clean regen/build, stage из manifest, matching NRO/ELF, first-run и warm-cache проверки | Повторная сборка с пустым build cache, воспроизводимые входы/конфигурация; инструкция установки подтверждена на устройстве |

Практическая ближайшая задача после этого исследования — **M1: analysis database нашего XBE и минимальный host-проект на закреплённой NFSU2 базе**, параллельно сверив запись Data.packed. Это ещё не перенос графических hacks и не оптимизация gameplay.

Ранняя оценка BLACK HLE может изменить архитектурное решение до больших затрат, если настоящий symbol scan и анализ вызовов покажут хорошее покрытие. Само совпадение 5849 и 38 export IDs такого перехода не оправдывает. Откладывать эту проверку до окончания порта тоже не стоит.

### Первый стенд Switch runtime: Ryubing

Для первых NRO-проверок и RenderDoc использовать локальный `emu/Ryubing`. На этапе первичного исследования были подтверждены наличие `Ryujinx.exe` и версия 1.3.3 по логам. Затем в отдельном профиле проверены runtime/GL/deko3d NRO-пробы; результаты и ограничения описаны в [WORKSPACE.md](WORKSPACE.md). Реальный RenderDoc capture/replay с нашим NRO пока не проверен.

Порядок работы: минимальный NRO → локальные runtime probes → clear/triangle/textured target → capture → игровое меню/сцена. Эти проверки начинают по готовности минимального runtime, не ожидая полного PC gameplay. Host-сборка остаётся удобным средством отделить ошибки x86 lifting от ошибок платформы Horizon.

Подготовить отдельную SD-структуру и run-каталоги для эмулятора; его saves/logs/caches не должны перезаписывать консольные результаты. Для каждого запуска хранить NRO/ELF hashes, config, backend, emulator version, host GPU/driver и capture. Привязка runtime draw/frame IDs к GPU-событиям и дампам состояния должна позволять сопоставлять Xbox-команды, наш backend и результат захвата.

При графическом захвате эмулятора анализируется host API после трансляции Switch GPU-команд; это не непосредственная трасса deko3d/NV2A. Поэтому сохранять собственные shader keys, guest surface addresses, draw IDs и resource dumps. Сначала проверить, что конкретный emulator/backend корректно проходит наш простой rendering/capture smoke test. Известные отказы NVK в Eden из референсов не переносить автоматически на Ryubing и не считать доказательством ошибки NRO.

Эмулятор подходит для короткого цикла сборка/запуск, boot, input, файлового пути и поиска графических ошибок. Аппаратная проверка нужна на границах этапов: memory aliases/IPC/unaligned atomics, scheduler/fences, audio, lifecycle и реальные timings могут отличаться. Первая консольная проверка — уже после минимальных runtime probes, а затем после устойчивой игровой сцены и перед приёмкой оптимизаций. FPS эмулятора не определяет нужный разгон Switch.

## 6. Обязательные технические решения

**CPU.** Сначала корректные integer flags, x87 precision/rounding, SSE/MMX, SEH и indirect targets. Differential conformance запускать на ARM64, не только x86-64. Локальные регистры включать вместе с call synchronization из того же генератора. Начать с разумных оптимизаций generated C, сравнить `-O2`/`-O3` на горячих участках, не включать глобальный fast-math. У BLACK успех `-O3`/NEON на XMV не доказывает такой же выигрыш для всего Scrapland.

**Memory.** Резерв 4 GB guest VA не означает 4 GB физической RAM. Должны быть проверены aliases низкой/contiguous/tiled памяти, reclaim после streaming и ARM64 unaligned atomics. В Horizon IPC передавать bounce buffers. Не скрывать allocation failures успешными возвратами.

**Scheduling.** Xbox-игра исходит из однопроцессорного guest-окружения с прерываниями. Сохранить проверенную модель сериализации guest threads и точки освобождения lock; не запускать guest-код произвольно параллельно и не отключать guest lock ради FPS. APU/render/IO host-потоки могут работать отдельно. Эвристики приоритетов NFS оценивать на Scrapland.

**Graphics.** Нужны NV2A vertex microcode, register combiners/texture modes, FFP, depth/stencil, palette/DXT/swizzle, render-to-texture и корректные lifetime/fences. Измерять объём CPU vertex conversion и fallback draws. Достижение меню на трёх generic shaders не является полноценным backend.

**Ownership.** Разделить GPU→GPU sampling, CPU→GPU writes и GPU→CPU readback. Предпочтителен readback по реальному запросу/владению поверхностью, а не полная синхронизация каждого draw. До доказательства сохранения semantics держать диагностический строгий режим. Успех Manhunt `gpu` mode не даёт разрешения игнорировать CPU↔surface coherence в Scrapland.

**GPU diagnostics.** Уже в первом игровом NRO нужны: выбор shader/draw range, bounded capture состояния и shaders, readback выбранного color/depth target, counters unsupported methods и fallback, frame/draw labels, контроль upload rings/fences. Неподдержанный draw должен оставлять однозначное событие. Сравнение цветов, fog, stencil/shadows, видео и save/menu transitions важнее одного красивого кадра.

**Audio и видео.** Для baseline сохранить DSOUND/WMADEC/XMV, явно обработать MMIO, использовать MCPX APU и native sink; отделять APU CPU time от ожиданий. Замерять реальные воспроизведённые samples/s и underruns. По inventory есть Ogg, MP2 и FSB assets; это ещё не карта runtime-декодеров. HLE DirectSound или native media decoder вводить после определения форматов и проверки streaming, notifications, loop/3D semantics и sync.

**Deko3d.** Остаётся кандидатом конечного backend, с гипотезой уменьшить накладные расходы submission и управления ресурсами. До измерений это гипотеза. В референсах нет готового полного deko3d renderer для нашего пути. Потребуются shader translation/compilation в DKSH, покрытие комбинаций и resource coherency. Нельзя автоматически подать в deko3d GLSL/SPIR-V из GL/VK. Официальный [primer](https://github.com/devkitPro/deko3d/blob/master/Primer.md) описывает UAM и DKSH. Ранний прототип: clear/triangle, textured draw, vertex microcode/combiner, depth и render-to-texture выбранного workload; счётчики неподдержанных операций без скрытого перехода на CPU. После проверки картинки сравнить representative raw batches GL/VK/deko3d на консоли при одинаковых частотах. Решение о полноценной реализации принимать по покрытию, стоимости и измеренному выигрышу; низкая скорость неполного адаптера Manhunt не является основанием отказа от deko3d.

**Профиль.** Хранить NRO+ELF+полную config+измеренные CPU/GPU/EMC clocks, handheld/docked mode, сцену/сохранение/input route. Сравнивать одинаковые сцены при одном internal scale, cold/warm shaders раздельно. Записывать median/p95/p99 frame time, pacing, game-time/wall-time, shader stalls, audio и memory high-water. Flip FPS может расти при сломанной симуляции; одного среднего FPS недостаточно. Рабочая первоначальная цель — устойчиво играбельные сцены без необходимости сильного разгона; 30 FPS — ориентир для оценки бюджета, не обещание и не повод менять timestep.

## 7. Что подготовлено и что остаётся непроверенным

Готовы воспроизводимый read-only audit, SHA-256 manifest всех внешних файлов, XBE sections/libraries/imports, статический kernel routing audit, ограниченный `.XTLID` probe, BFPK directory inventory и настоящий план интеграции с критериями завершения.

Не выполнены полный code discovery, signature scanner, CPU conformance, сборка или запуск Scrapland, замеры на Switch и утверждение конкретного backend по производительности. Результаты чужих игр служат основанием для выбора компонентов, а не результатами нашего порта.

Для актуальной документации сверены официальные upstream: [xboxrecomp](https://github.com/sp00nznet/xboxrecomp), [XboxXBERecomp](https://github.com/TGP482/XboxXBERecomp). Их текущие ветки могут отличаться от локальных закреплённых снимков; автоматически обновлять основу по HEAD не следует.
