# FinderCTL — Управление настройками macOS Finder

**FinderCTL** — это утилита командной строки для централизованного управления настройками Finder на macOS. Она применяет единые настройки ко всем контейнерам, создаёт верифицированные бэкапы и позволяет синхронизировать `.DS_Store` в папках.

## Что решает

Каждый раздел Finder (рабочий стол, документы, iCloud, мусорное ведро) хранит свои собственные настройки просмотра:
- Сортировка по умолчанию
- Видимые колонки и ширина
- Расчёт размеров папок
- Размер иконок и текста
- Где открываются новые окна

Эти настройки разбросаны по `com.apple.finder.plist` и `.DS_Store` файлам в каждой папке. Ручная правка утомительна и рискованна. FinderCTL решает это централизованно и безопасно.

## Установка

### Способ 1: Homebrew (рекомендуется)

Homebrew — самый простой способ. Устанавливается один раз, потом `finderctl` доступен глобально из любого терминала.

```bash
# 1. Подключить tap
brew tap azatisakov/finderctl

# 2. Установить
brew install finderctl

# 3. Проверить
finderctl --help
```

После этого `finderctl` доступен везде. Никаких `cd`, `uv run`, `.venv` не нужно.

### Способ 2: uv + виртуальное окружение

Подходит для разработки или если хочешь держать зависимости изолированными.

```bash
# 1. Скачать проект
git clone https://github.com/azatisakov/FinderCTL.git
cd FinderCTL

# 2. Создать venv и установить зависимости
uv sync

# 3. Активировать venv
source .venv/bin/activate

# 4. Проверить
finderctl --help
```

### Способ 3: Скачать с GitHub и запустить локально

Без установки, без `git clone`, без `uv`. Подходит для разового использования.

```bash
# 1. Скачать архив релиза
curl -L -o finderctl.tar.gz https://github.com/azatisakov/FinderCTL/archive/v1.0.0.tar.gz

# 2. Распаковать
tar -xzf finderctl.tar.gz
cd FinderCTL-1.0.0

# 3. Создать venv и установить зависимости
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 4. Запустить
finderctl --help
```

## Как выйти из finderctl

FinderCTL — это CLI утилита, она не запускает долгий процесс. Каждая команда выполняется и завершается. Чтобы выйти из режима, в который ты попал:

- Если активирован `.venv` — выйди командой:
  ```bash
  deactivate
  ```
- Если хочешь выйти из папки проекта — перейди в домашнюю:
  ```bash
  cd ~
  ```
- Если просто хочешь закрыть текущую команду — нажми `Ctrl+C`

## Быстрый старт

### 1. Проверить статус

```bash
finderctl status
```

Вывод: найден ли plist, версия macOS и Finder, количество секций и бэкапов.

### 2. Создать бэкап

```bash
finderctl backup --label до-изменений
```

Бэкап сохраняется в `~/.finderctl/backups/` с проверкой SHA-256.

### 3. Применить стандартные настройки

```bash
# Посмотреть, что изменится
finderctl apply-defaults --dry-run --json

# Применить
finderctl apply-defaults --json
```

Это основная команда. Она:
1. Создаёт бэкап `pre-apply-defaults`
2. Устанавливает сортировку по дате изменения
3. Включает расчёт размеров папок (`calculateAllSizes`)
4. Синхронизирует 12 колонок (видимость, порядок, ширина)
5. Устанавливает глобальные предпочтения (новое окно → домашняя папка, боковая панель, строка состояния)

### 4. Настроить `.DS_Store` в папках (опционально)

Finder хранит локальные настройки в `.DS_Store` в каждой папке. Чтобы они тоже соответствовали желаемым:

```bash
# Preview: что изменится
finderctl enforce -p ~ --dry-run --json

# Применить
finderctl enforce -p ~/Documents

# Откатить
finderctl enforce -p ~/Documents --rollback
```

## Команды

### `finderctl status`

Проверить текущее состояние Finder и резервных копий.

```bash
finderctl status           # человеческий вывод
finderctl status --json    # JSON для скриптов
```

