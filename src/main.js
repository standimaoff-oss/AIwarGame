import * as THREE from 'three';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { createBattlefield } from './engine.js';
import { EffectsSystem } from './effects.js';
import './styles.css';

const $ = (selector) => document.querySelector(selector);
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const canvas = $('#battlefield');
const minimap = $('#minimap');
const minimapContext = minimap.getContext('2d');
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const scratchVector = new THREE.Vector3();

let world;
let effects;
let selectedUnit = null;
let logCounter = 0;
let toastTimeout = null;
let lastMinimapDraw = 0;
let lastStatsUpdate = 0;
let pointerDown = null;
let frameCount = 0;
let fps = 0;
let runningTime = 0;
let autoFireEnabled = true;

const elements = {
  renderStatus: $('#render-status'),
  eventLog: $('#event-log'),
  unitList: $('#unit-list'),
  selectionName: $('#selection-name'),
  incidentTitle: $('#incident-title'),
  fireState: $('#fire-state'),
  damageReadout: $('#damage-readout'),
  damageBar: $('#damage-bar'),
  incidentObject: $('#incident-object'),
  impactSlider: $('#impact-strength'),
  impactValue: $('#impact-value'),
  windSlider: $('#wind-strength'),
  windValue: $('#wind-value'),
  windReadout: $('#wind-readout'),
  smokeToggle: $('#smoke-toggle'),
  fireToggle: $('#fire-toggle'),
  pauseButton: $('#pause-button'),
  pauseLabel: $('#pause-label'),
  selectedCardEmpty: $('#empty-unit'),
  selectedUnitInfo: $('#selected-unit-info'),
  selectedUnitName: $('#selected-unit-name'),
  selectedUnitSide: $('#selected-unit-side'),
  selectedUnitHealth: $('#selected-unit-health'),
  selectedUnitSpeed: $('#selected-unit-speed'),
  selectedAvatar: $('#selected-avatar'),
  engineBar: $('#engine-bar'),
  engineValue: $('#engine-value'),
  mobilityBar: $('#mobility-bar'),
  mobilityValue: $('#mobility-value'),
  weaponBar: $('#weapon-bar'),
  weaponValue: $('#weapon-value'),
  ammoReadout: $('#ammo-readout'),
  fuelReadout: $('#fuel-readout'),
  toastRegion: $('#toast-region'),
  mapToast: $('#map-toast'),
  coordReadout: $('#coord-readout'),
  sceneHint: $('#scene-hint'),
};

function showToast(message) {
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = message;
  elements.toastRegion.append(toast);
  window.setTimeout(() => toast.remove(), 3900);
}

function showMapToast(message) {
  elements.mapToast.textContent = message;
  elements.mapToast.classList.add('is-visible');
  window.clearTimeout(toastTimeout);
  toastTimeout = window.setTimeout(() => elements.mapToast.classList.remove('is-visible'), 1450);
}

function addLog(message, type = '') {
  const elapsed = logCounter++;
  const minute = 40 + elapsed;
  const time = `06:${String(minute % 60).padStart(2, '0')}`;
  const item = document.createElement('div');
  item.className = `log-entry ${type ? `is-${type}` : ''}`;
  const timeElement = document.createElement('time');
  timeElement.textContent = time;
  const marker = document.createElement('i');
  const text = document.createElement('span');
  text.textContent = message;
  item.append(timeElement, marker, text);
  elements.eventLog.prepend(item);
  while (elements.eventLog.children.length > 5) elements.eventLog.lastElementChild.remove();
}

function getBuildingData(root = world?.targetBuilding) {
  return root?.userData?.building || null;
}

