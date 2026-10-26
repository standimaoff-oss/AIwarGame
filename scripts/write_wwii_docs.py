#!/usr/bin/env python3
"""Write task/state/README/source docs and the visual overview contact sheet."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SLUGS = ("ppsh-41", "mosin-m91-30", "mosin-m91-30-pu", "nagant-m1895")
BRANCH = "arena/64d1db80-aiwargame"

META = {
    "ppsh-41": {
        "title": "ППШ-41",
        "name": "ППШ-41 с 71-зарядным барабанным магазином",
        "length": "843 мм",
        "barrel": "269 мм",
        "source": "Wikipedia; MuseumOfWeapon; Dockery Armory",
        "choice": "поздний военный выпуск, деревянный приклад, барабан на 71 патрон и перфорированный кожух ствола",
    },
    "mosin-m91-30": {
        "title": "Мосин обр. 1891/30",
        "name": "Винтовка Мосина обр. 1891/30 с механическим прицелом",
        "length": "1232 мм",
        "barrel": "730 мм",
        "source": "Wikipedia; Sniper Central; IWM",
        "choice": "рядовая пехотная винтовка с открытыми механическими прицельными приспособлениями",
    },
    "mosin-m91-30-pu": {
        "title": "Мосин обр. 1891/30 ПУ",
        "name": "Винтовка Мосина обр. 1891/30 с прицелом ПУ 3,5×",
        "length": "1232 мм",
        "barrel": "730 мм",
        "source": "Wikipedia; Sniper Central; Russian Mosin Nagant; Guns & Ammo; AWM",
        "choice": "снайперский вариант с боковым кронштейном, полым корпусом прицела ПУ длиной 169 мм и опущенной рукоятью затвора",
    },
    "nagant-m1895": {
        "title": "Наган обр. 1895",
        "name": "Револьвер Нагана обр. 1895",
        "length": "235 мм",
        "barrel": "114 мм",
        "source": "Wikipedia; Smithsonian; Modern Firearms; Pritzker Military Museum",
        "choice": "7-зарядный барабан, ствол 114 мм, тёмные щёчки рукояти",
    },
}

SOURCES_MD = """# Источники и референсы

Все внешние изображения использовались только для визуального изучения силуэта.
Файлы изображений в репозиторий не копировались; 3D-геометрия и текстуры созданы
с нуля процедурно. Маркировки на моделях вымышленные.

| Источник | URL | Вариант /用途 | Лицензия / ограничение |
|---|---|---|---|
| Wikipedia — PPSh-41 | https://en.wikipedia.org/wiki/PPSh-41 | длина 843 мм, ствол 269 мм, калибр и магазины | CC BY-SA |
| MuseumOfWeapon — PPSh-41 | https://sites.google.com/view/museumofweapon/collections/submachine-guns/ppsh-41-eng | независимое подтверждение 843 / 269 мм | справочный сайт |
| Dockery Armory — PPSh-41 | https://dockeryarmory.com/ppsh-41/ | боковые фотографии позднего ППШ-41 с барабаном | визуальный референс, файлы не скопированы |
| Wikipedia — Mosin–Nagant | https://en.wikipedia.org/wiki/Mosin%E2%80%93Nagant | M91/30: 1232 / 730 мм; ПУ 3,5× | CC BY-SA |
| Sniper Central — M1891/30 Sniper | https://snipercentral.com/mosin-nagant-189130-sniper/ | 1232 / 729 мм, снайперская комплектация | справочный сайт |
| Imperial War Museums — M1891/30 Sniper | https://www.iwm.org.uk/collections/item/object/30033634 | музейный экземпляр, длина 1230 мм | музейный каталог |
| Russian Mosin Nagant — PU scope | https://boydhouse.com/darryl/russianmosinnagant/sniper_section.html | длина прицела ПУ 169 мм | справочный сайт |
| Guns & Ammo — PU scope | https://www.gunsandammo.com/editorial/best-world-war-ii-sniper-rifle-3-mosin-nagant/527411 | кратность 3,5× и диаметр трубы ~28,7 мм | визуально-справочный источник |
| Australian War Memorial — PU rifle | https://www.awm.gov.au/collection/C238955 | боковой кронштейн и съёмный ПУ | музейный каталог |
| Wikipedia — Nagant M1895 | https://en.wikipedia.org/wiki/Nagant_M1895 | длина 235 мм, ствол 114 мм, 7 патронов | CC BY-SA |
| Smithsonian — Russian M1895 Nagant | https://americanhistory.si.edu/collections/object/nmah_415470 | музейные габариты ~232 мм | музейный каталог |
| Modern Firearms — Nagant m.1895 | https://modernfirearms.net/en/handguns/double-action-revolvers/russia-double-action-revolvers/nagan-obr-1895-eng/ | длина 230 мм, ствол 114 мм | справочный сайт |
| Pritzker Military Museum — Nagant 1928 | https://www.pritzkermilitary.org/explore/museum/digital-collection/view/oclc/1035845981 | длина ~240 мм, год выпуска | музейный каталог |
| AllOutdoor — Nagant M1895 | https://www.alloutdoor.com/2026/04/15/cr-130-nagant-m1895-revolver-p3/ | боковой силуэт и детали рукояти | визуальный референс, файлы не скопированы |

