# AIwarGame — скилл «Реалистичные 3D-ассеты из GitHub»

Общий навык для ИИ-агента (Arena AI, Mirasim, Claude-подобные клиенты со скиллами): пользователь даёт **ссылку на GitHub-репозиторий** — агент читает задачу и референсы, строит **реалистичную детализированную 3D-модель** в Blender, делает **UV и PBR-текстуры**, рендерит доказательства и возвращает результат **веткой, коммитами и pull request** в тот же репозиторий.

Архетипы: **дома и архитектура** (с интерьером, планировкой и конструкцией), **люди и персонажи** (анатомия, топология под деформацию, кожа, волосы, одежда), **оружие и hard surface** (сквозные каналы, внутренности, механизмы), **пропсы и мебель**, **транспорт и техника**, **окружение и природа**.

Входная точка — [SKILL.md](SKILL.md). Оперативный протокол для агента — [AGENTS.md](AGENTS.md).

## Быстрый старт

**Вариант 1 — есть репозиторий:**

```text
https://github.com/<owner>/<repo> — сделай реалистичный деревенский дом с интерьером и 4K текстурами,
верни результат pull request'ом
```

Агент: склонирует репозиторий → прочитает `README`, `docs/`, issues → создаст `assets/<slug>/` → заполнит `TASK.md` (контракт) → соберёт референсы → пройдёт стадии S0–S10 → запушит ветку `asset/<slug>-<цель>` и откроет PR с доказательствами.

**Вариант 2 — задача текстом, репозитория нет:** агент работает в текущем репозитории и сам создаёт структуру `assets/<slug>/` скриптом `scripts/init_asset_repo.py`.

**Вариант 3 — есть готовый `.blend`:** агент чинит/дорабатывает его, прогоняет аудит и рендерит новый набор доказательств для текущей версии.

## Установка

Скилл — обычная папка с `SKILL.md`. Скопируйте её (или весь репозиторий) в каталог скиллов клиента:

```text
<skills>/realistic-3d-assets/SKILL.md
<skills>/realistic-3d-assets/references/…
<skills>/realistic-3d-assets/scripts/…
```

Вызов в чате: `$realistic-3d-assets` или обычная формулировка задачи — `description` в `SKILL.md` написан так, чтобы скилл подхватывался автоматически.

## Карта репозитория

```text
SKILL.md                     ядро скилла: контракт результата, правила, маршрутизация
AGENTS.md                    короткий операционный протокол для агента
PROMPT_3D_Guns.md            пример подробного боевого брифа (шесть оружейных моделей)
agents/openai.yaml           интерфейс скилла (display name, default prompt)
references/
  github-pipeline.md         GitHub: клонирование, ветки, LFS, PR, CI, секреты
  intake-and-brief.md        приём задачи, контракт, карта «запрос → доказательство»
  workflow-stages.md         стадии S0–S10 и их ворота
  quality-gates.md           матрица приёмки, автопровалы, минимальные наборы доказательств
  archetypes.md              маршрутизация по семействам ассетов
  architecture.md            дома, здания, интерьеры: размеры, конструкция, старение
  characters.md              люди: пропорции, анатомия, топология, кожа, волосы, одежда
  hard-surface.md            оружие, оптика, механизмы: проходы, панели, крепеж, bevel
  props-and-set-dressing.md  мебель, быт, clutter, storytelling-износ
  vehicles-and-machines.md   автомобили, авиация, флот, роботы
  nature-and-environments.md терраин, скалы, растительность, вода, сезоны
  geometry.md                форма, масштаб, Boolean, bevel, нормали, скульпт, ретопология
  texturing-pbr.md           PBR-значения реальных материалов, износ, кожа, ткань, стекло
  uv-baking-maps.md          UV, texel density, baking, наборы карт, trim, UDIM
  rig-and-animation.md       риг, pivot, позы, cloth, props, ролики
  lookdev-and-proofs.md      свет, камера, рендер, состав доказательств, turntable
  game-ready-export.md       ретопология, LOD, collision, glTF/FBX/OBJ/USD/STL, движки
  delivery-and-handoff.md    версии, manifest, отчёт, состав передачи, остановка
  audit-helper.md            скриптовый аудит и валидация репозитория
  safety-and-licensing.md    лицензии, запреты, секреты, приватность
  local-environment.md       Blender, GPU, git/LFS/gh, ffmpeg, кодировки, MCP
  lessons.md                 типовые провалы по всем архетипам
  lessons-pm.md              оружейный кейс (проект ПМ)
  audit-example*.json        примеры конфигураций аудита
  templates/                 TASK.md, asset-state.md, manifest + схема, CONVENTIONS.md,
                             CI workflow, PR-шаблон, issue-форма, .gitattributes, .gitignore
scripts/                     8 скриптов (см. ниже)
blender-asset-workflow/      предыдущая узкая версия скилла (только оружие) — сохранена как есть
```