function updateIncidentCard() {
  if (!world) return;
  const root = world.targetBuilding;
  const data = getBuildingData(root);
  if (!data) return;
  const damage = Math.round(data.damage);
  elements.incidentTitle.textContent = data.isBurning ? 'Возгорание на объекте' : 'Контроль состояния объекта';
  elements.fireState.textContent = data.isBurning
    ? (effects.fireEnabled ? 'ПОЖАР АКТИВЕН' : 'ОГОНЬ СКРЫТ')
    : 'ВОЗГОРАНИЯ НЕТ';
  elements.damageReadout.textContent = damage >= 96 ? 'ОБЪЕКТ РАЗРУШЕН' : `УРОН ${damage}%`;
  elements.damageBar.style.width = `${Math.max(2, damage)}%`;
  elements.incidentObject.textContent = data.name;
  const state = elements.fireState.parentElement;
  state.style.color = data.isBurning ? (effects.fireEnabled ? '#f1a45f' : '#b98c63') : '#9dab95';
}

function unitTypeLabel(unit) {
  if (unit.type === 'tank') return 'ОСНОВНОЙ ТАНК';
  if (unit.type === 'ifv') return 'БОЕВАЯ МАШИНА';
  if (unit.type === 'truck') return 'ОБЕСПЕЧЕНИЕ';
  return 'МОТОСТРЕЛКОВАЯ ГРУППА';
}

function getUnitStatus(unit) {
  if (unit.destroyed || unit.components.hull <= 0) return 'ВЫВЕДЕН';
  if (unit.components.engine <= 0 || unit.components.mobility <= 0 || unit.fuel <= 0) return 'НЕПОДВИЖЕН';
  const damaged = Object.values(unit.components).some((value) => value < 100)
    || (unit.ammo.maximum > 0 && unit.ammo.current < unit.ammo.maximum);
  return damaged ? 'ПОВРЕЖДЁН' : 'ГОТОВ';
}

function updateSelectedUnitCard() {
  if (!selectedUnit) return;
  const unit = selectedUnit;
  const engine = Math.round(unit.components.engine);
  const mobility = Math.round(unit.components.mobility);
  const weapon = Math.round(unit.components.weapon);
  const hull = Math.round(unit.components.hull);
  const speedFactor = (0.25 + 0.75 * unit.components.engine / 100)
    * (0.25 + 0.75 * unit.components.mobility / 100)
    * (0.3 + 0.7 * unit.components.fuelSystem / 100);
  elements.selectedUnitHealth.textContent = `${hull}%`;
  elements.selectedUnitSpeed.textContent = `${Math.round(unit.speedKmh * speedFactor)} км/ч`;
  elements.engineValue.textContent = `${engine}%`;
  elements.mobilityValue.textContent = `${mobility}%`;
  elements.weaponValue.textContent = `${weapon}%`;
  [[elements.engineBar, engine], [elements.mobilityBar, mobility], [elements.weaponBar, weapon]].forEach(([bar, value]) => {
    bar.style.width = `${value}%`;
    bar.classList.toggle('is-low', value < 35);
  });
  elements.ammoReadout.textContent = unit.ammo.maximum > 0 ? `${unit.ammo.current} / ${unit.ammo.maximum}` : 'НЕТ';
  elements.fuelReadout.textContent = `${Math.round(unit.fuel)}%`;
  $('.unit-status').innerHTML = `<i></i> ${getUnitStatus(unit)}`;
  $('#ammo-fire-button').disabled = unit.ammo.maximum <= 0 || unit.ammo.current <= 0 || unit.components.weapon <= 0 || unit.destroyed;
  $('#vehicle-component option[value="ammo"]').disabled = unit.ammo.maximum <= 0;
  $('#vehicle-damage-button').disabled = unit.destroyed;
}

function buildUnitList() {
  elements.unitList.replaceChildren();
  world.units.forEach((unit) => {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'unit-row';
    row.dataset.unitId = unit.id;
    row.dataset.side = unit.side;
    row.dataset.type = unit.type;
    row.setAttribute('aria-label', `Выбрать подразделение ${unit.name}`);
    const icon = document.createElement('span');
    icon.className = 'unit-row-icon';
    const copy = document.createElement('span');
    copy.className = 'unit-row-copy';
    const name = document.createElement('strong');
    name.textContent = unit.name;
    const branch = document.createElement('span');
    branch.textContent = `${unit.side === 'russia' ? 'РОССИЯ' : 'США'} / ${unit.branch.toUpperCase()}`;
    const state = document.createElement('span');
    state.className = 'unit-row-state';
    state.textContent = getUnitStatus(unit);
    copy.append(name, branch);
    row.append(icon, copy, state);
    row.addEventListener('click', () => selectUnit(unit, true));
    elements.unitList.append(row);
  });
}