Вы увидите: найден ли plist, доступен ли для чтения/записи, версия macOS и Finder, количество секций настроек, число бэкапов.

### `finderctl backup`

Создать верифицированный бэкап текущего `com.apple.finder.plist`.

```bash
finderctl backup --label pre-change      # с ярлыком
finderctl backup --no-verify             # пропустить SHA-256 проверку (не рекомендуется)
finderctl backup --json                  # вывести JSON
```

Бэкапы хранятся в `~/.finderctl/backups/` с sidecar `.sha256` для проверки целостности.

### `finderctl apply-defaults`

Применить стандартные настройки FinderCTL ко всем контейнерам.

```bash
finderctl apply-defaults --dry-run --json  # посмотреть, что изменится
finderctl apply-defaults --json            # применить
```

### `finderctl apply`

Применить одну конкретную настройку к выбранному объёму.

```bash
# Сортировка по дате везде
finderctl apply --scope all sortColumn dateModified --no-restart

# Включить предпросмотр иконок на iCloud
finderctl apply --scope icloud showIconPreview True

# Скрыть предпросмотр в мусорке
finderctl apply --scope trash showIconPreview False

# Индивидуальная папка
finderctl apply --scope folder:Documents iconSize 32
```

**Доступные scope:**

| Scope | Что затрагивает |
|-------|----------------|
| `default` | Корневой шаблон (`FK_DefaultListViewSettingsV2`) |
| `all` | Все контейнеры сразу |
| `standard` | Стандартные папки (рабочий стол, документы и т.д.) |
| `desktop` | Только рабочий стол |
| `icloud` | Только iCloud Drive |
| `trash` | Мусорное ведро |
| `package` | Пакеты (приложения, dmg) |
| `folder:<key>` | Индивидуальная папка |

**Разрешённые поля:**

- `sortColumn` — по чём сортировать (`name`, `dateModified`, `size`, `kind` и др.)
- `calculateAllSizes` — считать размеры папок (`True`/`False`)
- `showIconPreview` — показывать эскизы файлов (`True`/`False`)
- `useRelativeDates` — относительные даты (сегодня, вчера) (`True`/`False`)
- `textSize` — размер текста
- `iconSize` — размер иконок
- `viewOptionsVersion` — версия настроек вью

### `finderctl clean`

Очистить старые и повреждённые бэкапы.

```bash
finderctl clean --keep 5             # оставить 5 последних
finderctl clean --keep 5 --verify    # перепроверить SHA-256 перед удалением
finderctl clean --dry-run --json     # посмотреть, что удалится
```

### `finderctl restore`

Восстановить настройки из бэкапа.

```bash
finderctl restore              # восстановить последний
finderctl restore pre-change   # восстановить по ярлыку
finderctl restore --dry-run    # посмотреть, что изменится
```

### `finderctl doctor`

Диагностика: проверка plist, бэкапов, версии macOS.

```bash
finderctl doctor               # список проверок с иконками
finderctl doctor --json      # JSON-отчёт
finderctl doctor --fix       # попытаться исправить
```

### `finderctl enforce` (опционально)

Настройка `.DS_Store` в папках. Finder хранит локальные настройки просмотра в скрытом файле `.DS_Store` в каждой папке. FinderCTL может синхронизовать эти настройки.

```bash
# Preview: что изменится в .DS_Store файлах домашней папки
finderctl enforce -p ~ --dry-run --json

# Применить изменения
finderctl enforce -p ~/Documents

# Откатить все изменения
finderctl enforce -p ~/Documents --rollback
```

## Глобальные опции

| Флаг | Описание |
|------|----------|
| `--verbose` / `-v` | Подробный вывод (debug логи в stderr) |
| `--quiet` / `-q` | Только критические ошибки |
| `--json` | JSON вместо человеческого вывода |
| `--no-restart` | Не перезапускать Finder после изменения |
| `--config` / `-c` | Путь к альтернативному конфигу |
| `--help` | Справка |

## Как изменить настройки по умолчанию