## Разброс источников

- ППШ-41: 843 мм у Wikipedia/MuseumOfWeapon и 849 мм у Dockery Armory; в модель заложены 843 мм.
- Мосин M91/30: 1230–1234 мм в зависимости от источника; в модель заложены 1232 мм.
- Наган M1895: 220–240 мм у разных музеев и справочников; в модель заложены 235 мм по Wikipedia.
- Прицел ПУ: 169 мм по Russian Mosin Nagant и 6,65 дюйма (~169 мм) по Guns & Ammo; в модель заложены 169 мм.

## Права

Процедурные PBR-карты созданы `scripts/generate_wwii_textures.py` и не содержат сторонних
изображений. Текстовые статьи и музейные каталоги используются как справочная информация;
их содержимое не копируется в файлы ассетов.
""".replace("用途", "что взято")


def stats(slug: str) -> dict:
    return json.loads((ASSETS / slug / "manifest" / "build-stats.json").read_text(encoding="utf-8"))


def task_md(slug: str) -> str:
    m = META[slug]
    s = stats(slug)
    return f"""# TASK — {m['name']}

Статус: `review` · Архетип: `hard_surface` · Ветка: `{BRANCH}` · Issue: не заведён.

## Предмет

Визуальный high-poly 3D-ассет **{m['name']}**. Выбранный вариант: {m['choice']}.
Это художественная модель для рендера/превью, а не CAD, не чертёж и не инструкция
по изготовлению или ремонту оружия.

## Источники

{m['source']}. Подробные URL и разброс значений — в `web_refs/sources.md`.

## Фиксированные допущения

- Единицы: метры, `scale_length = 1.0`, Z-up. Ось ствола/дула — +X, правая сторона — −Y,
  мировая точка (0,0,0) — ось канала ствола у казённого среза.
- Общая длина: **{m['length']}**, длина ствольной части: **{m['barrel']}**.
- Разрешение текстур: 1K (1024×1024) — выбрано как компромисс для четырёх ассетов.
- Движок, LOD, collision, риг и анимация не заданы; game-ready экспорт не заказан.
- Серийные номера и надписи вымышленные.

## Критерии приёмки

1. Редактируемый `.blend` с именованными коллекциями и отдельными деталями/контролами.
2. Реальный сквозной канал ствола с внутренними стенками, а не чёрный диск; многолучевая
   проверка в `audit/audit-report.json`.
3. UV-развёртка `UVMap` у всех мешей; шесть полных PBR-наборов
   (`BaseColor`, `Roughness`, `Metallic`, `Normal`, `AO`) в `textures/`.
4. Доказательства не старее модели: hero, right/left/top силуэты, дульный срез, макро канала,
   clay и turntable GIF в `renders/`.
5. `manifest/asset-manifest.json` схемы v2 и `audit/audit-report.json` со статусом `PASS`.
6. Текущие размеры и решения зафиксированы в `asset-state.md`; источники — в `web_refs/sources.md`.

