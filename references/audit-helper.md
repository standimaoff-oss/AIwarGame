# Read-only аудит Blender

`scripts/audit_blend.py` запускается встроенным Python Blender. Он пишет JSON, не сохраняет `.blend`, не применяет модификаторы и не двигает сетки. После чтения поз возвращает исходные кадр и камеру в памяти. Внешних Python-пакетов не требует.

## Запуск

Укажи существующий файл, абсолютные пути скрипта, конфигурации и отчёта. Подставь пути текущего проекта, не используй пример буквально.

```powershell
& 'D:\ПРОГРАММЫ\Blender 5\blender.exe' --factory-startup --background 'C:\Project\asset.blend' --python 'C:\Skills\blender-asset-workflow\scripts\audit_blend.py' -- --config 'C:\Project\audit-config.json' --output 'C:\Project\audit-report.json'
```

Без `--config` скрипт делает информационный inventory сцены со статусом INFO. Для оценки требования передай конфигурацию. Пример: [audit-example.json](audit-example.json). Его имена, размеры и кадры демонстрационные: замени их по текущей модели и запросу.

## Что задаёт конфигурация

Корневые поля: `schema_version: 1`, необязательное `description`, массивы `targets`, `poses`, `passages`. В каждой записи нужны `id` и явные `objects` и/или `collections` с точными именами. Коллекция включает вложенные коллекции; одинаковые объекты не суммируются дважды. Неизвестные имена дают FAIL, неизвестные настройки и неверный формат — ERROR.

### targets

- `frame` — необязательный целочисленный кадр измерения; иначе используется текущий.
- `dimensions_mm: {expected: [X,Y,Z], tolerance_mm: число или [X,Y,Z]}` — размеры общего world-space bounding box выбранной evaluated-геометрии.
- `finite_transforms: true` — дополнительный критерий отсутствия NaN/Infinity в трансформах.
- `topology` — критерии отдельно для `base` и `evaluated`: `max_boundary_edges`, `max_nonmanifold_edges`, `max_overfull_edges`, `max_wire_edges`, `max_loose_vertices`, `max_nonfinite_vertices`, `max_zero_area_faces`. Можно задать только нужные ограничения.
- `zero_area_epsilon_mm2` внутри выбранного режима — физический порог площади, по умолчанию `1e-10` мм². Это порог счётчика, а не расстояние для автоматического cleanup.

Base использует исходную mesh-геометрию, evaluated — результат модификаторов и зависимостей на кадре. Замеры учитывают world transforms и `scene.unit_settings.scale_length`. Топология считается для mesh objects; размеры доступны также для геометрии, которую Blender умеет представить evaluated mesh.

Boundary — ребро с одной гранью; overfull — больше двух; wire — без граней. Nonmanifold в этом отчёте включает рёбра с числом граней, отличным от двух. Для намеренного открытого листа положительные boundary/nonmanifold допустимы. Не задавай ему `max_nonmanifold_edges: 0` автоматически.

### poses

Задай `frame`, выбранные объекты, необязательное точное имя `camera` и массив `criteria`. Критерий включает `object` из выбранного scope и нужные поля:

- `visible: true/false` — render flags объекта/коллекций и ненулевой evaluated world scale.
- `finite_transform: true` — здесь единственное число, в отличие от targets.
- `location_mm` и `dimensions_mm`: `{expected: [X,Y,Z], tolerance_mm: ...}`.
- `rotation_deg`: `{expected: [X,Y,Z], tolerance_deg: ...}` — world Euler XYZ, полученный из decomposed matrix. Для больших поворотов, gimbal и углов около ±180° учитывай неоднозначность Euler и отдельно смотри матрицу/визуальную позу.

Visible не означает, что объект виден в кадре: перекрытие, alpha материала, отсечение камерой и исключение отдельного View Layer требуют визуальной проверки. Наличие camera не проверяет framing или её активность; фактическая активность записывается в отчёт.

### passages

