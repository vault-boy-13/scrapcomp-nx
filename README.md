# scrapcomp-nx

[English](#english) · [Русский](#русский)

## English

An upcoming unofficial static recompilation of **Scrapland**, bringing the **original Xbox version** to **Nintendo Switch**.

The goal is to translate the original Xbox executable's x86 code into C, compile it for ARM64, and run the game through an adapted runtime on Nintendo Switch.

> [!IMPORTANT]
> **This project is in early development.** There is no playable Nintendo Switch build yet; Scrapland does not currently boot on Nintendo Switch.
>
> **No game files are distributed.** Working with the project requires your own lawfully obtained copy of the original Xbox game.

### Current status

- Analysis, recompilation, and PC/Switch build tools are prepared.
- Initial analysis of the Xbox executable and preliminary C code generation are complete.
- A native Windows diagnostic `.exe` reaches the menu and a controllable first scene. A repeated ten-minute host scenario passes bounded audio and liveness checks, with observed movement, camera and gameplay after requested resumes. Full-game validation is ongoing; unrecovered guest targets still stop execution when reached. See the [host milestone](docs/HOST_MILESTONE.md).
- Runtime libraries and standalone test NROs have been built; runtime, OpenGL, and deko3d probes have been checked in Ryubing.
- Playable game startup, rendering, and operation on a physical Nintendo Switch still need to be implemented and verified.

The test NRO results validate individual parts of the development environment. They do not establish that the game works or demonstrate its performance on a console.

### Foundation and acknowledgements

CPU recompilation and the runtime are based on [xboxrecomp](https://github.com/sp00nznet/xboxrecomp), including its development in [nfsu2-sw](https://github.com/antoxa2584x/nfsu2-sw).

The project draws on research into successful original Xbox ports: [NFS Underground](https://github.com/antoxa2584x/nfsu1-sw), [NFS Underground 2](https://github.com/antoxa2584x/nfsu2-sw), [Manhunt](https://github.com/baezahuertaelias/manhunt1_nx), and [BLACK](https://github.com/gerisson1996/BLACK-NX-PORT). Thanks to their authors and contributors for the tools, research, and published solutions. Third-party components retain their respective licences and copyright notices.

The technical approach and next milestones are described in the [project plan](docs/PORTING_ROUTE.md), currently in Russian.

See [third-party notices](THIRD_PARTY_NOTICES.md) for patch provenance and upstream licence texts.

### Copyright

**Scrapland** was developed by the Spanish studio [MercurySteam](https://www.mercurysteam.com/en/games/scrapland/) (**Mercury Steam Entertainment S.L.**). Rights to Scrapland belong to MercurySteam and the respective rights holders. All rights to the original game, its code, name, artwork, music, and other materials remain with their owners.

**scrapcomp-nx** is an independent, unofficial project. It is not affiliated with MercurySteam, Microsoft, or Nintendo and does not claim their endorsement or support.

The published repository files contain no original game source code, XBE, game assets, or C code generated from the game. Game data, recompilation output, builds, and captures remain in local directories excluded from Git. Proprietary SDKs, system firmware, and keys are not distributed either.

Nintendo, Nintendo Switch and Nintendo Switch Lite are trademarks of Nintendo
Co., Ltd. Copyrights in Nintendo software and other proprietary materials
belong to their respective rights holders. Product names are used to identify
compatible hardware.

The project is intended for research and compatibility with your own lawfully obtained copy of the game. It grants no rights to the original materials and is not intended for their unauthorised distribution.

---

## Русский

Будущая неофициальная статическая рекомпиляция **Scrapland** с **Xbox Original** для **Nintendo Switch**.

Цель проекта — преобразовать x86-код оригинальной Xbox-версии в C, скомпилировать его для ARM64 и обеспечить работу игры через адаптированный runtime на Nintendo Switch.

> [!IMPORTANT]
> **Проект находится на ранней стадии разработки.** Готовой игровой сборки для Nintendo Switch пока нет; Scrapland ещё не запускается на Nintendo Switch.
>
> **Игровые файлы не распространяются.** Для работы с проектом необходима собственная законно полученная копия оригинальной Xbox-версии игры.

### Текущее состояние

- Подготовлены инструменты анализа, рекомпиляции и сборки для PC и Switch.
- Выполнены первоначальный анализ Xbox executable и предварительная генерация C-кода.
- Нативный диагностический Windows `.exe` доходит до меню и управляемой первой сцены. Повторный десятиминутный сценарий проходит ограниченные проверки звука и непрерывности работы; подтверждены движение, камера и игровая сцена после запросов возврата из паузы. Проверка всей игры продолжается; при достижении невосстановленных гостевых переходов исполнение по-прежнему останавливается. См. [результаты этапа на ПК](docs/HOST_MILESTONE.md).
- Собраны runtime-библиотеки и отдельные тестовые NRO; runtime, OpenGL и deko3d проверены в Ryubing.
- Полноценный игровой запуск, рендеринг и работоспособность на физической Nintendo Switch ещё предстоит реализовать и проверить.

Результаты тестовых NRO подтверждают готовность отдельных компонентов окружения. Они не подтверждают работоспособность самой игры или её производительность на консоли.

### Основа проекта и благодарности

Основой CPU-рекомпиляции и runtime служит [xboxrecomp](https://github.com/sp00nznet/xboxrecomp), в том числе его развитие в [nfsu2-sw](https://github.com/antoxa2584x/nfsu2-sw).

При подготовке проекта изучены успешные порты Xbox Original: [NFS Underground](https://github.com/antoxa2584x/nfsu1-sw), [NFS Underground 2](https://github.com/antoxa2584x/nfsu2-sw), [Manhunt](https://github.com/baezahuertaelias/manhunt1_nx) и [BLACK](https://github.com/gerisson1996/BLACK-NX-PORT). Благодарим авторов и участников этих проектов за инструменты, исследования и опубликованные решения. Сторонние компоненты сохраняют собственные лицензии и уведомления об авторских правах.

Технический маршрут и дальнейшие этапы описаны в [плане проекта](docs/PORTING_ROUTE.md).

Происхождение patches и тексты лицензий upstream указаны в [уведомлениях о сторонних компонентах](THIRD_PARTY_NOTICES.md).

### Авторские права

**Scrapland** — игра испанской студии [MercurySteam](https://www.mercurysteam.com/en/games/scrapland/) (**Mercury Steam Entertainment S.L.**). Права на Scrapland принадлежат MercurySteam и соответствующим правообладателям. Все права на оригинальную игру, её код, название, графику, музыку и другие материалы сохраняются за их владельцами.

Nintendo, Nintendo Switch и Nintendo Switch Lite — товарные знаки Nintendo
Co., Ltd. Авторские права на программное обеспечение Nintendo и другие
проприетарные материалы принадлежат соответствующим правообладателям.
Названия продуктов используются для обозначения совместимого оборудования.

**scrapcomp-nx** — независимый неофициальный проект. Он не связан с MercurySteam, Microsoft или Nintendo и не заявляет об их одобрении или поддержке.

Публикуемые файлы репозитория не содержат оригинальных исходников игры, XBE, игровых ресурсов или сгенерированного из игры C-кода. Игровые данные, результаты рекомпиляции, сборки и захваты остаются в локальных каталогах, исключённых из Git. Проприетарные SDK, системные прошивки и ключи также не распространяются.

Проект предназначен для исследования и совместимости с собственной законно полученной копией игры. Он не предоставляет прав на оригинальные материалы и не предназначен для их несанкционированного распространения.