## Не входит в задачу

- Game-ready оптимизация, LOD, collision, экспорт в Unreal/Unity/glTF.
- Функциональные размеры патронника, нарезов, УСМ и других критических узлов.
- Анимация, скелет, симуляция и звук.
- Копирование чужих 3D-моделей, сканов или текстур.

## Текущие числовые факты

- BBox: {s['bbox_mm'][0]:.1f} × {s['bbox_mm'][1]:.1f} × {s['bbox_mm'][2]:.1f} мм.
- Объектов: {s['object_count']}; треугольников (evaluated): {s['triangle_count']}.
- Blender: {s['blender_version']}; рендер: {s['render_engine']} (CPU).
"""


def state_md(slug: str) -> str:
    m = META[slug]
    s = stats(slug)
    controls = ", ".join(f"`{name}`" for name in s["pivot_controls"]) or "нет"
    return f"""# asset-state — {m['title']}

Статус: `review` · Версия: `v001_procedural` · Ветка: `{BRANCH}`

## Текущий файл

- Источник: `source/{slug}.blend` — активный и единственный `.blend` в папке ассета.
- Генератор: `scripts/build_wwii_arms.py` + `scripts/wwii_arms_lib.py`.
- Текстуры: `scripts/generate_wwii_textures.py`.
- Рендеры: `scripts/render_wwii_proofs.py`.
- Blender: {s['blender_version']}, Cycles CPU.

## Единицы и система координат

Метры, `scale_length = 1.0`, Z-up. Дуло +X, верх +Z, правая сторона −Y.
Начало координат — ось канала ствола у казённого среза. Нормализация по длине:
factor = {s['normalization_factor']}.

## Размеры

- Evaluated bbox: **{s['bbox_mm'][0]:.1f} × {s['bbox_mm'][1]:.1f} × {s['bbox_mm'][2]:.1f} мм**.
- Габарит X: {m['length']} (источник {m['source']}).
- Ствольная часть: {m['barrel']}.
- Y/Z и小型 детали — дизайн-оценка, а не обмер музейного экземпляра.

## Состояние

- Именованные коллекции: `{slug}_Model` и подколлекции Barrel/Receiver/Stock/Sights/
  Controls/Magazine/Internals/Fasteners/Markings/Optics/Cylinder.
- UV: `UVMap`, smart project, без UDIM.
- Материалы: 6 текстурных PBR-наборов + процедурные материалы для тёмных полостей,
  светлого металла, гравировок и студии.
- Сквозные полости: ствол с отдельным лайнером и дульной фаской; магазинная шахта
  (ППШ/Мосин), семь камор барабана (Наган), оптическая труба ПУ.
- Контролы (pivot empties): {controls}.
- Анимация: нет. Все proof-рендеры сделаны на кадре 1.
- Доказательства: 7 PNG + 1 GIF + `renders/proofs-index.json`.
- Аудит: `audit/audit-config.json` → `audit/audit-report.json`.
- Manifest: `manifest/asset-manifest.json`, `manifest/build-stats.json`.

## Решения и вопросы

- Выбран вариант: {m['choice']}.
- Разрешение текстур 1K и отсутствие game-ready экспорта — допущения, так как пользователь
  не задал бюджет и целевой движок.
- Если нужен экспорт в движок, LOD/collision или 4K-текстуры, это отдельная итерация.
- Внешние референсные изображения не включены в репозиторий из лицензионных соображений.
""".replace("小型", "мелкие")


def readme_md(slug: str) -> str:
    m = META[slug]
    return f"""# {m['title']} — {m['name']}

Статус: `review` · Архетип: `hard_surface` · Ветка: `{BRANCH}`

![Hero](renders/hero.png)

## Состав

| Путь | Что |
|---|---|
| `TASK.md` | контракт задачи и критерии приёмки |
| `asset-state.md` | текущее состояние, размеры, решения, вопросы |
| `web_refs/sources.md` | источники, URL, вариант, лицензия |
| `source/{slug}.blend` | редактируемый high-poly источник |
| `textures/` | 30 PBR-карт 1K (6 наборов × 5 карт) |
| `renders/` | hero, силуэты, дульный срез, макро, clay, turntable GIF |
| `audit/` | конфигурация и отчёт скриптового аудита |
| `manifest/` | machine-readable manifest и статистика сборки |
| `exports/` | пусто: game-ready экспорт не заказан |

