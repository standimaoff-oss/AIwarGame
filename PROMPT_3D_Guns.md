# Task: Realistic 3D models of six firearms in Blender

## 1. Goal

Create six separate high-poly art 3D models of firearms in Blender. Each model must match the real firearm as closely as possible: proportions, dimensions, silhouette from every angle, individual parts and their seams, bevels, fasteners, markings, materials and wear. The models are for a YouTube project, "Realistic gun models created by Claude Opus 5.5 in Blender", so you build all geometry yourself with Python/bpy in the live Blender sessions.

The main criterion is **flawless quality and fidelity to the real firearm**. Time and amount of work are secondary. You have full freedom over methods, work order, tools and sources. Resolve open questions yourself, record each decision with its reasoning, and do not stop to ask for clarification. Contact the user only for a real blocker, such as Blender being unreachable.

These are visual art models. Do not produce drawings, CAD, or files for manufacturing or 3D printing functional parts.

**Communicate with the user in Russian.** Write `REPORT.md` and messages to the user in Russian; internal notes may be in any language.

## 2. Environment

- OS: Windows 11. Blender **5.2.2 LTS**: `W:\Blender\blender.exe`. The `D:\ПРОГРАММЫ\Blender 5\...` path in the skill belongs to a different computer and does not exist here.
- GPU: NVIDIA GeForce RTX 5070. Use OptiX and the denoiser for Cycles.
- Project root: `W:\YouTube\3D Model Guns\`.
- All six files are already open in six separate Blender windows. In each window the MCP add-on listens on its own port, and Mirasim connects to each port through a separate server.

### Server, port and file mapping (strict)

| Model | Mirasim server (MCP) | Port | File |
|---|---|---|---|
| AK-47 | `custom-blender-ak47` | 9883 | `W:\YouTube\3D Model Guns\AK 47\AK47.blend` |
| AR-15 | `custom-blender-ar15` | 9884 | `W:\YouTube\3D Model Guns\AR-15\AR15.blend` |
| Desert Eagle | `custom-blender-deserteagle` | 9885 | `W:\YouTube\3D Model Guns\Desert Eagle\DesertEagle.blend` |
| M4A4 | `custom-blender-m4a4` | 9886 | `W:\YouTube\3D Model Guns\M4A4\M4A4.blend` |
| Remington 870 | `custom-blender-remington870` | 9887 | `W:\YouTube\3D Model Guns\Remington 870\Remington870.blend` |
| M1911 | `custom-blender-1911` | 9888 | `W:\YouTube\3D Model Guns\М1911\M1911.blend` |

Server tools are named `mcp__<server>__<tool>`, e.g. `mcp__custom-blender-ak47__execute_blender_code`, `..._get_scene_info`, `..._look`.

**Warning:** in the folder name `М1911` the first letter is the **Cyrillic** "М", while in the file name `M1911.blend` it is the Latin "M". Copy these paths instead of typing them.

### Connection rules

1. **Verify all six mappings before starting.** Call `get_scene_info` with `fields: ["settings"]` on each server, or print `bpy.data.filepath` via `execute_blender_code`, and compare the path with the table. If a path does not match, do not modify that file and tell the user.
2. Modify each model **only through its own server**. Before every save, confirm that `bpy.data.filepath` points to the expected file.
3. **Never open other files in these windows** via `File → Open` or `bpy.ops.wm.open_mainfile`: that breaks the port-to-file mapping and may stop the MCP server. Save the main file with `bpy.ops.wm.save_mainfile()`. Save version snapshots with `bpy.ops.wm.save_as_mainfile(filepath=..., copy=True)` so the window keeps working on the main file.
4. Port **9876** has a different project of the user open, `3DDodgeChallenger_v001.blend`. **Do not touch it**, and do not close any other Blender processes. If other Blender servers appear in the session, do not use them.
5. The MCP add-on in these windows is probably outdated (protocol 7, expected 13). If a tool fails, fall back to `execute_blender_code`. Do not reinstall the add-on or restart Blender without the user's consent. If the work is impossible without an update, tell the user.
6. Split long scripts into steps to avoid MCP timeouts. After each step, `print()` the result.
7. **Do not use `generate_3d`, `search_assets` or `import_asset` for the firearms or their parts**, and do not import any third-party firearm models. You build the firearm geometry yourself. For studio lighting and materials you may use CC0 HDRIs or textures, e.g. downloaded manually from Poly Haven.

### Per-model folder layout

```text
<Model folder>\
    <Model>.blend    ← working file, open in Blender on its port
    1.jpg … 5.webp   ← the user's references (do not modify or delete)
    web_refs\        ← references you download + sources.md (URL, what it shows, variant)
    versions\        ← snapshots: <Model>_v001_blockout.blend, _v002_..., ...
    renders\         ← previews, reference comparisons, final renders
    audit\           ← audit-config.json, audit-report.json
    asset-state.md   ← asset state (see the skill)
