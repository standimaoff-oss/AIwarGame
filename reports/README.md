# Отчёты проверки

| Файл | Что содержит |
|---|---|
| `overview.png` | контакт-лист четырёх hero-рендеров |
| `validation-report.json` / `validation.txt` | результат `validate_asset.py --root . --strict` |
| `texture-report.json` / `texture-report.txt` | результат `texture_report.py assets --recursive --check` |
| `audit-summary.json` | сводка четырёх отчётов `audit_blend.py` |
| `build-summary.json` | фактические размеры, объекты, треугольники и текстуры |

Команды воспроизведения:

```bash
python3 scripts/validate_asset.py --root . --strict --json reports/validation-report.json
python3 scripts/texture_report.py assets --recursive --check --json reports/texture-report.json
# для каждого ассета:
python scripts/run_blender_tool.py --blend assets/<slug>/source/<slug>.blend \
  --script scripts/audit_blend.py \
  --args --config "$PWD/assets/<slug>/audit/audit-config.json" \
         --output "$PWD/assets/<slug>/audit/audit-report.json"
```

`run_blender_tool.py` и остальные генераторы запускались в headless Blender 4.5.15 LTS
через модуль `bpy`; X/GL-заглушки нужны только в этой песочнице без графического сервера.
