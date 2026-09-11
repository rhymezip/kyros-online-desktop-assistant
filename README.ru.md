<div align="center">

# KYROS

### Голосовой помощник рабочего стола для macOS и Linux

Говорите естественно. Kyros слушает через Gemini Live, выбирает общую
возможность, выполняет действие и сообщает фактический результат.

**macOS 13+** · **Linux / Wayland** · **Hyprland** · **Python 3.10–3.14** · **MIT**

</div>

---

## О проекте

Kyros — локальный клиент для Google Gemini Live API. Он объединяет
двунаправленный голос, компактную панель PyQt6, нативное аудио платформы и
общие инструменты управления рабочим столом.

Путь macOS остаётся нативным: Swift `AVAudioEngine`, Apple voice processing,
Accessibility, Quartz, AppleScript и `zsh`. Linux использует отдельный адаптер
на базе PipeWire, Hyprland/Wayland, AT-SPI2, XDG-порталов и доступных
системных backend'ов.

В проекте нет маршрутизатора команд по фразам, списка разрешённых приложений
или regex-сопоставления. Модель получает общие инструменты и комбинирует их
во время работы. Результаты инструментов проверяются; недоступная возможность
возвращается как реальная ошибка.

Актуальная подробная документация:
[English](README.md) · [Türkçe](README.tr.md)

## Возможности

- Gemini Live с микрофоном, голосовым ответом, прерыванием и восстановлением
  сессии;
- общий shell, инспекция интерфейса, клавиатура/мышь, запуск приложений,
  управление мультимедиа, clipboard, уведомления, чтение веб-страниц и
  поиск;
- Swift voice processing на macOS;
- PipeWire по умолчанию и явный PortAudio fallback на Linux;
- Hyprland IPC, окна, workspace, AT-SPI2, XDG-порталы и X11/XWayland
  fallback'и;
- ограниченные по времени и отменяемые операции;
- краткие события в терминале и подробные вращаемые логи;
- установка и удаление с учётом фактического владения ресурсами.

## Поддерживаемые платформы

| Платформа | Основной путь | Примечание |
| --- | --- | --- |
| macOS 13+ | Swift audio bridge + Accessibility/Quartz | Нужны Apple Command Line Tools и разрешения приватности. |
| Linux / Wayland | PipeWire + `linux_desktop` | Основная цель — Hyprland; порталы и X11 используются при наличии. |
| Linux-дистрибутивы | `pacman`, `apt`, `dnf`, `zypper` | Используются официальные репозитории. |
| Windows | Не поддерживается | Реализации Windows нет. |

## Быстрый старт

~~~bash
git clone https://github.com/rhymezip/kyros-online-desktop-assistant.git
cd kyros-online-desktop-assistant
chmod +x install.sh uninstall.sh
bash install.sh
venv/bin/python main.py
~~~

`install.sh` сам выбирает macOS или Linux и устанавливает только зависимости
выбранной платформы. При первом запуске добавьте и проверьте прямой ключ
Google Gemini в панели Settings либо задайте `GEMINI_API_KEY` заранее.

## Установка и удаление

План можно посмотреть без изменений:

~~~bash
bash install.sh --dry-run
~~~

На Linux installer определяет менеджер пакетов и устанавливает PipeWire,
WirePlumber, инструменты скриншотов и ввода, clipboard, MPRIS, уведомления,
polkit, AT-SPI2, порталы и зависимости PyGObject из официальных репозиториев.
Он не использует AUR, внешний installer, `sudo pip`,
`--break-system-packages` или частичное обновление через `pacman -Sy`.

Если нужны Linux-настройки `uinput`, installer заранее объясняет операцию и
просит пароль администратора. Пароль не отправляется в Gemini и не сохраняется;
он используется только системным механизмом авторизации для описанной операции.

PortAudio на Linux устанавливается отдельно:

~~~bash
bash install.sh --with-portaudio
venv/bin/python main.py --audio-backend portaudio
~~~

Удаление сначала можно проверить:

~~~bash
bash uninstall.sh --dry-run
bash uninstall.sh
~~~

Uninstaller:

- удаляет только пакеты Linux, которых не было до установки Kyros и которые
  записаны в manifest;
- не выполняет общий `autoremove` и не использует `pacman -Rs`;
- удаляет `venv` и macOS audio binary только если их создал Kyros;
- убирает только собственные, не изменённые service/permission-файлы;
- сохраняет `config/local.json` по умолчанию, чтобы не потерять ключ.

`--yes` пропускает подтверждения. `--purge-config` отдельно запрашивает
удаление локальной конфигурации. Если manifest отсутствует, существующие
пакеты и окружения не угадываются и не удаляются.

## Запуск

~~~bash
venv/bin/python main.py
venv/bin/python main.py --text
venv/bin/python main.py --no-panel
venv/bin/python main.py --doctor
venv/bin/python main.py --audio-check
venv/bin/python main.py --debug
~~~

