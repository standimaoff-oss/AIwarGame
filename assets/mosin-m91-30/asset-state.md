# asset-state — Мосин обр. 1891/30

Статус: `review` · Версия: `v001_procedural` · Ветка: `arena/64d1db80-aiwargame`

## Текущий файл

- Источник: `source/mosin-m91-30.blend` — активный и единственный `.blend` в папке ассета.
- Генератор: `scripts/build_wwii_arms.py` + `scripts/wwii_arms_lib.py`.
- Текстуры: `scripts/generate_wwii_textures.py`.
- Рендеры: `scripts/render_wwii_proofs.py`.
- Blender: 4.5.15 LTS, Cycles CPU.

## Единицы и система координат

Метры, `scale_length = 1.0`, Z-up. Дуло +X, верх +Z, правая сторона −Y.
Начало координат — ось канала ствола у казённого среза. Нормализация по длине:
factor = 0.99716711.

## Размеры

- Evaluated bbox: **1232.0 × 68.3 × 98.8 мм**.
- Габарит X: 1232 мм (источник Wikipedia; Sniper Central; IWM).
- Ствольная часть: 730 мм.
- Y/Z имелкие детали — дизайн-оценка, а не обмер музейного экземпляра.

## Состояние

- Именованные коллекции: `mosin-m91-30_Model` и подколлекции Barrel/Receiver/Stock/Sights/
  Controls/Magazine/Internals/Fasteners/Markings/Optics/Cylinder.
- UV: `UVMap`, smart project, без UDIM.
- Материалы: 6 текстурных PBR-наборов + процедурные материалы для тёмных полостей,
  светлого металла, гравировок и студии.
- Сквозные полости: ствол с отдельным лайнером и дульной фаской; магазинная шахта
  (ППШ/Мосин), семь камор барабана (Наган), оптическая труба ПУ.
- Контролы (pivot empties): `CTRL_mosin-m91-30_Bolt`, `CTRL_mosin-m91-30_BoltHandle`, `CTRL_mosin-m91-30_Trigger`.
- Анимация: нет. Все proof-рендеры сделаны на кадре 1.
- Доказательства: 7 PNG + 1 GIF + `renders/proofs-index.json`.
- Аудит: `audit/audit-config.json` → `audit/audit-report.json`.
- Manifest: `manifest/asset-manifest.json`, `manifest/build-stats.json`.

## Решения и вопросы

- Выбран вариант: рядовая пехотная винтовка с открытыми механическими прицельными приспособлениями.
- Разрешение текстур 1K и отсутствие game-ready экспорта — допущения, так как пользователь
  не задал бюджет и целевой движок.
- Если нужен экспорт в движок, LOD/collision или 4K-текстуры, это отдельная итерация.
- Внешние референсные изображения не включены в репозиторий из лицензионных соображений.