## Как открыть

Blender {stats(slug)['blender_version']}; метры, Z-up. Корневая коллекция `{slug}_Model`.
Студийные камера, света и пол лежат в `{slug}_Studio`; скрытая 100-мм масштабная线性ка —
тоже там. Все текстуры лежат рядом с `.blend` по относительному пути `//../textures/`.
Анимации нет; pivot-контролы перечислены в `asset-state.md`.

## Проверки

См. `manifest/asset-manifest.json` (блок `proofs`) и `audit/audit-report.json`.
Каждое изображение в `renders/` закрывает конкретный критерий из `TASK.md`.

## Ограничения

Визуальная модель, а не производственная документация. Game-ready оптимизация,
LOD, collision, риг и анимация не выполнялись.

## Происхождение материалов

Все PBR-карты процедурные и оригинальные. Внешние статьи/музейные страницы
использовались только как справочники; см. `web_refs/sources.md`.
""".replace("线性ка", "линейка")


def audit_notes_md(slug: str) -> str:
    return f"""# Аудит — {slug}

`audit-config.json` выполняется скриптом `scripts/audit_blend.py` в headless Blender.
Отчёт `audit-report.json` относится ровно к текущему `source/{slug}.blend`.

Проверяются:

- габарит всей модели по collection `{slug}_Model`;
- длина ствольной части;
- конечные трансформации, отсутствие нефинитных вершин, wire-рёбер и свободных вершин;
- пять лучей внутри канала ствола;
- вертикальные лучи через магазинную шахту (ППШ/Мосин);
- семь лучей через каморы барабана (Наган);
- оптическая труба и кольца прицела ПУ (только для версии с оптикой).

Ограничения: лучи — конечная выборка, а не доказательство непрерывной проходимости
или работоспособности механизма. Нулевые грани, которые создают модификаторы Bevel
и конвертированный Text, не являются критерием приёмки и в конфигурации не проверяются.
"""


def make_overview() -> None:
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    title_font = ImageFont.truetype(font_path, 38)
    label_font = ImageFont.truetype(font_path, 23)
    small_font = ImageFont.truetype(font_path, 18)
    width, height = 1600, 1040
    canvas = Image.new("RGB", (width, height), (28, 30, 34))
    draw = ImageDraw.Draw(canvas)
    draw.text((40, 24), "Советское стрелковое оружие WWII — 4 модели", font=title_font, fill=(238, 238, 232))
    draw.text((42, 72), "Blender 4.5.15 LTS · Cycles CPU · 1K PBR · редактируемые .blend · настоящие сквозные каналы",
              font=small_font, fill=(170, 176, 184))

    positions = [(36, 120), (812, 120), (36, 570), (812, 570)]
    card_w, card_h = 752, 412
    for slug, (x, y) in zip(SLUGS, positions):
        hero = Image.open(ASSETS / slug / "renders" / "hero.png").convert("RGB")
        hero.thumbnail((card_w - 12, card_h - 58), Image.Resampling.LANCZOS)
        card = Image.new("RGB", (card_w, card_h), (47, 50, 55))
        card.paste(hero, ((card_w - hero.width) // 2, 6))
        cd = ImageDraw.Draw(card)
        label = f"{META[slug]['title']} · {META[slug]['length']}"
        cd.text((14, card_h - 44), label, font=label_font, fill=(240, 238, 230))
        canvas.paste(card, (x, y))
    draw.text((40, 995), "Все доказательства, manifest и audit — в папках assets/<slug>/", font=small_font,
              fill=(170, 176, 184))
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    out = reports_dir / "overview.png"
    canvas.save(out, optimize=True)
    print(f"overview: {out}")


def report_md() -> str:
    rows = []
    for slug in SLUGS:
        m = META[slug]
        s = stats(slug)
        rows.append(
            f"| {m['title']} | [{m['name']}](assets/{slug}/README.md) | "
            f"[.blend](assets/{slug}/source/{slug}.blend) | "
            f"[hero](assets/{slug}/renders/hero.png) | "
            f"[manifest](assets/{slug}/manifest/asset-manifest.json) | "
            f"[audit](assets/{slug}/audit/audit-report.json) | "
            f"{s['bbox_mm'][0]:.0f} мм | {s['triangle_count']} |"
        )
    return f"""# Отчёт — реалистичные 3D-ассеты советского оружия WWII