Все настройки находятся в `finderctl/config.py`. Измените — примените.

### Глобальные предпочтения Finder

```python
DESIRED_GLOBAL_PREFS = {
    "NewWindowTarget": "PfHm",     # PfHm = домашняя папка, PfDesk = рабочий стол, PfVD = виртуальный десктоп
    "FXPreferredViewStyle": "Nlsv", # Nlsv = список, Gvpt = значки, Flsr = галерея
    "FXPreferredGroupBy": "Kind",   # Группировать по типу
    "FXArrangeGroupViewBy": "Name", # Сортировать группы по имени
    "_FXSortFoldersFirst": True,    # Папки сверху
    "ShowSidebar": True,            # Боковая панель
    "ShowStatusBar": True,          # Строка состояния
    "ShowPathbar": True,            # Путь в строке
    "ShowPreviewPane": False,       # Предпросмотр ⌘+⌥+П
    "ShowHardDrivesOnDesktop": True, # Жёсткие диски на рабочем столе
    "ShowExternalHardDrivesOnDesktop": True, # Внешние диски
    "ShowMountedServersOnDesktop": False,     # Серверы
    "ShowRemovableMediaOnDesktop": False,     # Внешние носители
}
```

### Настройки списка файлов

```python
DESIRED_DEFAULT_LIST_VIEW = {
    "sortColumn": "dateModified",   # Сортировать по дате изменения
    "iconSize": 16.0,               # Размер иконок
    "textSize": 13.0,               # Размер текста
    "showIconPreview": True,        # Показывать эскизы
    "useRelativeDates": True,       # Относительные даты
    "calculateAllSizes": True,      # Показывать размеры папок
    "viewOptionsVersion": 1,        # Версия настроек
    "columns": [
      {"identifier": "name",         "visible": True,  "width": 187},
      {"identifier": "dateModified", "visible": True,  "width": 181},
      {"identifier": "size",         "visible": True,  "width": 97},
      {"identifier": "kind",         "visible": True,  "width": 115},
      {"identifier": "dateCreated",  "visible": False, "width": 181},
      {"identifier": "label",        "visible": False, "width": 100},
      {"identifier": "version",      "visible": False, "width": 75},
      {"identifier": "comments",     "visible": False, "width": 300},
      {"identifier": "dateLastOpened", "visible": False, "width": 190},
      {"identifier": "dateAdded",    "visible": False, "width": 181},
      {"identifier": "invitationStatus", "visible": False, "width": 210},
    ],
}
```

### 3-шаговый процесс применения изменений

```bash
# 1. Отредактировать finderctl/config.py
# 2. Посмотреть, что изменится
finderctl apply-defaults --dry-run --json

# 3. Применить (бэкап создаётся автоматически)
finderctl apply-defaults --json
```

## Окружение и проверенные версии

FinderCTL разрабатывается и тестируется на macOS Tahoe. Ниже актуальные данные окружения, на котором проверялась эта версия.

| Компонент | Версия / значение |
|---|---|
| macOS | 26.6 (Tahoe) |
| Finder | 26.4 |
| Python | 3.13+ |
| Архитектура | arm64 |
| Рабочая директория | `/Users/zeefiles/Projects/FinderCTL` |
| Бэкапы | `~/.finderctl/backups/` |
| Конфиг | `finderctl/config.py` |
| Homebrew tap | `azatisakov/finderctl` |
| Деплой-тег | `v1.0.0` |

### Установленные зависимости

- `typer`
- `ds-store`
- `mac-alias`
- `click`
- `shellingham`

## Требования

- macOS 14+ (Sonoma) — 26+ (Tahoe)
- Python 3.13+ (только для установки из исходников)
- Homebrew (только для установки через brew)

## Разработка

```bash
git clone https://github.com/azatisakov/FinderCTL.git
cd FinderCTL
uv sync
source .venv/bin/activate

# Запуск
finderctl --help

# Тесты
python -m pytest --cov

# Линт/типы
mypy --strict finderctl/
ruff check .
```

## Лицензия

MIT