## Скрипты

Четыре работают на чистом Python 3.9+ (пригодны для CI), четыре — внутри Blender.

| Скрипт | Среда | Назначение |
|---|---|---|
| `init_asset_repo.py` | Python | создать структуру репозитория/ассета, LFS, CI, шаблоны, скопировать валидаторы в `tools/` |
| `validate_asset.py` | Python | структура, manifest, имена, разрешения, LFS, секреты, запрещённые файлы; `--strict` для CI |
| `texture_report.py` | Python | разрешения и наборы карт без Pillow: PNG/JPEG/WebP/TGA/BMP/EXR/HDR/DDS; POT, полнота set, цветовое пространство |
| `gltf_report.py` | Python | валидность glTF/GLB: структура, треугольники, материалы, тангенты, внешние файлы, расширения |
| `audit_blend.py` | Blender | read-only аудит: размеры, топология, позы, сквозные проходы по лучам → JSON PASS/FAIL |
| `make_manifest.py` | Blender | генерация `asset-manifest.json` из `.blend`, сохраняет ручные блоки |
| `render_proofs.py` | Blender | стандартный набор доказательств (силуэты, clay, wireframe, turntable) без сохранения файла |
| `export_asset.py` | Blender | экспорт в glb/gltf/fbx/obj/usd/stl с preflight-проверками и логом |

Примеры запуска — в [references/audit-helper.md](references/audit-helper.md).

## Конвейер

```text
S0 контракт → S1 референсы → S2 блокаут → S3 форма → S4 детали → S5 UV
→ S6 материалы → S7 риг (по запросу) → S8 доказательства → S9 game-ready (по запросу) → S10 PR
```

Каждая стадия закрывается воротами: сохранённый снапшот, измерение, рендер или отчёт скрипта. Детали — [references/workflow-stages.md](references/workflow-stages.md).

## Что агент не делает

- Не создаёт чертежи, CAD и файлы для производства или печати **функционального** оружия (художественный визуальный ассет — можно).
- Не воспроизводит портретное сходство с реальным живым человеком без его согласия; ничего, связанного с несовершеннолетними, в неприемлемом виде.
- Не коммитит секреты, чужие лицензионные ассеты и мусор; не мержит и не закрывает PR без явной просьбы.
- Не переводит ассет в game-ready и не удаляет слои/UV/внутренности ради оптимизации, если этого не просили.
- Останавливается по команде и сохраняет достигнутое состояние.

Полный список — [references/safety-and-licensing.md](references/safety-and-licensing.md).

## История

`blender-asset-workflow/` — исходная узкая версия скилла для оружейных ассетов (Blender/Krita, сквозные стволы, внутренности затвора, bevel). Она сохранена без изменений для существующего проекта; её знания перенесены в общий скилл: `references/hard-surface.md`, `references/rig-and-animation.md`, `references/lessons-pm.md`, `scripts/audit_blend.py`.