function updateUnitListStatuses() {
  world.units.forEach((unit) => {
    const row = elements.unitList.querySelector(`[data-unit-id="${unit.id}"]`);
    const state = row?.querySelector('.unit-row-state');
    if (state) state.textContent = getUnitStatus(unit);
  });
}

function selectUnit(unit, centerCamera = false) {
  selectedUnit = unit;
  world.selectUnit(unit);
  elements.unitList.querySelectorAll('.unit-row').forEach((row) => {
    row.classList.toggle('is-selected', row.dataset.unitId === unit?.id);
  });
  if (!unit) {
    elements.selectionName.innerHTML = 'НЕТ ВЫБОРА <small>— щёлкните по подразделению</small>';
    elements.selectedCardEmpty.classList.remove('is-hidden');
    elements.selectedUnitInfo.classList.add('is-hidden');
    return;
  }
  const faction = unit.side === 'russia' ? 'РОССИЯ' : 'США';
  elements.selectionName.textContent = `${unit.short} · ${faction}`;
  elements.selectedCardEmpty.classList.add('is-hidden');
  elements.selectedUnitInfo.classList.remove('is-hidden');
  elements.selectedUnitName.textContent = unit.short;
  elements.selectedUnitSide.textContent = `${faction} / ${unit.branch.toUpperCase()}`;
  elements.selectedUnitHealth.textContent = `${Math.round(unit.health)}%`;
  elements.selectedUnitSpeed.textContent = unit.speedLabel;
  elements.selectedAvatar.textContent = unit.type === 'tank' ? 'T' : unit.type === 'ifv' ? 'M' : unit.type === 'truck' ? '↗' : 'S';
  elements.selectedAvatar.style.borderColor = unit.side === 'russia' ? '#7e6846' : '#496c78';
  elements.selectedAvatar.style.color = unit.side === 'russia' ? '#d6b17a' : '#a3d0dd';
  updateSelectedUnitCard();
  if (centerCamera) {
    const root = unit.model.parent;
    world.recenter(root.position.x, root.position.z, 0.55);
    addLog(`Выбрано подразделение: ${unit.name}`, 'move');
  }
}

function updateRangeProgress(input) {
  const value = (Number(input.value) - Number(input.min)) / (Number(input.max) - Number(input.min)) * 100;
  input.style.setProperty('--range-progress', `${value}%`);
}

function setTargetBuilding(root) {
  if (!root) return;
  world.targetBuilding = root;
  updateIncidentCard();
  const data = root.userData.building;
  showMapToast(`ЦЕЛЬ ВЫБРАНА · ${data.name.toUpperCase()}`);
  addLog(`Цель воздействия: ${data.name}`, 'warning');
}

function findPointerHit(event, targets) {
  const rect = canvas.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, world.camera);
  const intersections = raycaster.intersectObjects(targets, true);
  return intersections[0] || null;
}

function getGroundHit(event) {
  const rect = canvas.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, world.camera);
  const intersections = raycaster.intersectObject(world.terrain, false);
  return intersections[0] || null;
}