```

Final report for all models: `W:\YouTube\3D Model Guns\REPORT.md`.

## 3. Skill

Use the **`blender-asset-workflow`** skill: `C:\Users\Cryptopiy\.mirasim\skills\blender-asset-workflow\`. The skill is written in Russian. If it is not loaded automatically, read `SKILL.md` and the relevant files in `references\`:

- `geometry.md`: shape, scale, seams, Booleans, bevels, normals;
- `construction-standards.md`: through-bores, magazine wells, internal cavities, quality of curved surfaces;
- `archetypes.md`: the "Пистолет" (pistol), "Дробовик" (shotgun) and "Автомат, винтовка, пулемёт" (rifle) sections;
- `materials-delivery.md`: materials, wear, renders, delivery;
- `audit-helper.md` and `scripts\audit_blend.py`: scripted checks of dimensions, topology and bores;
- `animation.md`: only for pivot setup of moving parts; no animation is required;
- `lessons-pm.md`: examples of typical mistakes;
- `local-environment.md` describes a **different** computer: use the environment from section 2.

The skill asks the user in two places. Here are the answers:

- **Attachments.** Model only what belongs to the chosen variant: factory sights, sling swivels, etc. Do not add optics, lights, lasers, suppressors or bipods. On every model the **magazine** is its own collection with its own origin. On the Remington 870 it is a tubular under-barrel magazine, so it stays part of the shotgun.
- **Missing information.** Research it online and decide yourself. Record each decision in `asset-state.md`, marked either "confirmed by source" or "assumption".

## 4. References and variant selection

Each model folder contains 5 references from the user. I reviewed them: several folders mix **different variants**, renders of other people's 3D models, game images and one AI-generated infographic. The skill forbids mixing parts of different variants. So first pick **one exact variant** and record it in `asset-state.md`. My recommendations follow; you may choose differently if you justify it.

General rules for sources:

- Take dimensions and shapes primarily from **photos of real firearms** and primary sources: field manuals, technical documentation, manufacturer manuals, high-resolution museum and auction photos, field-stripping photos. Third-party 3D renders and game models show only the general configuration: they contain errors and stylization.
- **Search online for many more references**: orthographic left and right, top, bottom, front and rear views, close-ups of assemblies, disassembly, markings. Save them in `web_refs\` and record each source in `sources.md`.
- Confirm every key dimension with at least two independent sources, and write a dimension table in `asset-state.md` before modeling.

### AK-47 (`AK 47\`)

- `1.png`: photo of a real AK-47 with a **milled** receiver (looks like a Type 2: metal adapter between receiver and stock).
- `2.webp`: milled AK-47, looks like a Type 3 (lightening cut directly above the magazine well). Small image.
- `3.jpg`: someone else's 3D exploded render. The receiver is **stamped** and the magazine is Bakelite, which is closer to the **AKM**.
- `4.jpg`: **AI-generated** infographic resembling an AKM (muzzle compensator). Details are unreliable; use it only for general understanding.
- `5.jpg`: photo of an **AKM**: stamped receiver, slant muzzle compensator, laminated furniture.
- **Recommendation:** the actual **AK-47 (milled receiver), Type 3**, or Type 2 per `1.png`. Determine the sub-type from sources and do not mix it with the AKM. Features you must not take from the AKM: stamped receiver with the dimple above the magazine; ribbed dust cover; slant compensator (the AK-47 has a thread-protector nut at the muzzle); palm swells on the AKM lower handguard; rear sight graduated to 1000 m on the AKM (800 m on the AK-47). Stock attachment differs between Type 2 and Type 3.
- Reference figures to verify, not to trust blindly: overall length about 870 mm, barrel about 415 mm.

### AR-15 (`AR-15\`)

- `1.jpg` and `3.webp`: photos of the same modern civilian **LMT Defense** rifle: free-float M-LOK handguard, folding front and rear sights, Magpul MOE SL-type stock, PMAG-type polymer magazine. This is the best reference.
- `2.jpg`: wireframe of someone else's Blender model. Use it only as an example of topology density, not as a source of dimensions.
- `4.jpg`: Sionics rifle in a similar configuration, seen from both sides; useful for the left side.
- `5.jpg`: generic AR-15 with an M4 stock and an Alamy watermark.
- **Recommendation:** a modern civilian AR-15 carbine in the configuration of `1.jpg`/`3.webp`. Identify the exact LMT model by searching, e.g. by its handguard, markings and controls. Reference figure: 16″ barrel (406 mm).
- **The AR-15 and M4A4 must look clearly different.** They are different configurations: see below.

### M4A4 (`M4A4\`)

- **No real firearm is called "M4A4".** The name comes from Counter-Strike. All five references are the CS game model or copies of it: `1.webp` and `4.jpg` are game renders; `3.jpeg` and `5.png` are fan 3D models; `2.jpg` is a vector template with an overall length of 840 mm.
- The task is to model **a real firearm in the configuration of the in-game M4A4**, not to copy game art. From the images, the prototype is an **M4/M4A1 carbine** with a 14.5″ barrel: **KAC RAS/RIS (quad rail)** handguard with ribbed rail covers, front sight on an **A2 FSB**, folding aperture rear sight on the upper rail, **SOPMOD (Crane)** collapsible stock, **A2** flash hider, 30-round aluminum STANAG (USGI) magazine.
- Verify this hypothesis by searching, e.g. "CS:GO M4A4 real life". Find photos of real M4A1s in this configuration and model from them. Markings and selector as on a real M4A1 (SAFE / SEMI / AUTO). If you find a more accurate real prototype, use it and justify the choice.
- Reference figures: barrel 368 mm (14.5″), overall length about 840 mm with the stock extended.
- **Reuse:** the lower and upper receivers, bolt carrier group, buffer tube and fire control group are nearly identical on the AR-15 and M4. Model the shared parts carefully once and bring them into the second file via **Append** (copy, not Link) so the files stay independent. Then rework the differences: selector and markings, auto sear on the M4A1, handguard, front sight, stock, magazine.

### Desert Eagle (`Desert Eagle\`)

- `5.webp`: photo of a **Mark XIX .50 AE, 6″ barrel**, standard unported barrel, Burnt Bronze finish.
- `2.jpeg`, `3.jpg`: someone else's renders of a chrome Mark XIX .50 AE. Useful for the general configuration; the "Minneapolis MN" marking belongs to an older period.
- `1.jpg`: Mark XIX with an **integral muzzle brake** (ports). This is a **different barrel variant**.
- `4.webp`: **L5 .357 Magnum**, a different model with a shorter barrel. Do not use it.
- **Recommendation:** **Mark XIX .50 AE with a 6″ standard barrel.** Pick a single finish (e.g. polished or brushed chrome, or stainless) and match the markings to the period and manufacturer of the chosen example. Reference figures: overall length about 273 mm, barrel 152 mm. Do not forget the gas system, the rotating bolt visible through the ejection port, and the rail on the barrel.

### Remington 870 (`Remington 870\`)

- `2.webp`: photo of an **870 Police/Express** with a barrel of about 18–18.5″: **wooden** stock and forend, magazine extension with barrel clamp. This is the best reference.
- `3.jpg`: someone else's render of the same configuration.
- `1.webp`: 870 Express Tactical with a synthetic pistol-grip stock. Different furniture.
- `4.jpg`: third-party/game render with a fictional "HUNTER 870" marking and a long barrel without an extension.
- `5.jpg`: photo of a pump shotgun **that may not be a Remington 870**: the gold trigger and receiver shape look more like a Winchester 1300. Verify before using it.
- **Recommendation:** **Remington 870 Police Magnum / Express** with a barrel of about 18–18.5″, wooden furniture and a magazine extension with clamp, as in `2.webp`. Confirm the exact model by searching. Reference figure: 18.5″ barrel (470 mm).

### M1911 (`М1911\`)

- `1.jpg`: photo of a WWII **M1911A1** made by Remington Rand: Parkerized finish, brown checkered plastic grips.
- `4.jpg`: replica of an M1911A1, right side.
- `5.webp`: photo of an **original M1911** (Colt, pre-A1): wooden double-diamond grips, long trigger, flat mainspring housing, no frame relief cuts behind the trigger. This is a **different variant**.
- `2.jpg`, `3.jpg`: low-quality third-party renders with a fictional "MISHAI" marking. Do not use them as a source.
- **Recommendation:** **M1911A1 (US Army, WWII)**, because most references show it. Do not carry M1911 features over to the A1: the A1 has a short trigger, an arched serrated mainspring housing, frame relief cuts behind the trigger, a longer grip-safety tang, a shorter hammer spur and a wider front sight. Reference figures: overall length 216 mm, barrel 127 mm (5″).

## 5. Model quality requirements

### Scale and coordinate system (identical for all six)

- Units are meters, `scene.unit_settings.scale_length = 1.0`, and every object has scale (1, 1, 1) after applying transforms.
- **Muzzle points to +X, up is +Z, the right side of the firearm (ejection port) faces −Y.** The Front view (numpad 1) then shows the right side.
- The world origin is on the bore axis at the breech face.
- Measure dimensions on **evaluated** geometry in world space, as the skill requires. Target: key dimensions within ~1% of the confirmed sources.

### Matching the references

- For each model, set up orthographic references: Image Empties in side, top and front views, or background images on orthographic cameras. Scale them by a known dimension, such as overall length or barrel length, and align them to the bore axis.
- Build a **blockout** of the main volumes first, with a plain material. Compare the silhouette with the references as an overlay: an orthographic render on top of the photo at about 50% opacity. Save these comparisons to `renders\compare_*.png`. Do not move on to details until the silhouette and proportions match.

### Geometry

- **Every real part is a separate object** with a clear name, e.g. `AK47_Receiver`, `AK47_BoltCarrier`, `AK47_DustCover`, `AK47_Trigger`, `M1911_Slide`, `M1911_GripPanel_L`. Objects are grouped into collections: `<Model>_Body`, `<Model>_Magazine`, `<Model>_Internals`, `<Model>_Furniture`, `<Model>_Sights`, `Studio`.
- Primary, secondary and tertiary detail: pins, slotted screws, visible springs, checkering and serrations, cuts and milling, sling swivels, front and rear sights with their real profiles, fine manufacturing chamfers.
- High-poly with no faceting: Subdivision Surface with support loops, or Bevel plus Weighted Normal / Harden Normals. Check with a **moving highlight** that curved surfaces have no stepping and flat surfaces have no shading artifacts. Do not blindly apply `shade_smooth`, Remesh or larger bevels to the whole model.
- **Through-bores:** every barrel has a real inner wall and an open muzzle. On the shotgun, the barrel and the magazine tube wherever visible. Check with multi-ray tests from both ends, as the skill requires.
- **Visible mechanism:** through the ejection port and magazine well you see the bolt or bolt carrier, chamber, extractor, magazine feed lips and follower. No empty shells or blanking plates. The magazine is loaded, with the top round visible between the feed lips.
- **Pivots and hierarchy** of moving parts are set up so they can be animated later: trigger, hammer, bolt or slide, charging handle, safeties and selector, magazine release, the Remington 870 forend, the AR dust cover, the collapsible stock. Do not create the animation itself.
- No unintended self-intersections, flipped normals, broken unapplied Booleans or duplicate vertices. Check the final mesh with `audit_blend.py` and visually.

### Materials and markings

- Physically correct PBR materials of the right type for every surface: blued or Parkerized steel, anodized aluminum (AR), chrome or stainless (Desert Eagle), finely textured polymer, wood with plausible grain and finish (AK-47, 870), rubber, cartridge brass.
- Non-uniform roughness: procedural masks, light wear on raised edges (Pointiness / AO / Geometry Nodes or baked masks), micro-scratches, handling marks near controls. Keep wear moderate and realistic, not piled-on grime.
- **Markings:** manufacturer and caliber engravings, selector markings and proof marks in the right places, with the characteristic typeface and correct depth. Make them as geometry (text → mesh → recessed) or as normal/displacement decals. Serial numbers are fictional.
- Set colors on shader node inputs. Look nodes up by type, not by name: the UI may be localized.

### Renders and checks

- A studio scene in the `Studio` collection: neutral cyclorama backdrop, three-point lighting or a studio HDRI, cameras. Render with Cycles, OptiX and the denoiser, AgX view transform. **Render one model at a time**: the six Blender windows share one GPU.
- Minimum set of renders in `renders\` for each model:
  1. 3/4 hero view, 3840×2160;
  2. orthographic left and right, top, front and rear views;
  3. close-ups: muzzle (the through-bore wall is visible), ejection port with the mechanism, magazine well from below, sights, markings;
  4. a clay render without materials to check shape and highlights;
  5. comparisons with the references from matching angles (`compare_*.png`);
  6. a partially exploded view with parts slightly separated (optional but recommended: it shows the internal mechanism well).
- For frequent intermediate checks, use the `look` tool with a small `max_size` (512–768) to keep context small.

### Self-review loop (mandatory for every model)

1. Save the file and a version snapshot, then render views that match the references.
2. Compare critically, part by part, and list **at least 10 specific discrepancies** with the references and sources: proportions, profiles, part positions, radii, missing features, materials.
3. Fix them and repeat the loop until no significant discrepancies remain.
4. Before signing off a model, run an **independent reviewer subagent**. Give it only the final renders, the references and the description of the chosen variant, without your own conclusions. It looks for differences from the real firearm. Fix what it finds with good reason.
5. Run `audit_blend.py` with a background Blender on the saved file (the file is not modified):

```powershell
& 'W:\Blender\blender.exe' --factory-startup --background '<path to .blend>' --python 'C:\Users\Cryptopiy\.mirasim\skills\blender-asset-workflow\scripts\audit_blend.py' -- --config '<folder>\audit\audit-config.json' --output '<folder>\audit\audit-report.json'
```

## 6. Work order (recommended)

1. Verify all six connections (section 2). Record the **start time** (`Get-Date`).
2. Study the skill and create the folder structure.
3. Do the models in order of increasing complexity: **M1911 → Desert Eagle → Remington 870 → AK-47 → AR-15 → M4A4**. The AR-15 and M4A4 go back to back so shared parts can be reused. You may change the order.
4. For each model: variant selection and source research → dimension table → references in the scene → blockout → major parts → small details → materials and markings → studio and renders → self-review loop → audit → final save.
5. Save often (`save_mainfile`) and snapshot to `versions\` before every major rework. If an operation keeps breaking the mesh, go back to the last clean snapshot.
6. Splitting the work across subagents (one per model and port) is allowed at your discretion. Each subagent works **only with its own server and its own folder** and receives the full requirements of this prompt. Still render one model at a time. Quality beats speed.
7. When a model is done, send the user the hero render and a reference comparison, if the session has a file-delivery tool. Then move on to the next model immediately without waiting for a reply. If the user sends corrections, apply them.

## 7. Delivery

For each model:

- the main `.blend` is saved (path from the table), with snapshots in `versions\`;
- renders in `renders\`, the audit report in `audit\`, sources in `web_refs\sources.md`;
- `asset-state.md` with: the chosen variant and why; a key-dimension table (source, value, measured in the model, deviation); confirmed facts and assumptions; what was checked; remaining uncertainties.

Overall report `W:\YouTube\3D Model Guns\REPORT.md`:

- a table for the six models: variant, overall length and barrel length (source / model), number of objects and polygons (evaluated), path to the hero render;
- what turned out well, which limitations and assumptions remain, what could be improved in the next iteration.

## 8. Cost accounting (after all work is finished)

Calculate the following and add it to the end of `REPORT.md` and to your final message to the user:

1. **Time.** Start and end (local time), total elapsed time and time per model. Cross-check against the timestamps in the session logs.
2. **Tokens.** Take exact figures from the Claude session logs:
   - folder: `C:\Users\Cryptopiy\.claude\projects\W--YouTube-3D-Model-Guns\`;
   - include the `*.jsonl` files of the sessions for this work and subagent logs in `<session id>\subagents\` subfolders, if any;
   - **exclude** `73dba2e5-d499-409e-af0b-6bd0a5681298.jsonl`: that is the session where this prompt was written;
   - every assistant record has `message.usage`: `input_tokens`, `cache_creation_input_tokens` (with the `cache_creation.ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens` breakdown, if present), `cache_read_input_tokens`, `output_tokens`, plus `message.model`;
   - one message is written to the log as several lines with the same `usage`, so **deduplicate by `message.id`**;
   - the files are large and contain images. Stream them with a script, e.g. Python with `-X utf8`, line by line with `json.loads`, rather than loading them whole;
   - report totals per category, per model (if they can be split by time) and overall, plus the number of API requests and web searches.
3. **Cost in USD at API rates.** Look up the **current official Anthropic prices** for the model in `message.model`: the pricing page in the Claude documentation (docs.claude.com, Pricing section) or anthropic.com/pricing. Do not use prices from memory. Price separately: uncached input, cache writes (5 min and 1 h at their own rates), cache reads, output, and web search if it is billed separately. Check whether **long-context premium rates** apply to requests with large inputs, and apply them to those requests if so. Give the total in USD, the pricing page URL and the date you checked it.
4. Briefly describe the counting method and its margin of error, e.g. anything missing from the logs.

---

Begin. The main thing: models indistinguishable from the real firearms from any angle.