`--doctor` выполняет только локальную диагностику и не вызывает Gemini.
`--audio-check` проверяет выбранный audio backend без API. `--text` использует
Live API, но не открывает микрофон.

## Инструменты

| Инструмент | macOS | Linux | Назначение |
| --- | :---: | :---: | --- |
| `run_shell` | ✓ | ✓ | Общий shell от имени пользователя: `zsh` или `/bin/sh`. |
| `run_applescript` | ✓ | — | AppleScript/JXA и native macOS automation. |
| `computer` | ✓ | ✓ | Инспекция и управление интерфейсом через доступные backend'ы. |
| `linux_desktop` | — | ✓ | Hyprland/Wayland, AT-SPI2, окна, workspace, ввод, скриншоты, clipboard, запуск и уведомления. |
| `launch_app` | ✓ | ✓ | Приложение, desktop entry, URI, путь или argv без shell. |
| `media_control` | ✓ | ✓ | Управление выбранным проигрывателем; MPRIS/`playerctl` на Linux. |
| `clipboard` | ✓ | ✓ | Чтение и запись clipboard. |
| `read_web` | ✓ | ✓ | Чтение HTTP(S) без открытия браузера. |
| Google Search | ✓ | ✓ | Нативный поиск Gemini для актуальных запросов. |
| `session_control` | ✓ | ✓ | Явные wake, standby и stop. |

В коде нет отдельных веток для Spotify, Notes или Telegram. Запуск —
универсальный `launch_app`, мультимедиа — `media_control`, а видимые действия
сначала инспектируются и затем проверяются.

## Linux и Hyprland

`linux_desktop` инспектирует реальные окна, мониторы, workspace и
AT-SPI2-дерево, если их предоставляет текущая сессия. Он также умеет
скриншоты через `grim`/`slurp` или портал, Unicode-ввод через `wtype`,
низкоуровневый ввод через `ydotoold`/портал/X11, clipboard, запуск,
уведомления и `capabilities`.

Модель должна сначала выполнить inspect и использовать возвращённые PID,
accessibility path, role, label, address, monitor или workspace. После
изменения состояния выполняется проверка. Если Wayland или политика desktop
отказывает в операции, Kyros возвращает ошибку, а не выдумывает успех.

## macOS и аудио

macOS использует Swift audio bridge. После первого запуска могут потребоваться
Microphone, Accessibility, Screen Recording и Automation. Полный чеклист:
[MAC_TEST.md](MAC_TEST.md).

Linux использует PipeWire через `pw-record`/`pw-play`. Для Linux нет Apple
voice-processing; при слышимом эхо используйте наушники или корректно
настроенный граф PipeWire/WirePlumber. Для изменения native audio на macOS:

~~~bash
bash build_audio.sh
venv/bin/python main.py --audio-check
~~~

Чеклист Hyprland находится в [LINUX_TEST.md](LINUX_TEST.md).

## Конфигурация

`GEMINI_API_KEY` и `GEMINI_MODEL` из environment имеют приоритет над значениями
в `config/local.json`. По умолчанию используется
`gemini-2.5-flash-native-audio-latest`. Installer создаёт локальный файл с
правами `0600`; он игнорируется Git.

~~~bash
cp config/local.json.example config/local.json
chmod 600 config/local.json
export GEMINI_API_KEY="your-direct-google-gemini-key"
~~~

Доступные runtime-переменные: `KYROS_AUDIO_BACKEND`,
`KYROS_INPUT_DEVICE` и `KYROS_OUTPUT_DEVICE`. Kyros требует прямой Google
Gemini API key для Live `bidiGenerateContent`; OpenAI-совместимый ключ не
является заменой.

## Диагностика, логи и Git

~~~bash
venv/bin/python -m unittest discover -s tests -v
tail -f logs/kyros.log
git status --short --ignored
git check-ignore -v config/local.json .env .kyros logs venv native/kyros-audio
git add -A --dry-run
~~~

`.gitignore` охватывает macOS и Linux: ключи, environment-файлы, `venv`,
Python cache, логи, installer state, native build products, app bundles,
редакторские файлы, большие audio/model-файлы и временные файлы.

Правило ignore работает только для ещё не отслеживаемых путей. Если secret
уже был закоммичен, его нужно удалить из истории и заменить ключ;
`.gitignore` не делает tracked-файл untracked.

## Структура

~~~text
.
├── main.py
├── config/                 # settings.py и local.json.example
├── core/                   # Live, audio, UI, tools, web и diagnostics
├── gui/panel.py            # PyQt6 panel/settings
├── native/                 # macOS Swift bridge и launcher sources
├── scripts/                # Linux package/permission lifecycle
├── system/                 # scoped uinput и ydotoold templates
├── tests/                  # unit и contract tests
├── install.sh
├── uninstall.sh
├── build_audio.sh
├── requirements*.txt
├── MAC_TEST.md
├── LINUX_TEST.md
├── LICENSE
└── README.md / README.tr.md
~~~

## Лицензия

Kyros распространяется по [MIT License](LICENSE).