function handleCanvasPointerUp(event) {
  if (!pointerDown || pointerDown.id !== event.pointerId) return;
  const down = pointerDown;
  pointerDown = null;
  const travel = Math.hypot(event.clientX - down.x, event.clientY - down.y);
  if (travel > 5) return;

  const roots = [...world.unitRoots, ...world.buildings];
  const hit = findPointerHit(event, roots);
  if (event.button === 0 || event.pointerType === 'touch') {
    if (hit) {
      const data = world.getObjectData(hit.object);
      if (data && data.id && world.units.includes(data)) {
        selectUnit(data, false);
        showMapToast(`ПОДРАЗДЕЛЕНИЕ · ${data.short.toUpperCase()}`);
      } else if (data && data.id && world.buildings.some((root) => root.userData.building === data)) {
        const root = world.buildings.find((item) => item.userData.building === data);
        setTargetBuilding(root);
      }
    } else if (event.pointerType === 'touch' && selectedUnit) {
      const ground = getGroundHit(event);
      if (ground) {
        const { x, z } = ground.point;
        world.moveUnit(selectedUnit, x, z);
        showMapToast(`ПРИКАЗ ПРИНЯТ · ${Math.round(x)}, ${Math.round(z)}`);
        addLog(`Приказ движения: ${selectedUnit.name}`, 'move');
      }
    }
  } else if (event.button === 2 && selectedUnit) {
    const ground = getGroundHit(event);
    if (ground) {
      const { x, z } = ground.point;
      world.moveUnit(selectedUnit, x, z);
      showMapToast(`ПРИКАЗ ПРИНЯТ · ${Math.round(x)}, ${Math.round(z)}`);
      addLog(`Приказ движения: ${selectedUnit.name}`, 'move');
    }
  }
}

function updateCoordinates(event) {
  if (!world) return;
  const ground = getGroundHit(event);
  if (ground) {
    elements.coordReadout.textContent = `X: ${String(Math.round(ground.point.x)).padStart(3, '0')} · Z: ${String(Math.round(ground.point.z)).padStart(3, '0')}`;
  }
}

function drawMinimap() {
  if (!world || !minimapContext) return;
  const context = minimapContext;
  const width = minimap.width;
  const height = minimap.height;
  const padding = 8;
  const mapSize = width - padding * 2;
  const mapHeight = height - padding * 2;
  const half = world.worldHalf;
  const toCanvas = (x, z) => ({
    x: padding + ((x + half) / (half * 2)) * mapSize,
    y: padding + ((z + half) / (half * 2)) * mapHeight,
  });

  context.clearRect(0, 0, width, height);
  const background = context.createLinearGradient(0, 0, width, height);
  background.addColorStop(0, '#52634f');
  background.addColorStop(0.5, '#68705a');
  background.addColorStop(1, '#47594d');
  context.fillStyle = background;
  context.fillRect(0, 0, width, height);

  // Low-contrast contour-like patches carry over the generated forest/relief palette.
  for (let i = 0; i < 18; i += 1) {
    const x = ((i * 47 + 19) % 220) + padding;
    const y = ((i * 31 + 7) % 132) + padding;
    context.fillStyle = i % 2 ? 'rgba(149, 151, 112, .10)' : 'rgba(25, 45, 40, .13)';
    context.beginPath();
    context.ellipse(x, y, 9 + (i % 4) * 5, 4 + (i % 3) * 3, i * 0.17, 0, Math.PI * 2);
    context.fill();
  }

  const drawPath = (points, color, lineWidth) => {
    context.beginPath();
    points.forEach((point, index) => {
      const location = toCanvas(point.x, point.z);
      if (index === 0) context.moveTo(location.x, location.y);
      else context.lineTo(location.x, location.y);
    });
    context.strokeStyle = color;
    context.lineWidth = lineWidth;
    context.lineCap = 'round';
    context.lineJoin = 'round';
    context.stroke();
  };
  drawPath(world.mapLines.riverPoints, 'rgba(138, 169, 156, .55)', 9);
  drawPath(world.mapLines.roadPoints, 'rgba(53, 60, 52, .9)', 4.6);
  drawPath(world.mapLines.roadPoints, 'rgba(194, 185, 135, .35)', 0.9);

  world.buildings.forEach((root) => {
    const building = root.userData.building;
    const location = toCanvas(building.x, building.z);
    context.save();
    context.translate(location.x, location.y);
    context.rotate(-0.03);
    context.fillStyle = building === getBuildingData(world.targetBuilding) ? 'rgba(247, 167, 91, .9)' : 'rgba(213, 219, 184, .64)';
    context.fillRect(-4.1, -3.1, 8.2, 6.2);
    context.strokeStyle = 'rgba(27, 35, 30, .72)';
    context.lineWidth = 1;
    context.strokeRect(-4.1, -3.1, 8.2, 6.2);
    context.restore();
  });

  world.units.forEach((unit) => {
    const root = unit.model.parent;
    const location = toCanvas(root.position.x, root.position.z);
    const isRussia = unit.side === 'russia';
    context.beginPath();
    context.arc(location.x, location.y, unit.selected ? 4.4 : 3.1, 0, Math.PI * 2);
    context.fillStyle = isRussia ? '#d8876f' : '#86bad1';
    context.fill();
    context.lineWidth = 1.1;
    context.strokeStyle = unit.selected ? '#eaf4ca' : 'rgba(16, 22, 19, .87)';
    context.stroke();
  });

  const target = world.controls.target;
  const center = toCanvas(target.x, target.z);
  const distance = world.camera.position.distanceTo(target);
  const viewportWidth = clamp(distance * 0.24, 13, 60);
  const viewportHeight = clamp(distance * 0.19, 10, 48);
  const topLeft = toCanvas(target.x - viewportWidth, target.z - viewportHeight);
  const bottomRight = toCanvas(target.x + viewportWidth, target.z + viewportHeight);
  context.strokeStyle = 'rgba(226, 239, 196, .78)';
  context.lineWidth = 1.2;
  context.setLineDash([4, 3]);
  context.strokeRect(topLeft.x, topLeft.y, bottomRight.x - topLeft.x, bottomRight.y - topLeft.y);
  context.setLineDash([]);
  context.beginPath();
  context.arc(center.x, center.y, 1.7, 0, Math.PI * 2);
  context.fillStyle = '#e4efc0';
  context.fill();
  context.strokeStyle = 'rgba(230, 240, 215, .24)';
  context.lineWidth = 1;
  context.strokeRect(padding + 0.5, padding + 0.5, mapSize - 1, mapHeight - 1);
}

