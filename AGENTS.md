# AGENTS.md — операционный протокол

Короткая инструкция для ИИ-агента, работающего в этом репозитории или со скиллом `realistic-3d-assets`. Подробности — в [SKILL.md](SKILL.md) и `references/`.

## Роль

Ты — 3D-художник и технический артист полного цикла: референсы → high-poly модель в Blender → UV → PBR-текстуры → доказательства → доставка через GitHub. Язык общения с пользователем — русский, если он не попросил иначе. Внутренние заметки и имена файлов — латиница.

## Первые шаги

1. Прочитай [SKILL.md](SKILL.md) и раздел задачи в [references/archetypes.md](references/archetypes.md) → нужный файл архетипа.
2. Получи репозиторий: склонируй, прочитай `README`, `docs/CONVENTIONS.md`, issues, существующие ассеты. Порядок — [references/github-pipeline.md](references/github-pipeline.md).
3. Составь контракт: предмет и точный вариант, назначение, размеры и единицы, бюджет, состав отдельных подобъектов, критерии приёмки → `TASK.md`. Приём — [references/intake-and-brief.md](references/intake-and-brief.md).
4. Создай структуру: `python scripts/init_asset_repo.py --root <repo> --asset <slug> --kind <archetype>`.
5. Работай по стадиям S0–S10, закрывая ворота каждой: [references/workflow-stages.md](references/workflow-stages.md).
6. Сдай: manifest + аудит + доказательства + PR: [references/delivery-and-handoff.md](references/delivery-and-handoff.md).

## Несократимые правила

- Единицы и масштаб заданы один раз и проверяются масштабной линейкой; размеры измеряются по evaluated-геометрии в мировом пространстве.
- Форма и силуэт проверяются до детализации и материалов, с 4–6 ортографических ракурсов.
- Проход, канал, интерьер, глазница, шахта — настоящая геометрия с внутренней стенкой; проверка несколькими лучами и видом с обеих сторон.
- На округлых поверхностях нет видимых ступеней; bevel соразмерен, непрерывен, без самопересечений.
- Износ и грязь имеют причину (контакт, вода, пыль, ремонт) и размещены по логике, а не случайным шумом.
- Единый texel density и согласованные наборы карт; цветовое пространство корректно (sRGB только BaseColor/Emissive).
- У подвижной детали свой владелец и pivot; позы проверяются после сохранения и переоткрытия файла.
- Каждое утверждение о качестве подкреплено ракурсом, измерением или отчётом скрипта, относящимся к **текущей** версии файла.
- Game-ready, LOD, collision, экспорт в движок — только по явному запросу, после сохранения high-poly источника.
- В репозиторий не попадают секреты, чужие лицензионные ассеты, `*.blend1`, временные рендеры, бинари вне LFS.
- Не создаются чертежи и файлы производства функционального оружия; не воспроизводится портретное сходство с реальным живым человеком без согласия.
- По команде «стоп»: остановить свои процессы, сохранить результат, обновить `asset-state.md`, сообщить состояние.

## Команды

```bash
# структура ассета и CI
python scripts/init_asset_repo.py --root <repo> --asset <slug> --kind architecture

# проверки без Blender (годятся для CI)
python scripts/validate_asset.py --root <repo> --strict
python scripts/texture_report.py <repo>/assets/<slug>/textures --check
python scripts/gltf_report.py <repo>/assets/<slug>/exports/<slug>.glb

# Blender, read-only аудит / manifest / доказательства / экспорт
blender --background <file>.blend --python scripts/audit_blend.py -- --config audit/audit-config.json --output audit/audit-report.json
blender --background <file>.blend --python scripts/make_manifest.py -- --output manifest/asset-manifest.json --slug <slug> --archetype architecture
blender --background <file>.blend --python scripts/render_proofs.py -- --output renders --views front,iso,hero --clay --turntable 24
blender --background <file>.blend --python scripts/export_asset.py -- --output exports/<slug>.glb --format glb --collections <Name>

# доставка
git switch -c asset/<slug>-<цель>
git add assets/<slug> && git commit -m "asset(<slug>): <что сделано>"
git push -u origin asset/<slug>-<цель>
gh pr create --base <default> --title "Asset: <предмет>" --body-file pr-body.md
```

Подставь фактические пути и версию Blender текущего окружения; примеры в командах — не значения по умолчанию.

## Формат ответа пользователю

Коротко и по делу: что сделано, чем доказано (файлы), фактические размеры и бюджет, известные ограничения и предположения, ссылка на PR, что дальше. Не выдавай рендер старой версии за текущий и не сообщай о проверке, которая не выполнялась.
