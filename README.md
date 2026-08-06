# FinderCTL — Управление настройками macOS Finder

## Быстрая установка

```bash
# Через Homebrew (рекомендуется)
brew tap azatisakov/finderctl
brew install finderctl

# Или через uv/pip на macOS
pipx install finderctl
```

## Что это и зачем

**FinderCTL** — это утилита командной строки для централизованного управления настройками Finder на macOS. 

### Проблема, которую решает

Каждый раздел в Finder (рабочий стол, стандартные папки, iCloud, мусорное ведро) хранит свои собственные настройки просмотра:
- Какую колонку сортировать по умолчанию?
- Показывать ли размеры файлов и папок?
- Видимые колонки и их ширина?
- Где новые окна открываются?
- Какая вью по умолчанию — списком, значками, галереей?

Эти настройки разбросаны по `com.apple.finder.plist` (глобальные + контейнеры) и `.DS_Store` файлах в каждой папке. Ручная правка — утомительна и опасна: одна опечатка может сломать Finder или потерять конфигурацию.

**FinderCTL решает это:**
- Применяет единые настройки во все контейнеры единовременно
- Автоматически создаёт бэкап перед каждым изменением
- Проверяет целостность SHA-256 каждого бэкапа
- Поддерживает preview (dry-run) — посмотри что изменится, прежде чем писать
- Восстанавливает из бэкапа одной командой

### Кому это нужно

- **Инженеры и администраторы** — настройка одинакового окружения на нескольких Mac
- **Дизайнеры и контент-менеджеры** — быстрая смена вью, колонок, сортировки
- **Кто чистит рабочий стол** — скрыть жёсткие диски, серверы, внешние носители
- **Кто хочет быстрый доступ к папкам** — сортировка папок сверху, открытие в домашней папке

## Быстрая установка

```bash
uv sync
source .venv/bin/activate
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

Это основная команда. Она:
1. Создаёт бэкап `pre-apply-defaults`
2. Устанавливает сортировку по дате изменения
3. Включает расчёт размеров папок
4. Синхронизирует 12 колонок (видимость, порядок, ширина)
5. Устанавливает глобальные предпочтения (новое окно → домашняя папка, боковая панель, строка состояния и т.д.)

### `finderctl apply`
Применить одну конкретную настройку к выбранному объёму.

```bash
# Сортировка по дате везде
finderctl apply --scope all sortColumn dateModified --no-restart

# Включить иконки в папках на iCloud
finderctl apply --scope icloud showIconPreview True

# Скрыть предпросмотр иконок в мусорке
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
- `calculateAllSizes` — считать размеры папок (True/False)
- `showIconPreview` — показывать эскизы файлов (True/False)
- `useRelativeDates` — относительные даты (сегодня, вчера) (True/False)
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

### `finderctl enforce` (opt-in, Layer B)
Настройка `.DS_Store` в папках. Finder хранит локальные настройки просмотра в скрытом файле `.DS_Store` в каждой папке. FinderCTL может синхронизовать эти настройки:

```bash
# Preview: что изменится в .DS_Store файлах домашней папки
finderctl enforce -p ~ --dry-run --json

# Применить изменения
finderctl enforce -p ~/Documents

# Откатить все изменения .истори
finderctl enforce -p ~/Documents --rollback
```

## Как изменить настройки по умолчанию

Все настройки находятся в `finderctl/config.py`. Измените — примените.

### Глобальные предпочтения Finder

```python
DESIRED_GLOBAL_PREFS = {
    "NewWindowTarget": "PfHm",     # PfHm = домашняя папка, PfDesk = рабочий стол, PfVD = виртуальный десктоп
    "FXPreferredViewStyle": "Nlsv", # Nlsv = список, Gvpt = значки, Flsr = галерея
    "_FXSortFoldersFirst": True,    # Папки сверху
    "ShowSidebar": True,            # Боковая панель
    "ShowStatusBar": True,          # Строка состояния
    "ShowPathbar": True,            # Путь в строке
    "ShowPreviewPane": False,       # Предпросмотр ⌘+⌥+П
    "ShowHardDrivesOnDesktop": True, # Жёсткие диски на рабочем столе
}
```

### Настройки списка файлов

```python
DESIRED_DEFAULT_LIST_VIEW = {
    "sortColumn": "dateModified",   # Сортировать по дате изменения
    "calculateAllSizes": True,      # Показывать размеры папок
    "columns": [
      {"identifier": "name",         "visible": True,  "width": 187},
      {"identifier": "dateModified", "visible": True,  "width": 181},
      {"identifier": "size",         "visible": True,  "width": 97},
      {"identifier": "kind",         "visible": True,  "width": 115},
      # ... остальные колонки: дата создания, метка, версия, комментарии, дата добавления и т.д.
    ],
}
```

### Как применить

```bash
# 1. Отредактировать finderctl/config.py
# 2. Посмотреть, что изменится
finderctl apply-defaults --dry-run --json

# 3. Применить
finderctl apply-defaults --json
```

Бэкап создаётся автоматически перед каждым изменением.

## Глобальные опции

| Флаг | Описание |
|------|----------|
| `--verbose` / `-v` | Подробный вывод (debug логи в stderr) |
| `--quiet` / `-q` | Только критические ошибки |
| `--json` | JSON вместо человеческого вывода |
| `--no-restart` | Не перезапускать Finder после изменения |

## Требования

- Python 3.13+
- macOS 14+ (Sonoma) — 26+ (Tahoe)

## Разработка

```bash
uv sync
source .venv/bin/activate
python -m pytest --cov
mypy --strict finderctl/
ruff check .
```