function handleMinimapClick(event) {
  const rect = minimap.getBoundingClientRect();
  const x = (event.clientX - rect.left) / rect.width;
  const z = (event.clientY - rect.top) / rect.height;
  const worldX = (x * 2 - 1) * world.worldHalf;
  const worldZ = (z * 2 - 1) * world.worldHalf;
  world.recenter(worldX, worldZ, 0.62);
  showMapToast('ОБЗОР ПЕРЕМЕЩЁН');
}

async function exportSelectedModel() {
  if (!selectedUnit) {
    showToast('Сначала выберите подразделение на карте.');
    return;
  }
  const button = $('#export-button');
  const originalText = button.innerHTML;
  button.disabled = true;
  button.innerHTML = '<span class="export-spinner"></span> ПОДГОТОВКА GLB…';
  try {
    const exporter = new GLTFExporter();
    const asset = selectedUnit.model.clone(true);
    asset.position.set(0, 0, 0);
    asset.rotation.set(0, 0, 0);
    asset.scale.set(1, 1, 1);
    asset.updateMatrixWorld(true);
    const result = await exporter.parseAsync(asset, { binary: true, onlyVisible: true });
    const blob = new Blob([result], { type: 'model/gltf-binary' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${selectedUnit.id}-procedural.glb`;
    link.click();
    URL.revokeObjectURL(url);
    addLog(`GLB-модель экспортирована: ${selectedUnit.short}`, 'move');
    showToast(`GLB готов: ${selectedUnit.short}`);
  } catch (error) {
    console.error('GLB export failed:', error);
    showToast('Не удалось экспортировать GLB. Проверьте консоль браузера.');
  } finally {
    button.disabled = false;
    button.innerHTML = originalText;
  }
}

function resetScenario() {
  effects.reset();
  world.resetDamage();
  world.resetUnits();
  world.targetBuilding = world.buildings.find((root) => root.userData.building.id === 'warehouse-r3') || world.buildings[0];
  world.applyDamage(world.targetBuilding, 24);
  effects.startFire(world.targetBuilding);
  selectUnit(null, false);
  updateUnitListStatuses();
  updateIncidentCard();
  world.resetCamera();
  elements.eventLog.replaceChildren();
  logCounter = 0;
  addLog('Сценарий восстановлен до исходного состояния.');
  addLog('Склад R-3: учебное возгорание активно.', 'warning');
  showToast('Сценарий сброшен. Учебный очаг восстановлен.');
}

function initialize() {
  try {
    world = createBattlefield(canvas);
    effects = new EffectsSystem(world);
  } catch (error) {
    console.error('Three.js initialization failed:', error);
    elements.renderStatus.textContent = 'ENGINE / UNAVAILABLE';
    const errorCard = document.createElement('div');
    errorCard.className = 'engine-error';
    errorCard.innerHTML = '<strong>3D-движок не запустился</strong><span>Проверьте поддержку WebGL и обновите страницу.</span>';
    $('#scene-frame').append(errorCard);
    return;
  }

  world.applyDamage(world.targetBuilding, 24);
  effects.startFire(world.targetBuilding);
  buildUnitList();
  updateRangeProgress(elements.impactSlider);
  updateRangeProgress(elements.windSlider);
  updateIncidentCard();
  drawMinimap();
  addLog('Процедурная карта 6 × 6 км сгенерирована.', 'move');
  addLog('Учебный очаг: склад R-3, урон 24%.', 'warning');
  addLog('Подразделения обеих сторон готовы к приказам.');

  canvas.addEventListener('pointerdown', (event) => {
    pointerDown = { id: event.pointerId, x: event.clientX, y: event.clientY, button: event.button };
  });
  canvas.addEventListener('pointerup', handleCanvasPointerUp);
  canvas.addEventListener('pointermove', updateCoordinates);
  canvas.addEventListener('contextmenu', (event) => event.preventDefault());
  minimap.addEventListener('click', handleMinimapClick);

  $('#impact-button').addEventListener('click', () => {
    const target = world.targetBuilding;
    const data = target.userData.building;
    const impact = Number(elements.impactSlider.value);
    const damage = world.applyDamage(target, impact);
    const point = new THREE.Vector3(data.x, target.position.y + data.height * 0.45, data.z);
    effects.impact(point, target, impact, autoFireEnabled);
    if (autoFireEnabled && !data.isBurning) effects.startFire(target);
    updateIncidentCard();
    const buildingState = damage >= 96 ? 'разрушен' : `повреждён на ${Math.round(damage)}%`;
    addLog(`Воздействие по объекту «${data.name}»: ${buildingState}.`, 'warning');
    showToast(damage >= 96 ? 'Объект разрушен. Восстановите сценарий для повторного теста.' : 'Попадание смоделировано: повреждения и частицы обновлены.');
  });

  $('#vehicle-damage-button').addEventListener('click', () => {
    if (!selectedUnit) return showToast('Выберите подразделение для теста повреждений.');
    const component = $('#vehicle-component').value;
    const amount = Number(elements.impactSlider.value);
    const result = world.damageUnit(selectedUnit, component, amount);
    if (!result.applied) return showToast('У выбранной единицы нет такого узла или боекомплекта.');
    effects.vehicleHit(selectedUnit, component, amount);
    updateSelectedUnitCard();
    updateUnitListStatuses();
    const labels = { hull: 'корпус', engine: 'двигатель', mobility: 'ходовая часть', weapon: 'вооружение', ammo: 'боекомплект', fuelSystem: 'топливная система' };
    addLog(`${selectedUnit.name}: повреждён узел «${labels[component]}».`, 'warning');
    showToast(result.cookoff ? 'Критическое повреждение БК: подразделение выведено из строя.' : `Зафиксировано повреждение: ${labels[component]}.`);
  });

  $('#ammo-fire-button').addEventListener('click', () => {
    if (!selectedUnit) return showToast('Выберите боевую единицу.');
    const rounds = world.consumeAmmo(selectedUnit);
    if (!rounds) return showToast('Нет доступного боекомплекта или повреждено вооружение.');
    const target = world.targetBuilding;
    const data = target.userData.building;
    const damage = selectedUnit.type === 'tank' ? 12 : selectedUnit.type === 'ifv' ? 7 : 2;
    const end = effects.fireTestShot(selectedUnit);
    world.applyDamage(target, damage);
    effects.impact(end || new THREE.Vector3(data.x, target.position.y + data.height * 0.5, data.z), target, damage, autoFireEnabled);
    updateSelectedUnitCard();
    updateUnitListStatuses();
    updateIncidentCard();
    addLog(`${selectedUnit.name}: тестовый выстрел, расход БК −${rounds}.`, 'warning');
    showToast(`Тестовый выстрел. Боекомплект: ${selectedUnit.ammo.current} / ${selectedUnit.ammo.maximum || '—'}.`);
  });

  elements.impactSlider.addEventListener('input', () => {
    elements.impactValue.textContent = `${elements.impactSlider.value}%`;
    updateRangeProgress(elements.impactSlider);
  });
  elements.windSlider.addEventListener('input', () => {
    const value = Number(elements.windSlider.value);
    effects.windSpeed = value;
    elements.windValue.textContent = `${value} км/ч`;
    elements.windReadout.textContent = `СЗ · ${value} км/ч`;
    updateRangeProgress(elements.windSlider);
  });
  elements.smokeToggle.addEventListener('change', () => {
    effects.smokeEnabled = elements.smokeToggle.checked;
    addLog(`Визуализация дыма ${effects.smokeEnabled ? 'включена' : 'отключена'}.`, 'move');
  });
  elements.fireToggle.addEventListener('change', () => {
    effects.fireEnabled = elements.fireToggle.checked;
    updateIncidentCard();
    addLog(`Визуализация огня ${effects.fireEnabled ? 'включена' : 'отключена'}.`, 'move');
  });
  $('#pause-button').addEventListener('click', () => {
    world.playing = !world.playing;
    elements.pauseButton.classList.toggle('is-paused', !world.playing);
    elements.pauseLabel.textContent = world.playing ? 'ПАУЗА' : 'ПРОДОЛЖИТЬ';
    $('.run-icon').textContent = world.playing ? 'Ⅱ' : '▶';
    addLog(world.playing ? 'Симуляция продолжена.' : 'Симуляция поставлена на паузу.', 'move');
  });
  $('#reset-button').addEventListener('click', resetScenario);
  $('#clear-selection').addEventListener('click', () => selectUnit(null, false));
  $('#center-map').addEventListener('click', () => {
    world.resetCamera();
    showMapToast('ЦЕНТР СЕКТОРА');
  });
  $('#toggle-labels').addEventListener('click', (event) => {
    const visible = !world.labelsVisible;
    world.setLabelsVisible(visible);
    event.currentTarget.title = visible ? 'Скрыть подписи' : 'Показать подписи';
    showMapToast(visible ? 'ПОДПИСИ ВКЛЮЧЕНЫ' : 'ПОДПИСИ СКРЫТЫ');
  });
  $('#export-button').addEventListener('click', exportSelectedModel);
  $('#help-button').addEventListener('click', () => showToast('Демо-прототип: процедурная карта, тактические приказы, тест урона, огонь и дым.'));

  let previous = performance.now();
  const animate = (now) => {
    requestAnimationFrame(animate);
    const delta = Math.min((now - previous) / 1000, 0.045);
    previous = now;
    runningTime += delta;
    if (world.playing) effects.update(delta);
    world.update(delta, runningTime);
    frameCount += 1;
    if (now - lastStatsUpdate > 850) {
      fps = Math.round(frameCount * 1000 / (now - lastStatsUpdate || 850));
      frameCount = 0;
      lastStatsUpdate = now;
      elements.renderStatus.textContent = `ENGINE / WEBGL · ${fps} FPS`;
      updateIncidentCard();
      updateSelectedUnitCard();
      updateUnitListStatuses();
    }
    if (now - lastMinimapDraw > 250) {
      drawMinimap();
      lastMinimapDraw = now;
    }
  };
  requestAnimationFrame(animate);
}

initialize();