![Обзор четырёх моделей](reports/overview.png)

Созданы четыре редактируемые high-poly модели в формате `.blend` (Blender 4.5.15 LTS),
с UV, процедурными PBR-текстурами 1K, именованными коллекциями, pivot-контролами,
Cycles-рендерами и скриптовым аудитом. Ветка: `{BRANCH}`.

## Ассеты

| Модель | Описание | Источник | Hero | Manifest | Audit | Длина X | Треуг. |
|---|---|---|---|---|---|---:|---:|
{chr(10).join(rows)}

## Что входит

- `assets/<slug>/source/<slug>.blend` — активный редактируемый источник.
- `assets/<slug>/textures/` — 30 PBR-карт 1024×1024 (6 наборов × 5 карт).
- `assets/<slug>/renders/` — hero, два боковых силуэта, вид сверху, дульный срез,
  макро канала, clay, turntable GIF и `proofs-index.json`.
- `assets/<slug>/audit/` — конфигурация и отчёт `audit_blend.py` (габариты, трансформации,
  топология, многолучевые проверки полостей).
- `assets/<slug>/manifest/` — `asset-manifest.json` (schema v2) и `build-stats.json`.
- `TASK.md`, `asset-state.md`, `README.md`, `web_refs/sources.md`.

## Ключевые допущения

- ППШ-41: 843 мм, ствол 269 мм, 71-зарядный барабан, поздний деревянный приклад.
- Мосин M91/30: 1232 мм, ствол 730 мм; отдельно рядовая версия и версия с ПУ 3,5×
  (корпус прицела 169 мм, боковой кронштейн).
- Наган M1895: 235 мм, ствол 114 мм, 7-зарядный барабан.
- Метры, Z-up, дуло +X, правая сторона −Y, origin на оси канала у казённого среза.
- 1K-текстуры выбраны как допущение; LOD, collision, риг, анимация и game-ready
  экспорт не заказаны и не выполнялись.

## Проверки

- `python3 scripts/validate_asset.py --root . --strict`
- `python3 scripts/texture_report.py assets --recursive --check`
- `scripts/audit_blend.py` через `scripts/run_blender_tool.py` для каждого `.blend`.
- Все доказательства сгенерированы текущей версией геометрии; отчёты лежат в `reports/`.

## Ограничения и безопасность

Это визуальные активы для рендера/превью. Нет CAD/STEP/STL, чертежей, производственных
допусков, инструкций по сборке или ремонту. Чужие 3D-модели и текстуры не импортировались;
внешние фото использовались только для изучения силуэта и не включены в репозиторий.

## Источники

Подробная таблица URL, вариантов и лицензий — в `assets/*/web_refs/sources.md`.
Основные размеры подтверждены Wikipedia, MuseumOfWeapon, Sniper Central, IWM,
Russian Mosin Nagant, Guns & Ammo, Smithsonian, Modern Firearms и Pritzker Military Museum.
"""


def main() -> None:
    for slug in SLUGS:
        base = ASSETS / slug
        (base / "TASK.md").write_text(task_md(slug), encoding="utf-8")
        (base / "asset-state.md").write_text(state_md(slug), encoding="utf-8")
        (base / "README.md").write_text(readme_md(slug), encoding="utf-8")
        (base / "web_refs" / "sources.md").write_text(SOURCES_MD, encoding="utf-8")
        (base / "audit" / "audit-notes.md").write_text(audit_notes_md(slug), encoding="utf-8")
        print(f"docs: {slug}")
    make_overview()
    (ROOT / "REPORT.md").write_text(report_md(), encoding="utf-8")
    print("report: REPORT.md")


if __name__ == "__main__":
    main()
