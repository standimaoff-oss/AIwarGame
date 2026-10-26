# CONVENTIONS — соглашения репозитория ассетов

Документ имеет приоритет над примерами скилла для этого репозитория. Меняй его осознанно и фиксируй изменение в PR.

## Именование

| Объект | Шаблон | Пример |
|---|---|---|
| Папка ассета | `assets/<slug>/` | `assets/village-house/` |
| slug | нижний регистр, дефисы, латиница, без пробелов | `village-house`, `ak-type3`, `mech-scout` |
| Рабочий файл | `source/<slug>.blend` | `source/village-house.blend` |
| Снапшот | `<slug>_v<NNN>_<стадия>.blend` | `village-house_v003_form.blend` |
| Коллекция | `<Slug>_<Часть>` | `House_Walls`, `House_Roof` |
| Объект (движок) | `SM_<Asset>_<Part>` / `SK_<Asset>` | `SM_House_DoorFront` |
| Материал | `M_<Asset>_<Material>` | `M_House_Brick` |
| Текстура | `T_<Asset>_<Set>_<Map>_<res>` | `T_House_Brick_Normal_4k` |
| Рендер | `<тип>_<участок>.png` | `silhouette_front.png`, `macro_brick.png` |

Кириллица и пробелы в путях ассетов запрещены (LFS, CI, движки).

## Единицы и оси

- Blender: метры, `unit_settings.scale_length = 1.0`, Z-up.
- Экспорт: glTF/FBX — Y-up, масштаб 1.0 = 1 м; для движка, работающего в см (Unreal), масштаб задаётся при импорте, а не в файле.
- Все размеры в документах — в миллиметрах (мелкие предметы) или метрах (архитектура, транспорт) с явным указанием.

## Texel density (см/пиксель @1024)

| Класс | Значение |
|---|---|
| Hero-предмет / лицо | 2–4 |
| Персонаж, одежда | 4–8 |
| Мебель, пропсы | 8–16 |
| Архитектура | 16–40 |
| Окружение, терраин | 40–150 |

Отклонение между соседними деталями одного ассета — не более ±30%.

## Карты и цветовые пространства

Суффиксы: `BaseColor`, `Roughness`, `Metallic`, `Normal`(OpenGL по умолчанию; `NormalDX` — DirectX), `Height`, `AO`, `Emissive`, `Opacity`, `Curvature`, `Thickness`, `Sheen`, `Anisotropy`.

sRGB: `BaseColor`, `Emissive`, `Opacity`(художественные маски). Non-Color: всё остальное.

Разрешения: степени двойки 1024/2048/4096/8192; UDIM-тайлы согласованного размера. Все карты одного material set — одного разрешения.

Для движка допускается упаковка `ORM` (Occlusion/Roughness/Metallic в RGB) — факт упаковки указывается в manifest.

## Структура папок

```text
assets/<slug>/
  TASK.md  asset-state.md
  references/  web_refs/(sources.md)
  source/(<slug>.blend, textures_src/)
  versions/  textures/  exports/  renders/  audit/  manifest/
```

## Git и LFS

- Бинари (`.blend`, `.fbx`, `.glb`, `.png`, `.exr`, `.kra`, `.mp4`) — через Git LFS; `.gitattributes` существует до первого коммита.
- Снапшоты `versions/` пушатся только при явной просьбе; иначе папка в `.gitignore`.
- Ветка: `asset/<slug>-<цель>` или `fix/<slug>-<проблема>`; один ассет — одна ветка.
- Коммиты: `asset(<slug>): <что>`, `textures(<slug>): <что>`, `docs(<slug>): <что>`, `chore: <что>`.
- Секреты, токены, `.env`, кэши, `*.blend1` — никогда не коммитятся.
- Мерж и теги — только по решению владельца репозитория.

## Проверки перед PR

1. `python scripts/validate_asset.py --root . --asset assets/<slug> --strict`
2. `python scripts/texture_report.py assets/<slug>/textures --check`
3. `python scripts/gltf_report.py assets/<slug>/exports/*.glb` (если есть экспорт)
4. Blender-аудит и manifest обновлены, рендеры соответствуют текущей версии файла
5. `TASK.md` — статусы критериев приёмки заполнены, невыполненные названы явно