Выбери все объекты, которые могут непреднамеренно перекрывать проверяемый проход. `samples` — массив `{start: [X,Y,Z], end: [X,Y,Z]}`; `max_hits: 0` означает отсутствие пересечений на этих лучах. Для ствола, дульного устройства и шахты добавляй осевые и смещённые лучи, а также проверку с противоположного торца; один луч не доказывает сквозную геометрию. `frame` задаёт позу; `unit` — `mm` по умолчанию или `scene`.

Без `reference_object` точки заданы в world coordinates. С этим полем точки сначала переводятся из выбранных единиц, затем умножаются на evaluated matrix_world указанного объекта. Его масштаб влияет на результат. Для локальных условных координат генератора используй `unit: scene`; отчёт всегда показывает получившиеся мировые миллиметры.

Задай лучи до выхода полости, включая края и несколько точек по её сечению. Скрипт не фильтрует render-hidden геометрию и записывает первое пересечение каждого выбранного объекта на луче. Не включённый в scope объект не участвует в проверке. Конечная сетка лучей не доказывает непрерывную свободу объёма, отсутствие всех коллизий или работоспособность механизма.

## Как читать результат

- PASS — прошли только перечисленные критерии. Даже проверка наличия выбранного имени является критерием; PASS не равен качеству всего ассета.
- FAIL — нарушен указанный критерий; смотри имя, actual/expected, кадр и hit position.
- INFO — наблюдения без заданного критерия качества.
- ERROR — неправильная конфигурация или ошибка вычисления; это не положительная проверка модели.

Читай `status`, `checks`, `errors`, `acceptance_check_count`, выбранные scope и кадры. Успешное завершение Blender или exit code 0 не означает PASS: скрипт записывает и отрицательные результаты без аварийного завершения процесса. Визуально осмотри сохранённую модель независимо от отчёта.

## Остальные скрипты скилла

Blender не требуется для `validate_asset.py`, `texture_report.py`, `gltf_report.py`, `init_asset_repo.py` — они работают на Python 3.9+ без внешних пакетов и годятся для CI. Blender нужен для `audit_blend.py`, `make_manifest.py`, `render_proofs.py`, `export_asset.py`.

| Скрипт | Назначение | Пример |
|---|---|---|
| `audit_blend.py` | read-only аудит геометрии, размеров, поз, проходов | см. раздел «Запуск» выше |
| `make_manifest.py` | генерация `asset-manifest.json` из `.blend` (read-only) | `blender --background a.blend --python scripts/make_manifest.py -- --output manifest/asset-manifest.json --slug village-house --archetype architecture` |
| `render_proofs.py` | стандартный набор доказательств (clay, силуэты, макро, turntable) без сохранения файла | `blender --background a.blend --python scripts/render_proofs.py -- --output renders --collections House --turntable 24 --clay --wireframe` |
| `export_asset.py` | экспорт выбранных коллекций в glb/gltf/fbx/obj/usd/stl с логом | `blender --background a.blend --python scripts/export_asset.py -- --collections House --format glb --output exports/house.glb` |
| `init_asset_repo.py` | создание структуры папки ассета, LFS, CI, шаблонов | `python scripts/init_asset_repo.py --root . --asset village-house --kind architecture` |
| `validate_asset.py` | структура, manifest, имена, размеры, LFS, секреты; `--strict` для CI | `python scripts/validate_asset.py --root . --asset assets/village-house --strict` |
| `texture_report.py` | разрешения, POT, полнота наборов карт, цветовое пространство | `python scripts/texture_report.py assets/village-house/textures --check --json texture-report.json` |
| `gltf_report.py` | валидность glTF/GLB, материалы, тангенты, единицы, расширения | `python scripts/gltf_report.py assets/village-house/exports/house.glb` |

Все скрипты возвращают ненулевой exit code при ошибках и пишут JSON-отчёт, если запрошен. Отчёт скрипта дополняет визуальный осмотр: ни один из них не подтверждает сходство с референсом, художественное качество или корректность выбранного варианта предмета.

Примеры конфигураций аудита под архетипы: [audit-example.json](audit-example.json) (базовый), [templates/audit-example-architecture.json](templates/audit-example-architecture.json), [templates/audit-example-character.json](templates/audit-example-character.json).
