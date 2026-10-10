import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const WORLD_HALF = 120;
const WORLD_SIZE = WORLD_HALF * 2;

function mulberry32(seed) {
  return function random() {
    let value = seed += 0x6D2B79F5;
    value = Math.imul(value ^ value >>> 15, value | 1);
    value ^= value + Math.imul(value ^ value >>> 7, value | 61);
    return ((value ^ value >>> 14) >>> 0) / 4294967296;
  };
}

const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

export function terrainHeight(x, z) {
  const rolling = Math.sin((x + 18) * 0.026) * 1.1
    + Math.cos((z - 11) * 0.031) * 0.88
    + Math.sin((x + z) * 0.022) * 0.64
    + Math.cos((x - z * 0.55) * 0.017) * 0.48;
  const hillA = Math.exp(-((x + 77) ** 2 + (z - 72) ** 2) / 1000) * 8.5;
  const hillB = Math.exp(-((x - 88) ** 2 + (z + 74) ** 2) / 1450) * 6.3;
  const ridge = Math.sin(x * 0.014 + z * 0.019) * Math.exp(-((x - 62) ** 2 + (z - 70) ** 2) / 3400) * 3.4;
  return rolling + hillA + hillB + ridge;
}

function standard(color, options = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.88, metalness: 0.02, ...options });
}

const textureCache = new Map();

function canvasTexture(canvas, colorSpace = THREE.SRGBColorSpace) {
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = colorSpace;
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = 4;
  texture.needsUpdate = true;
  return texture;
}

function makeNormalTexture(seed, scale = 0.34) {
  const size = 192;
  const random = mulberry32(seed);
  const height = new Float32Array(size * size);
  for (let i = 0; i < height.length; i += 1) height[i] = random();
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext('2d');
  const image = context.createImageData(size, size);
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const index = y * size + x;
      const left = height[y * size + (x + size - 1) % size];
      const right = height[y * size + (x + 1) % size];
      const up = height[((y + size - 1) % size) * size + x];
      const down = height[((y + 1) % size) * size + x];
      let nx = (left - right) * scale;
      let ny = (up - down) * scale;
      let nz = 1;
      const length = Math.hypot(nx, ny, nz);
      nx = nx / length * 0.5 + 0.5;
      ny = ny / length * 0.5 + 0.5;
      nz /= length;
      const pixel = index * 4;
      image.data[pixel] = Math.round(nx * 255);
      image.data[pixel + 1] = Math.round(ny * 255);
      image.data[pixel + 2] = Math.round(nz * 255);
      image.data[pixel + 3] = 255;
    }
  }
  context.putImageData(image, 0, 0);
  return canvasTexture(canvas, THREE.NoColorSpace);
}

function makeRoughnessTexture(seed, base = 205) {
  const size = 192;
  const random = mulberry32(seed);
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext('2d');
  const image = context.createImageData(size, size);
  for (let i = 0; i < size * size; i += 1) {
    const value = Math.max(0, Math.min(255, base + (random() - 0.5) * 56));
    const pixel = i * 4;
    image.data[pixel] = image.data[pixel + 1] = image.data[pixel + 2] = value;
    image.data[pixel + 3] = 255;
  }
  context.putImageData(image, 0, 0);
  return canvasTexture(canvas, THREE.NoColorSpace);
}

function makeCamoTexture(side) {
  const key = `camo-${side}`;
  if (textureCache.has(key)) return textureCache.get(key);
  const size = 512;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext('2d');
  const random = mulberry32(side === 'russia' ? 90210 : 73021);
  const russianPalette = ['#4c5c41', '#66734b', '#817f5c', '#343e32', '#a29b72', '#596648'];
  const americanPalette = ['#6b6c55', '#88836a', '#4c5547', '#a49a79', '#555c4d', '#777b60'];
  const palette = side === 'russia' ? russianPalette : americanPalette;
  context.fillStyle = side === 'russia' ? '#626e4d' : '#79765e';
  context.fillRect(0, 0, size, size);
  for (let i = 0; i < 118; i += 1) {
    const centerX = random() * size;
    const centerY = random() * size;
    const radiusX = 9 + random() * 38;
    const radiusY = 8 + random() * 25;
    const vertices = 5 + Math.floor(random() * 5);
    context.beginPath();
    for (let point = 0; point <= vertices; point += 1) {
      const angle = point / vertices * Math.PI * 2;
      const radius = 0.68 + random() * 0.62;
      const x = centerX + Math.cos(angle) * radiusX * radius;
      const y = centerY + Math.sin(angle) * radiusY * radius;
      if (point === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    }
    context.closePath();
    context.fillStyle = palette[Math.floor(random() * palette.length)];
    context.globalAlpha = 0.34 + random() * 0.44;
    context.fill();
  }
  context.globalAlpha = 1;
  const pixels = context.getImageData(0, 0, size, size);
  for (let i = 0; i < pixels.data.length; i += 4) {
    const grain = (random() - 0.5) * 18;
    pixels.data[i] = Math.max(0, Math.min(255, pixels.data[i] + grain));
    pixels.data[i + 1] = Math.max(0, Math.min(255, pixels.data[i + 1] + grain));
    pixels.data[i + 2] = Math.max(0, Math.min(255, pixels.data[i + 2] + grain * 0.82));
  }
  context.putImageData(pixels, 0, 0);
  context.globalAlpha = 0.24;
  for (let i = 0; i < 140; i += 1) {
    const x = random() * size;
    const y = random() * size;
    context.strokeStyle = i % 2 ? '#d5cba1' : '#20271f';
    context.lineWidth = 0.4 + random() * 1.2;
    context.beginPath();
    context.moveTo(x, y);
    context.lineTo(x + random() * 12 - 6, y + random() * 2 - 1);
    context.stroke();
  }
  context.globalAlpha = 1;
  const maps = {
    map: canvasTexture(canvas),
    normalMap: makeNormalTexture(side === 'russia' ? 5011 : 6143, 0.28),
    roughnessMap: makeRoughnessTexture(side === 'russia' ? 2112 : 3441, 212),
  };
  textureCache.set(key, maps);
  return maps;
}

function makeBuildingTexture(kind) {
  const key = `building-${kind}`;
  if (textureCache.has(key)) return textureCache.get(key);
  const size = 512;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext('2d');
  const random = mulberry32(kind.length * 7741 + 65);
  const base = kind === 'warehouse' ? '#7b7a6e' : kind === 'apartment' ? '#918a78' : '#8c846e';
  context.fillStyle = base;
  context.fillRect(0, 0, size, size);
  if (kind === 'warehouse') {
    for (let x = 0; x < size; x += 20) {
      context.fillStyle = x % 40 ? 'rgba(32,39,35,.10)' : 'rgba(230,225,200,.12)';
      context.fillRect(x, 0, 3, size);
      context.fillStyle = 'rgba(34,40,36,.18)';
      for (let y = 18; y < size; y += 70) {
        context.beginPath();
        context.arc(x + 10, y, 1.3, 0, Math.PI * 2);
        context.fill();
      }
    }
  } else {
    for (let y = 0; y < size; y += 32) {
      context.strokeStyle = 'rgba(54,55,47,.13)';
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(0, y);
      context.lineTo(size, y);
      context.stroke();
      const offset = (Math.floor(y / 32) % 2) * 24;
      for (let x = offset; x < size; x += 48) {
        context.beginPath();
        context.moveTo(x, y);
        context.lineTo(x, y + 32);
        context.stroke();
      }
    }
  }
  for (let i = 0; i < 1500; i += 1) {
    context.fillStyle = random() > 0.5 ? 'rgba(34,39,34,.055)' : 'rgba(235,225,197,.07)';
    context.fillRect(random() * size, random() * size, 1 + random() * 4, 1 + random() * 3);
  }
  const maps = {
    map: canvasTexture(canvas),
    normalMap: makeNormalTexture(kind.length * 437, kind === 'warehouse' ? 0.2 : 0.12),
    roughnessMap: makeRoughnessTexture(kind.length * 991, kind === 'warehouse' ? 224 : 206),
  };
  textureCache.set(key, maps);
  return maps;
}

function addMesh(parent, geometry, material, position = [0, 0, 0], options = {}) {
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.set(position[0], position[1], position[2]);
  mesh.castShadow = options.castShadow ?? true;
  mesh.receiveShadow = options.receiveShadow ?? true;
  if (options.rotation) mesh.rotation.set(...options.rotation);
  if (options.scale) mesh.scale.set(...options.scale);
  if (options.name) mesh.name = options.name;
  parent.add(mesh);
  return mesh;
}

function makeRibbon(points, width, yOffset = 0) {
  const vertices = [];
  const indices = [];
  for (let i = 0; i < points.length; i += 1) {
    const previous = points[Math.max(0, i - 1)];
    const next = points[Math.min(points.length - 1, i + 1)];
    const dx = next.x - previous.x;
    const dz = next.z - previous.z;
    const length = Math.hypot(dx, dz) || 1;
    const nx = -dz / length;
    const nz = dx / length;
    const half = width / 2;
    const y = terrainHeight(points[i].x, points[i].z) + yOffset;
    vertices.push(points[i].x + nx * half, y, points[i].z + nz * half);
    vertices.push(points[i].x - nx * half, y, points[i].z - nz * half);
    if (i < points.length - 1) {
      const offset = i * 2;
      indices.push(offset, offset + 1, offset + 2, offset + 1, offset + 3, offset + 2);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function createTerrain(scene, segments = 150) {
  const geometry = new THREE.PlaneGeometry(WORLD_SIZE, WORLD_SIZE, segments, segments);
  const position = geometry.attributes.position;
  const colors = [];
  const low = new THREE.Color('#66765b');
  const mid = new THREE.Color('#778364');
  const high = new THREE.Color('#91917a');
  const patch = new THREE.Color();

  for (let i = 0; i < position.count; i += 1) {
    const x = position.getX(i);
    const z = -position.getY(i);
    const height = terrainHeight(x, z);
    position.setZ(i, height);
    const moisture = 0.5 + Math.sin(x * 0.033) * 0.16 + Math.cos(z * 0.027) * 0.13;
    patch.copy(low).lerp(mid, clamp(moisture, 0, 1));
    if (height > 4.2) patch.lerp(high, clamp((height - 4.2) / 11, 0, 0.45));
    const speckle = 0.975 + (Math.sin(x * 2.1 + z * 0.83) * Math.cos(z * 1.61 - x * 0.37)) * 0.026;
    patch.multiplyScalar(speckle);
    colors.push(patch.r, patch.g, patch.b);
  }
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  geometry.rotateX(-Math.PI / 2);
  geometry.computeVertexNormals();

  const terrainMaterial = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1, metalness: 0 });
  const terrain = addMesh(scene, geometry, terrainMaterial, [0, 0, 0], { castShadow: false, name: 'Procedural terrain / 6 x 6 km' });
  terrain.receiveShadow = true;

  const edge = addMesh(scene, new THREE.BoxGeometry(WORLD_SIZE + 20, 1.8, WORLD_SIZE + 20), standard('#313c32'), [0, -5.2, 0], { castShadow: false, receiveShadow: false, name: 'World edge' });
  edge.visible = false;
  return terrain;
}

function createWaterAndRoad(scene) {
  const riverCurve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(-128, 0, -64),
    new THREE.Vector3(-90, 0, -54),
    new THREE.Vector3(-54, 0, -37),
    new THREE.Vector3(-18, 0, -22),
    new THREE.Vector3(19, 0, -7),
    new THREE.Vector3(56, 0, 12),
    new THREE.Vector3(91, 0, 29),
    new THREE.Vector3(130, 0, 39),
  ]);
  const riverPoints = riverCurve.getPoints(84);
  const riverGeometry = makeRibbon(riverPoints, 10.5, 0.35);
  const river = addMesh(scene, riverGeometry, new THREE.MeshPhysicalMaterial({
    color: '#52756f', roughness: 0.24, metalness: 0.08, transparent: true, opacity: 0.84,
  }), [0, 0, 0], { castShadow: false, name: 'River / procedural spline' });
  river.material.side = THREE.DoubleSide;
  river.renderOrder = 2;

  const bankGeometry = makeRibbon(riverPoints, 15.5, 0.16);
  const bank = addMesh(scene, bankGeometry, new THREE.MeshStandardMaterial({ color: '#817b5a', roughness: 1, side: THREE.DoubleSide }), [0, 0, 0], { castShadow: false, name: 'River bank' });
  bank.renderOrder = 1;

  const roadCurve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(-128, 0, 22),
    new THREE.Vector3(-90, 0, 20),
    new THREE.Vector3(-56, 0, 15),
    new THREE.Vector3(-20, 0, 11),
    new THREE.Vector3(19, 0, 9),
    new THREE.Vector3(59, 0, 8),
    new THREE.Vector3(94, 0, 10),
    new THREE.Vector3(128, 0, 15),
  ]);
  const roadPoints = roadCurve.getPoints(90);
  const shoulder = addMesh(scene, makeRibbon(roadPoints, 8.2, 0.26), standard('#777461', { side: THREE.DoubleSide }), [0, 0, 0], { castShadow: false, name: 'Route / gravel shoulder' });
  shoulder.renderOrder = 3;
  const asphalt = addMesh(scene, makeRibbon(roadPoints, 5.4, 0.31), standard('#484c44', { side: THREE.DoubleSide, roughness: 0.97 }), [0, 0, 0], { castShadow: false, name: 'Route / asphalt' });
  asphalt.renderOrder = 4;

  const centerPoints = roadCurve.getPoints(150).map((point) => new THREE.Vector3(point.x, terrainHeight(point.x, point.z) + 0.37, point.z));
  const markingGeometry = new THREE.BufferGeometry().setFromPoints(centerPoints);
  const marking = new THREE.Line(markingGeometry, new THREE.LineDashedMaterial({ color: '#c7c298', dashSize: 2.2, gapSize: 2.8, transparent: true, opacity: 0.38 }));
  marking.computeLineDistances();
  scene.add(marking);

  // A short service bridge ties the road across the shallow river crossing.
  const bridge = new THREE.Group();
  bridge.position.set(44, terrainHeight(44, 8) + 0.6, 8);
  bridge.rotation.y = -0.1;
  addMesh(bridge, new THREE.BoxGeometry(19, 0.65, 7.8), standard('#5d6258'), [0, 0, 0], { name: 'Bridge deck' });
  addMesh(bridge, new THREE.BoxGeometry(19, 0.42, 0.25), standard('#75796b'), [0, 0.61, -3.75], { name: 'Bridge rail north' });
  addMesh(bridge, new THREE.BoxGeometry(19, 0.42, 0.25), standard('#75796b'), [0, 0.61, 3.75], { name: 'Bridge rail south' });
  for (const x of [-7, -2.4, 2.4, 7]) {
    addMesh(bridge, new THREE.BoxGeometry(0.42, 0.15, 7.6), standard('#4d554d'), [x, 0.39, 0], { castShadow: false });
  }
  scene.add(bridge);

  return { roadPoints, riverPoints };
}

function createForest(scene, treeCount = 255) {
  const random = mulberry32(32817);
  const locations = [];
  let tries = 0;
  const roadZ = (x) => 11 + x * -0.065 + Math.sin(x * 0.035) * 1.4;
  const riverZ = (x) => -14 + x * 0.39;
  const safeBuildings = [
    [-23, 31], [-8, 31], [9, 31], [25, 32], [-23, 15], [-8, 16], [9, 15], [25, 14], [-22, -2], [-5, -2], [18, -2], [28, -2],
  ];
  while (locations.length < treeCount && tries < 5000) {
    tries += 1;
    const x = -112 + random() * 224;
    const z = -108 + random() * 216;
    if (Math.abs(z - roadZ(x)) < 9) continue;
    if (Math.abs(z - riverZ(x)) < 10) continue;
    if (x > -34 && x < 38 && z > -11 && z < 47) continue;
    if (safeBuildings.some(([bx, bz]) => Math.hypot(x - bx, z - bz) < 9)) continue;
    const cluster = (Math.sin(x * 0.047) + Math.cos(z * 0.061) + 2) / 4;
    if (random() > 0.56 + cluster * 0.39) continue;
    locations.push({ x, z, scale: 0.72 + random() * 0.7, hue: random() });
  }

  const trunkGeometry = new THREE.CylinderGeometry(0.18, 0.28, 1, 7);
  const crownGeometry = new THREE.ConeGeometry(1, 1, 7, 1);
  const trunkMaterial = standard('#ffffff');
  const crownMaterial = standard('#ffffff');

  const trunks = new THREE.InstancedMesh(trunkGeometry, trunkMaterial, locations.length);
  const crownOne = new THREE.InstancedMesh(crownGeometry, crownMaterial, locations.length);
  const crownTwo = new THREE.InstancedMesh(crownGeometry, crownMaterial, locations.length);
  const crownThree = new THREE.InstancedMesh(crownGeometry, crownMaterial, locations.length);
  trunks.castShadow = true;
  crownOne.castShadow = true;
  crownTwo.castShadow = true;
  crownThree.castShadow = true;
  trunks.receiveShadow = true;
  crownOne.receiveShadow = true;
  crownTwo.receiveShadow = true;
  crownThree.receiveShadow = true;
  const matrix = new THREE.Object3D();
  const treeColors = ['#52604b', '#5b674e', '#657154', '#485a49', '#6c7250'];
  const leafPalette = treeColors.map((value) => new THREE.Color(value));
  const trunkPalette = ['#5e513e', '#645844', '#554a39'].map((value) => new THREE.Color(value));

  locations.forEach((tree, index) => {
    const ground = terrainHeight(tree.x, tree.z);
    const trunkH = 1.4 * tree.scale;
    const tall = 5.4 * tree.scale;
    matrix.position.set(tree.x, ground + trunkH / 2, tree.z);
    matrix.rotation.set(0, tree.hue * Math.PI * 2, 0);
    matrix.scale.set(tree.scale, trunkH, tree.scale);
    matrix.updateMatrix();
    trunks.setMatrixAt(index, matrix.matrix);
    trunks.setColorAt(index, trunkPalette[index % trunkPalette.length]);

    const tiers = [
      { mesh: crownOne, y: ground + trunkH + tall * 0.23, radius: 1.33 * tree.scale, height: 3.2 * tree.scale, offset: 0 },
      { mesh: crownTwo, y: ground + trunkH + tall * 0.49, radius: 0.98 * tree.scale, height: 2.9 * tree.scale, offset: 1 },
      { mesh: crownThree, y: ground + trunkH + tall * 0.72, radius: 0.65 * tree.scale, height: 2.45 * tree.scale, offset: 2 },
    ];
    tiers.forEach((tier) => {
      matrix.position.set(tree.x, tier.y, tree.z);
      matrix.rotation.set(0, tree.hue * Math.PI * 2 + tier.offset, 0);
      matrix.scale.set(tier.radius, tier.height, tier.radius);
      matrix.updateMatrix();
      tier.mesh.setMatrixAt(index, matrix.matrix);
      const color = leafPalette[(index + tier.offset + Math.floor(tree.hue * 4)) % leafPalette.length];
      tier.mesh.setColorAt(index, color);
    });
  });
  [trunks, crownOne, crownTwo, crownThree].forEach((mesh) => {
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.computeBoundingSphere();
    scene.add(mesh);
  });

  const rockGeometry = new THREE.DodecahedronGeometry(1, 0);
  const rockMaterial = standard('#747568', { flatShading: true });
  const rocks = new THREE.InstancedMesh(rockGeometry, rockMaterial, 48);
  for (let i = 0; i < 48; i += 1) {
    const x = -108 + random() * 216;
    const z = -105 + random() * 210;
    const scale = 0.45 + random() * 1.25;
    matrix.position.set(x, terrainHeight(x, z) + scale * 0.31, z);
    matrix.rotation.set(random(), random() * Math.PI * 2, random() * 0.3);
    matrix.scale.set(scale * 1.25, scale * 0.7, scale);
    matrix.updateMatrix();
    rocks.setMatrixAt(i, matrix.matrix);
    rocks.setColorAt(i, new THREE.Color(random() > 0.5 ? '#77796e' : '#646b5f'));
  }
  rocks.castShadow = true;
  rocks.receiveShadow = true;
  scene.add(rocks);
}

function createGableGeometry(width, depth, rise) {
  const vertices = [
    -width / 2, 0, -depth / 2,
    width / 2, 0, -depth / 2,
    width / 2, 0, depth / 2,
    -width / 2, 0, depth / 2,
    -width / 2, rise, 0,
    width / 2, rise, 0,
  ];
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
  geometry.setIndex([
    0, 1, 5, 0, 5, 4,
    3, 4, 5, 3, 5, 2,
    0, 3, 4,
    1, 5, 2,
  ]);
  geometry.computeVertexNormals();
  return geometry;
}

function addBuildingWindows(group, width, height, depth, floors, columns, palette) {
  const windowMaterial = standard(palette.window, { roughness: 0.34, metalness: 0.04, emissive: palette.window, emissiveIntensity: 0.05 });
  const frameMaterial = standard(palette.frame, { roughness: 0.8 });
  const windowW = Math.min(0.9, width / (columns * 2.5));
  const windowH = Math.min(1.02, height / (floors * 2.8));
  for (const side of [-1, 1]) {
    for (let row = 0; row < floors; row += 1) {
      for (let col = 0; col < columns; col += 1) {
        const x = -width / 2 + (col + 0.5) * width / columns;
        const y = 1.05 + row * Math.max(1.5, (height - 1.4) / floors);
        const z = side * (depth / 2 + 0.035);
        addMesh(group, new THREE.BoxGeometry(windowW + 0.14, windowH + 0.13, 0.1), frameMaterial, [x, y, z], { castShadow: false });
        addMesh(group, new THREE.BoxGeometry(windowW, windowH, 0.13), windowMaterial, [x, y, z + side * 0.055], { castShadow: false });
        addMesh(group, new THREE.BoxGeometry(0.035, windowH, 0.03), frameMaterial, [x, y, z + side * 0.13], { castShadow: false });
      }
    }
  }
  for (const side of [-1, 1]) {
    const rows = Math.max(1, floors);
    const sideColumns = Math.max(1, Math.floor(depth / 4));
    for (let row = 0; row < rows; row += 1) {
      for (let col = 0; col < sideColumns; col += 1) {
        const z = -depth / 2 + (col + 0.5) * depth / sideColumns;
        const y = 1.1 + row * Math.max(1.5, (height - 1.4) / floors);
        const x = side * (width / 2 + 0.035);
        addMesh(group, new THREE.BoxGeometry(0.1, windowH + 0.13, Math.min(0.9, depth / (sideColumns * 2.4)) + 0.12), frameMaterial, [x, y, z], { castShadow: false });
        addMesh(group, new THREE.BoxGeometry(0.13, windowH, Math.min(0.9, depth / (sideColumns * 2.4))), windowMaterial, [x + side * 0.055, y, z], { castShadow: false });
      }
    }
  }
}

function createBuilding(scene, config, random) {
  const { id, name, x, z, width, depth, height, kind = 'residential', target = false } = config;
  const root = new THREE.Group();
  root.name = `Building / ${name}`;
  root.position.set(x, terrainHeight(x, z), z);
  const buildingMaps = makeBuildingTexture(kind);
  const roofMaps = makeBuildingTexture('warehouse');
  const baseMaterial = standard('#ffffff', { map: buildingMaps.map, normalMap: buildingMaps.normalMap, roughnessMap: buildingMaps.roughnessMap, roughness: 0.94 });
  const roofMaterial = standard(kind === 'warehouse' ? '#5f665c' : '#687064', { map: roofMaps.map, normalMap: roofMaps.normalMap, roughnessMap: roofMaps.roughnessMap, roughness: 0.92, side: THREE.DoubleSide });
  const trimMaterial = standard('#aaa38c', { roughness: 0.9 });
  const windowPalette = { window: kind === 'warehouse' ? '#414c49' : '#394743', frame: '#696d60' };
  const body = addMesh(root, new THREE.BoxGeometry(width, height, depth), baseMaterial, [0, height / 2, 0], { name: 'Structural shell' });
  const floors = Math.max(1, Math.floor(height / 2.7));
  const columns = Math.max(2, Math.floor(width / 3.1));
  addBuildingWindows(root, width, height, depth, floors, columns, windowPalette);

  let roof;
  if (kind === 'residential' || kind === 'house') {
    roof = addMesh(root, createGableGeometry(width + 0.9, depth + 0.9, Math.min(2.8, height * 0.38)), roofMaterial, [0, height, 0], { name: 'Pitched roof' });
    const chimney = addMesh(root, new THREE.BoxGeometry(0.72, 1.3, 0.72), standard('#756a5a'), [-width * 0.24, height + 1.9, -depth * 0.14], { name: 'Chimney' });
    chimney.rotation.z = -0.04;
  } else {
    roof = addMesh(root, new THREE.BoxGeometry(width + 0.45, 0.34, depth + 0.45), roofMaterial, [0, height + 0.16, 0], { name: 'Flat roof' });
    addMesh(root, new THREE.BoxGeometry(width + 0.72, 0.32, 0.32), trimMaterial, [0, height + 0.29, -depth / 2], { castShadow: false });
    addMesh(root, new THREE.BoxGeometry(width + 0.72, 0.32, 0.32), trimMaterial, [0, height + 0.29, depth / 2], { castShadow: false });
    for (let i = 0; i < (kind === 'warehouse' ? 4 : 2); i += 1) {
      const vent = addMesh(root, new THREE.BoxGeometry(1.15, 0.55, 0.9), standard('#555a52'), [width * (i / 6 - 0.2), height + 0.58, -depth * 0.18], { name: 'Roof vent' });
      if (kind === 'warehouse') addMesh(root, new THREE.BoxGeometry(0.08, 0.42, 0.95), standard('#858477'), [vent.position.x, vent.position.y, vent.position.z], { castShadow: false });
    }
  }

  if (kind === 'warehouse') {
    const doorMaterial = standard('#50564e', { roughness: 0.8 });
    addMesh(root, new THREE.BoxGeometry(width * 0.47, Math.min(height * 0.68, 3.8), 0.18), doorMaterial, [0, Math.min(height * 0.37, 2.05), depth / 2 + 0.12], { name: 'Loading door' });
    for (let i = 0; i < 5; i += 1) {
      addMesh(root, new THREE.BoxGeometry(width * 0.43, 0.055, 0.04), trimMaterial, [0, 0.75 + i * 0.55, depth / 2 + 0.23], { castShadow: false });
    }
    for (let i = 0; i < 9; i += 1) {
      const rib = addMesh(root, new THREE.BoxGeometry(0.1, height - 0.4, 0.11), standard('#6b6b5f'), [-width / 2 + i * width / 8, height / 2, depth / 2 + 0.035], { castShadow: false });
    }
  }

  if (kind === 'apartment') {
    const balconyMaterial = standard('#8f8a77');
    for (let row = 0; row < floors - 1; row += 1) {
      for (let col = 0; col < 3; col += 1) {
        addMesh(root, new THREE.BoxGeometry(1.65, 0.14, 0.72), balconyMaterial, [-width / 2 + 2.4 + col * 3.4, 1.45 + row * 2.8, depth / 2 + 0.36], { castShadow: false });
        addMesh(root, new THREE.BoxGeometry(1.55, 0.48, 0.06), standard('#767b6d'), [-width / 2 + 2.4 + col * 3.4, 1.72 + row * 2.8, depth / 2 + 0.7], { castShadow: false });
      }
    }
  }

  const groundPad = addMesh(scene, new THREE.PlaneGeometry(width + 3.6, depth + 3.6), standard('#8d876e', { roughness: 1 }), [x, terrainHeight(x, z) + 0.045, z], { rotation: [-Math.PI / 2, 0, 0], castShadow: false, receiveShadow: true, name: `${name} / apron` });
  groundPad.renderOrder = 1;

  const rubble = new THREE.Group();
  rubble.name = 'Damaged masonry';
  const rubbleMaterials = ['#625e51', '#777161', '#484c45', '#8c816a'].map((color) => standard(color, { roughness: 1, flatShading: true }));
  for (let i = 0; i < 13; i += 1) {
    const size = 0.45 + random() * 1.4;
    const angle = random() * Math.PI * 2;
    const radius = Math.max(width, depth) * (0.2 + random() * 0.48);
    const chunk = addMesh(rubble, new THREE.BoxGeometry(size * (0.7 + random()), size * (0.45 + random()), size * (0.6 + random())), rubbleMaterials[i % rubbleMaterials.length], [Math.cos(angle) * radius, 0.25 + random() * 0.42, Math.sin(angle) * radius], { name: 'Rubble fragment' });
    chunk.rotation.set(random() * 0.25, random() * Math.PI, random() * 0.32);
  }
  root.add(rubble);
  rubble.visible = false;

  const soot = new THREE.Mesh(new THREE.CircleGeometry(Math.max(width, depth) * 0.34, 32), new THREE.MeshBasicMaterial({ color: '#252621', transparent: true, opacity: 0, depthWrite: false }));
  soot.rotation.x = -Math.PI / 2;
  soot.position.set(0, 0.08, 0);
  root.add(soot);

  const damageDetails = root.children.filter((child) => child !== body && child !== roof && child !== rubble && child !== soot);
  root.userData.building = {
    id, name, x, z, width, depth, height, kind, target,
    damage: 0,
    isBurning: false,
    body,
    roof,
    rubble,
    soot,
    damageDetails,
    baseColor: baseMaterial.color.clone(),
    baseRoofColor: roofMaterial.color.clone(),
    roofMaterial,
    bodyMaterial: baseMaterial,
    maxIntegrity: 100,
    fireAnchor: new THREE.Vector3(x, terrainHeight(x, z) + height + 0.6, z),
  };
  scene.add(root);
  return root;
}

function addTrackWheels(group, xSign, width, depth, material) {
  const wheelMaterial = standard('#333a34', { roughness: 0.83, metalness: 0.04 });
  const hubMaterial = standard('#83816c', { roughness: 0.75, metalness: 0.18 });
  addMesh(group, new THREE.BoxGeometry(0.9, 0.86, depth * 0.91), material, [xSign * (width / 2 + 0.22), 0.64, 0], { name: 'Track assembly' });
  const wheelCount = Math.max(5, Math.round(depth / 1.05));
  for (let i = 0; i < wheelCount; i += 1) {
    const z = -depth * 0.39 + i * (depth * 0.78 / (wheelCount - 1));
    const wheel = addMesh(group, new THREE.CylinderGeometry(0.43, 0.43, 0.22, 12), wheelMaterial, [xSign * (width / 2 + 0.72), 0.64, z], { rotation: [0, 0, Math.PI / 2], name: 'Road wheel' });
    wheel.userData.rollingWheel = true;
    const hub = addMesh(group, new THREE.CylinderGeometry(0.15, 0.15, 0.245, 10), hubMaterial, [xSign * (width / 2 + 0.74), 0.64, z], { rotation: [0, 0, Math.PI / 2], name: 'Hub' });
    hub.userData.rollingWheel = true;
  }
}

function addWheel(group, x, z, scale = 1) {
  const rubber = standard('#252c29', { roughness: 0.96 });
  const hub = standard('#697063', { roughness: 0.82, metalness: 0.1 });
  const tire = addMesh(group, new THREE.CylinderGeometry(0.43 * scale, 0.43 * scale, 0.24 * scale, 12), rubber, [x, 0.52 * scale, z], { rotation: [0, 0, Math.PI / 2], name: 'Tire' });
  tire.userData.rollingWheel = true;
  const center = addMesh(group, new THREE.CylinderGeometry(0.17 * scale, 0.17 * scale, 0.27 * scale, 10), hub, [x + Math.sign(x) * 0.02, 0.52 * scale, z], { rotation: [0, 0, Math.PI / 2], name: 'Wheel hub' });
  center.userData.rollingWheel = true;
}

function createVehicleModel(unit, palette, random) {
  const model = new THREE.Group();
  model.name = `Procedural vehicle / ${unit.id}`;
  const paintMaps = makeCamoTexture(unit.side);
  const bodyMat = standard('#ffffff', { map: paintMaps.map, normalMap: paintMaps.normalMap, roughnessMap: paintMaps.roughnessMap, roughness: 0.9, metalness: 0.045 });
  const edgeMat = standard('#ffffff', { map: paintMaps.map, normalMap: paintMaps.normalMap, roughnessMap: paintMaps.roughnessMap, roughness: 0.82, metalness: 0.035 });
  const darkMat = standard('#2c332d', { roughnessMap: makeRoughnessTexture(8821, 238), roughness: 0.96 });
  const glassMat = standard('#263638', { roughness: 0.3, metalness: 0.1 });
  const accentMat = standard(palette.accent, { roughness: 0.72, metalness: 0.1 });
  const turretPivot = new THREE.Group();
  const wheels = [];
  const type = unit.type;

  if (type === 'tank') {
    addMesh(model, new THREE.BoxGeometry(4.85, 1.15, 6.9), bodyMat, [0, 1.11, 0], { name: 'Armored hull' });
    addMesh(model, new THREE.BoxGeometry(3.85, 0.3, 2.6), edgeMat, [0, 1.78, -0.72], { name: 'Engine deck' });
    addTrackWheels(model, -1, 4.85, 6.75, darkMat);
    addTrackWheels(model, 1, 4.85, 6.75, darkMat);
    model.traverse((object) => { if (object.userData.rollingWheel) wheels.push(object); });
    addMesh(model, new THREE.CylinderGeometry(1.55, 1.65, 0.42, 12), darkMat, [0, 1.85, -0.45], { name: 'Turret ring' });
    if (unit.side === 'russia') {
      addMesh(turretPivot, new THREE.DodecahedronGeometry(1, 0), bodyMat, [0, 0.2, 0], { scale: [1.85, 0.66, 1.9], name: 'Low profile turret' });
      for (const x of [-1.15, 0, 1.15]) addMesh(turretPivot, new THREE.BoxGeometry(0.72, 0.38, 0.72), edgeMat, [x, 0.77, -0.52], { name: 'Explosive reactive armor block' });
    } else {
      addMesh(turretPivot, new THREE.BoxGeometry(3.85, 1.16, 4.08), bodyMat, [0, 0.23, 0], { name: 'Angular turret' });
      addMesh(turretPivot, new THREE.BoxGeometry(1.05, 0.55, 0.86), edgeMat, [-1.38, 0.18, -1.22], { name: 'Rear turret stowage' });
      addMesh(turretPivot, new THREE.BoxGeometry(1.05, 0.55, 0.86), edgeMat, [1.38, 0.18, -1.22], { name: 'Rear turret stowage' });
    }
    addMesh(turretPivot, new THREE.BoxGeometry(2.25, 0.48, 1.18), edgeMat, [0, 0.54, 0.35], { name: 'Turret mantlet' });
    const cannon = addMesh(turretPivot, new THREE.CylinderGeometry(0.19, 0.23, 4.7, 12), bodyMat, [0, 0.53, 2.75], { rotation: [Math.PI / 2, 0, 0], name: 'Main gun' });
    cannon.rotation.x = Math.PI / 2;
    addMesh(turretPivot, new THREE.CylinderGeometry(0.23, 0.25, 0.38, 12), edgeMat, [0, 0.53, 5.02], { rotation: [Math.PI / 2, 0, 0], name: 'Muzzle' });
    addMesh(turretPivot, new THREE.CylinderGeometry(0.58, 0.58, 0.24, 12), bodyMat, [0, 0.81, -0.52], { name: 'Commander hatch' });
    const hatch = addMesh(turretPivot, new THREE.BoxGeometry(0.18, 0.44, 0.45), edgeMat, [0.82, 0.28, -0.5], { rotation: [0, 0.18, 0], name: 'Optics' });
    addMesh(model, new THREE.BoxGeometry(4.8, 0.14, 0.2), accentMat, [0, 1.2, 3.46], { castShadow: false, name: 'Faction recognition panel' });
    turretPivot.position.set(0, 1.85, -0.45);
    turretPivot.userData.turret = true;
    model.add(turretPivot);
  } else if (type === 'ifv') {
    const russianIfv = unit.side === 'russia';
    const hullWidth = russianIfv ? 4.3 : 4.75;
    const hullLength = russianIfv ? 5.85 : 6.4;
    addMesh(model, new THREE.BoxGeometry(hullWidth, russianIfv ? 1.35 : 1.68, hullLength), bodyMat, [0, 1.12, 0], { name: 'Armored carrier hull' });
    addMesh(model, new THREE.BoxGeometry(hullWidth - 0.35, 0.45, hullLength * 0.71), edgeMat, [0, 1.95, -0.58], { name: 'Upper armor' });
    addMesh(model, new THREE.BoxGeometry(hullWidth - 0.9, 0.45, 0.2), darkMat, [0, 1.42, hullLength / 2], { name: 'Rear ramp' });
    addTrackWheels(model, -1, hullWidth, hullLength, darkMat);
    addTrackWheels(model, 1, hullWidth, hullLength, darkMat);
    model.traverse((object) => { if (object.userData.rollingWheel) wheels.push(object); });
    addMesh(model, new THREE.CylinderGeometry(0.8, 0.85, 0.48, 10), darkMat, [0, 2.12, 0.5], { name: 'Remote weapon mount' });
    if (russianIfv) {
      addMesh(turretPivot, new THREE.DodecahedronGeometry(1, 0), bodyMat, [0, 0.25, 0], { scale: [0.88, 0.42, 0.82], name: 'BMP-3 turret' });
      addMesh(turretPivot, new THREE.CylinderGeometry(0.16, 0.19, 3.15, 10), edgeMat, [0.12, 0.38, 1.78], { rotation: [Math.PI / 2, 0, 0], name: 'Low velocity cannon' });
      addMesh(turretPivot, new THREE.CylinderGeometry(0.08, 0.1, 2.2, 8), darkMat, [-0.34, 0.24, 1.62], { rotation: [Math.PI / 2, 0, 0], name: 'Coaxial cannon' });
    } else {
      addMesh(turretPivot, new THREE.BoxGeometry(2.18, 0.78, 2.0), bodyMat, [0, 0.25, 0], { name: 'Bradley turret' });
      addMesh(turretPivot, new THREE.CylinderGeometry(0.12, 0.16, 2.8, 10), edgeMat, [0.15, 0.35, 1.75], { rotation: [Math.PI / 2, 0, 0], name: 'Autocannon' });
      addMesh(turretPivot, new THREE.BoxGeometry(0.62, 0.5, 0.58), glassMat, [-0.92, 0.48, 0.18], { name: 'Optical sight' });
      addMesh(turretPivot, new THREE.BoxGeometry(0.8, 0.32, 0.72), edgeMat, [1.35, 0.12, -0.7], { name: 'Turret stowage' });
    }
    addMesh(model, new THREE.BoxGeometry(hullWidth - 0.1, 0.15, 0.18), accentMat, [0, 1.07, hullLength / 2], { castShadow: false, name: 'Faction recognition panel' });
    turretPivot.position.set(0, russianIfv ? 1.95 : 2.05, 0.42);
    turretPivot.userData.turret = true;
    model.add(turretPivot);
  } else if (type === 'truck') {
    if (unit.side === 'usa') {
      // A compact, four-wheel utility vehicle silhouette for the HMMWV unit.
      addMesh(model, new THREE.BoxGeometry(2.15, 0.72, 5.15), bodyMat, [0, 0.82, 0], { name: 'Utility chassis' });
      addMesh(model, new THREE.BoxGeometry(2.2, 0.7, 1.52), bodyMat, [0, 1.27, 1.63], { name: 'Engine hood' });
      addMesh(model, new THREE.BoxGeometry(2.12, 1.38, 2.18), bodyMat, [0, 1.91, 0.15], { name: 'Cab' });
      addMesh(model, new THREE.BoxGeometry(1.86, 0.76, 0.08), glassMat, [0, 2.08, 1.26], { name: 'Windshield' });
      addMesh(model, new THREE.BoxGeometry(0.08, 0.84, 0.11), edgeMat, [-0.96, 2.0, 1.27], { castShadow: false });
      addMesh(model, new THREE.BoxGeometry(0.08, 0.84, 0.11), edgeMat, [0.96, 2.0, 1.27], { castShadow: false });
      for (const side of [-1, 1]) {
        addMesh(model, new THREE.BoxGeometry(0.075, 0.62, 1.12), glassMat, [side * 1.075, 2.02, 0.04], { name: 'Cab side window' });
        addWheel(model, side * 1.18, -1.63, 0.97);
        addWheel(model, side * 1.18, 1.65, 0.97);
      }
      addMesh(model, new THREE.BoxGeometry(2.0, 0.18, 1.12), edgeMat, [0, 1.24, -1.58], { name: 'Rear utility deck' });
      addMesh(model, new THREE.CylinderGeometry(0.55, 0.55, 0.22, 12), darkMat, [0, 1.44, -2.42], { rotation: [0, 0, Math.PI / 2], name: 'Rear spare wheel' });
      addMesh(model, new THREE.BoxGeometry(2.05, 0.14, 0.16), accentMat, [0, 0.94, 2.58], { castShadow: false, name: 'Faction recognition panel' });
    } else {
      // Six-wheel cargo configuration for the Russian Ural supply truck.
      addMesh(model, new THREE.BoxGeometry(2.55, 1.15, 7.15), bodyMat, [0, 1.03, -0.05], { name: 'Utility chassis' });
      addMesh(model, new THREE.BoxGeometry(2.48, 1.75, 2.3), bodyMat, [0, 1.97, 2.15], { name: 'Cab' });
      addMesh(model, new THREE.BoxGeometry(2.18, 0.78, 0.08), glassMat, [0, 2.15, 3.33], { name: 'Windshield' });
      addMesh(model, new THREE.BoxGeometry(0.1, 1.0, 0.1), edgeMat, [-1.1, 2.15, 3.36], { castShadow: false });
      addMesh(model, new THREE.BoxGeometry(0.1, 1.0, 0.1), edgeMat, [1.1, 2.15, 3.36], { castShadow: false });
      addMesh(model, new THREE.BoxGeometry(2.4, 1.75, 3.45), edgeMat, [0, 2.0, -1.72], { name: 'Canvas cargo bed' });
      for (const x of [-1, 1]) {
        addMesh(model, new THREE.BoxGeometry(0.11, 1.42, 3.26), bodyMat, [x * 1.25, 2.04, -1.72], { name: 'Cargo side rail' });
        addWheel(model, x * 1.35, -2.52, 0.9);
        addWheel(model, x * 1.35, -0.47, 0.9);
        addWheel(model, x * 1.35, 2.31, 0.9);
      }
      addMesh(model, new THREE.BoxGeometry(2.45, 0.13, 0.15), accentMat, [0, 1.14, 3.61], { castShadow: false, name: 'Faction recognition panel' });
    }
    model.traverse((object) => { if (object.userData.rollingWheel) wheels.push(object); });
  } else {
    const soldierPalette = [bodyMat, edgeMat, accentMat];
    const positions = [[-1.05, 0], [0.95, 0.2], [0, -1.55], [-0.95, -2.1]];
    positions.forEach(([x, z], index) => {
      const soldier = new THREE.Group();
      soldier.position.set(x, 0, z);
      soldier.rotation.y = (index % 2 ? 1 : -1) * 0.18;
      addMesh(soldier, new THREE.CylinderGeometry(0.18, 0.23, 0.75, 7), soldierPalette[index % soldierPalette.length], [0, 1.0, 0], { name: 'Infantry armor' });
      addMesh(soldier, new THREE.SphereGeometry(0.22, 8, 6), standard(palette.body), [0, 1.54, 0.03], { name: 'Helmet' });
      addMesh(soldier, new THREE.BoxGeometry(0.34, 0.12, 0.32), accentMat, [0, 1.66, 0.02], { castShadow: false, name: 'Helmet band' });
      addMesh(soldier, new THREE.BoxGeometry(0.12, 0.52, 0.16), bodyMat, [-0.1, 0.37, 0], { rotation: [0, 0, -0.08], name: 'Leg' });
      addMesh(soldier, new THREE.BoxGeometry(0.12, 0.52, 0.16), bodyMat, [0.1, 0.37, 0.02], { rotation: [0, 0, 0.08], name: 'Leg' });
      addMesh(soldier, new THREE.BoxGeometry(0.12, 0.52, 0.15), bodyMat, [-0.28, 1.05, 0.2], { rotation: [0.15, 0, -0.28], name: 'Arm' });
      addMesh(soldier, new THREE.BoxGeometry(0.12, 0.52, 0.15), bodyMat, [0.26, 1.02, 0.17], { rotation: [0.15, 0, 0.28], name: 'Arm' });
      const rifle = addMesh(soldier, new THREE.BoxGeometry(0.08, 0.08, 0.83), darkMat, [0.16, 1.02, 0.58], { name: 'Rifle silhouette' });
      rifle.rotation.x = -0.1;
      model.add(soldier);
    });
  }

  // Small service details make each generated silhouette read clearly at tactical zoom.
  if (type !== 'squad') {
    const panelZ = type === 'truck' ? (unit.side === 'usa' ? 0.18 : 0.9) : 0.9;
    const sideColor = palette.mark;
    for (const side of [-1, 1]) {
      const sideX = type === 'truck' ? (unit.side === 'usa' ? 1.12 : 1.28) : 2.52;
      const sideY = type === 'truck' ? (unit.side === 'usa' ? 1.38 : 1.38) : 1.72;
      addMesh(model, new THREE.BoxGeometry(0.14, 0.26, 0.58), standard(sideColor), [side * sideX, sideY, panelZ], { castShadow: false, name: 'Side marking' });
    }
    if (type !== 'truck') {
      const hatchCount = type === 'tank' ? 3 : 2;
      for (let i = 0; i < hatchCount; i += 1) {
        const hatch = addMesh(model, new THREE.CylinderGeometry(0.22, 0.24, 0.13, 10), edgeMat, [i * 0.68 - (hatchCount - 1) * 0.34, 2.03, -1.66], { name: 'Service hatch' });
        addMesh(model, new THREE.BoxGeometry(0.44, 0.1, 0.06), darkMat, [hatch.position.x, 2.13, -1.66], { castShadow: false });
      }
    }
    const rearPanelZ = type === 'truck' ? (unit.side === 'usa' ? -2.7 : -3.66) : -3.1;
    addMesh(model, new THREE.BoxGeometry(type === 'truck' ? 2.1 : 3.25, 0.11, 0.18), accentMat, [0, 0.73, rearPanelZ], { castShadow: false, name: 'Rear recognition panel' });
  }

  // Slight palette variation is deterministic per spawned model, not a downloaded asset.
  if (random() > 0.55) bodyMat.color.offsetHSL(0, 0, (random() - 0.5) * 0.055);
  return { model, wheels, turretPivot };
}

function makeUnitLabel(text, sideColor) {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 96;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = 'rgba(10, 16, 15, 0.84)';
  ctx.beginPath();
  ctx.roundRect(8, 8, 496, 80, 8);
  ctx.fill();
  ctx.fillStyle = sideColor;
  ctx.fillRect(8, 8, 5, 80);
  ctx.strokeStyle = 'rgba(220, 232, 209, 0.28)';
  ctx.lineWidth = 2;
  ctx.strokeRect(9, 9, 494, 78);
  ctx.fillStyle = '#dce5d6';
  ctx.font = '600 34px system-ui, sans-serif';
  ctx.textBaseline = 'middle';
  ctx.fillText(text.toUpperCase(), 29, 48, 444);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false, opacity: 0.78 }));
  sprite.scale.set(12, 2.25, 1);
  sprite.position.set(0, 9.2, 0);
  sprite.renderOrder = 18;
  return sprite;
}

function makeSelectionRing(sideColor) {
  const ring = new THREE.Mesh(new THREE.RingGeometry(4.1, 4.28, 64), new THREE.MeshBasicMaterial({ color: sideColor, transparent: true, opacity: 0.8, side: THREE.DoubleSide, depthWrite: false }));
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = 0.16;
  ring.visible = false;
  ring.renderOrder = 7;
  return ring;
}

function createUnit(scene, config, random) {
  const root = new THREE.Group();
  root.name = `Unit / ${config.name}`;
  root.position.set(config.x, terrainHeight(config.x, config.z) - 0.1, config.z);
  root.rotation.y = config.heading ?? 0;
  const palette = config.side === 'russia'
    ? { body: '#606c4b', edge: '#79805c', accent: '#ad7651', mark: '#ae6d55', side: '#d57960' }
    : { body: '#77735a', edge: '#8c8569', accent: '#a8a187', mark: '#8f735b', side: '#88b8c8' };
  const { model, wheels, turretPivot } = createVehicleModel(config, palette, random);
  root.add(model);
  const sideColor = config.side === 'russia' ? '#df8468' : '#84b5c8';
  const label = makeUnitLabel(config.name, sideColor);
  const selectionRing = makeSelectionRing(sideColor);
  root.add(label, selectionRing);
  const ammoCapacity = config.type === 'tank' ? 42 : config.type === 'ifv' ? 180 : config.type === 'truck' ? 0 : 120;
  const baseSpeed = config.type === 'tank' ? 5.8 : config.type === 'ifv' ? 7.3 : config.type === 'truck' ? 8.4 : 3.1;
  root.userData.unit = {
    ...config,
    model,
    wheels,
    turretPivot,
    label,
    selectionRing,
    goal: null,
    selected: false,
    health: 100,
    components: { hull: 100, engine: 100, mobility: 100, weapon: 100, fuelSystem: 100 },
    ammo: { current: ammoCapacity, maximum: ammoCapacity },
    fuel: 100,
    ammoCookoff: false,
    damageMarks: [],
    baseSpeed,
    speed: baseSpeed,
    speedKmh: Number.parseInt(config.speedLabel, 10) || 30,
    heading: config.heading ?? 0,
    startHeading: config.heading ?? 0,
    startX: config.x,
    startZ: config.z,
  };
  scene.add(root);
  return root;
}

function createWorldMarker(scene, x, z, text, color, size = 2.5) {
  const geometry = new THREE.RingGeometry(size * 0.72, size, 32);
  const material = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.31, side: THREE.DoubleSide, depthWrite: false });
  const ring = addMesh(scene, geometry, material, [x, terrainHeight(x, z) + 0.2, z], { rotation: [-Math.PI / 2, 0, 0], castShadow: false, name: text });
  return ring;
}

export function createBattlefield(canvas) {
  const lowPower = Boolean(window.matchMedia?.('(max-width: 850px)').matches || (navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4));
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#83918a');
  scene.fog = new THREE.FogExp2('#84918a', 0.00185);

  const camera = new THREE.PerspectiveCamera(44, 1, 0.1, 800);
  camera.position.set(114, 137, 149);
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: !lowPower, alpha: false, powerPreference: lowPower ? 'low-power' : 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, lowPower ? 1.2 : 1.75));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.22;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.setClearColor('#83918a', 1);

  const hemisphere = new THREE.HemisphereLight('#edf2df', '#5b6458', 2.05);
  scene.add(hemisphere);
  const sun = new THREE.DirectionalLight('#fff2d9', 2.45);
  sun.position.set(-55, 92, 38);
  sun.castShadow = true;
  sun.shadow.mapSize.set(lowPower ? 1024 : 2048, lowPower ? 1024 : 2048);
  sun.shadow.camera.left = -145;
  sun.shadow.camera.right = 145;
  sun.shadow.camera.top = 145;
  sun.shadow.camera.bottom = -145;
  sun.shadow.camera.near = 1;
  sun.shadow.camera.far = 290;
  sun.shadow.bias = -0.00038;
  sun.shadow.normalBias = 0.025;
  scene.add(sun);
  const fill = new THREE.DirectionalLight('#b3c8cb', 0.46);
  fill.position.set(72, 30, -70);
  scene.add(fill);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 1, 0);
  controls.enableDamping = true;
  controls.dampingFactor = 0.075;
  controls.minDistance = 34;
  controls.maxDistance = 270;
  controls.minPolarAngle = 0.32;
  controls.maxPolarAngle = Math.PI / 2.08;
  controls.enablePan = true;
  controls.screenSpacePanning = false;
  controls.rotateSpeed = 0.45;
  controls.panSpeed = 0.65;
  controls.zoomSpeed = 0.85;
  controls.target.set(0, 0, 0);
  controls.update();

  const random = mulberry32(481516);
  const terrain = createTerrain(scene, lowPower ? 96 : 150);
  const mapLines = createWaterAndRoad(scene);
  createForest(scene, lowPower ? 170 : 255);

  const buildings = [];
  const buildingConfigs = [
    { id: 'warehouse-r3', name: 'Склад · сектор R-3', x: 10, z: 30, width: 13.5, depth: 9.2, height: 5.6, kind: 'warehouse', target: true },
    { id: 'depot-east', name: 'Депо', x: 26, z: 32, width: 9, depth: 8.2, height: 4.3, kind: 'warehouse' },
    { id: 'residence-a', name: 'Жилой корпус A', x: -10, z: 32, width: 10, depth: 8, height: 8.4, kind: 'apartment' },
    { id: 'residence-b', name: 'Жилой корпус B', x: -24, z: 31, width: 8.4, depth: 7.2, height: 6.7, kind: 'residential' },
    { id: 'clinic', name: 'Медпункт', x: -24, z: 14, width: 9.5, depth: 8, height: 4.2, kind: 'house' },
    { id: 'workshop', name: 'Мастерская', x: -8, z: 13, width: 11.5, depth: 8.4, height: 4.8, kind: 'warehouse' },
    { id: 'residence-c', name: 'Жилой корпус C', x: 9, z: 14, width: 9.2, depth: 7.8, height: 7.1, kind: 'apartment' },
    { id: 'residence-d', name: 'Дом на холме', x: 27, z: 13, width: 8.2, depth: 7, height: 5.8, kind: 'residential' },
    { id: 'station', name: 'Станция связи', x: -22, z: -4, width: 9, depth: 7.6, height: 5.1, kind: 'warehouse' },
    { id: 'hangar', name: 'Сервисный ангар', x: 28, z: -14, width: 12, depth: 8.5, height: 4.9, kind: 'warehouse' },
    { id: 'water-tower', name: 'Водонапорная башня', x: 5, z: -5, width: 6.5, depth: 6.5, height: 8.3, kind: 'apartment' },
    { id: 'house-east', name: 'Полевой дом', x: 40, z: -4, width: 8, depth: 7, height: 4.8, kind: 'house' },
  ];
  buildingConfigs.forEach((config) => buildings.push(createBuilding(scene, config, random)));
  const targetBuilding = buildings.find((building) => building.userData.building.target);

  // Sparse field markers help communicate distance and give the playable area scale.
  [[-89, -82, 'OBS-1', '#b8cc96'], [85, -73, 'OBS-2', '#b8cc96'], [92, 79, 'OBS-3', '#b8cc96']].forEach(([x, z, label, color]) => createWorldMarker(scene, x, z, label, color, 1.8));

  const unitConfigs = [
    { id: 'ru-t90', name: 'Т-90М · 01', short: 'Т-90М', side: 'russia', type: 'tank', x: -67, z: 2, heading: 0.32, branch: 'Бронетехника', speedLabel: '32 км/ч' },
    { id: 'ru-bmp', name: 'БМП-3 · 02', short: 'БМП-3', side: 'russia', type: 'ifv', x: -58, z: -12, heading: 0.25, branch: 'Бронетехника', speedLabel: '41 км/ч' },
    { id: 'ru-log', name: 'Урал · снабжение', short: 'УРАЛ', side: 'russia', type: 'truck', x: -82, z: 26, heading: 0.05, branch: 'Обеспечение', speedLabel: '48 км/ч' },
    { id: 'ru-squad', name: 'Группа «Север»', short: 'ПЕХОТА', side: 'russia', type: 'squad', x: -49, z: 28, heading: 0.4, branch: 'Пехота', speedLabel: '18 км/ч' },
    { id: 'us-m1', name: 'M1A2 · ALPHA', short: 'M1A2', side: 'usa', type: 'tank', x: 68, z: -9, heading: -0.55, branch: 'Бронетехника', speedLabel: '38 км/ч' },
    { id: 'us-bradley', name: 'M2 BRADLEY · 2', short: 'BRADLEY', side: 'usa', type: 'ifv', x: 58, z: 22, heading: -0.48, branch: 'Бронетехника', speedLabel: '43 км/ч' },
    { id: 'us-truck', name: 'HMMWV · LOG', short: 'HMMWV', side: 'usa', type: 'truck', x: 86, z: 4, heading: -0.2, branch: 'Обеспечение', speedLabel: '55 км/ч' },
    { id: 'us-squad', name: 'SQUAD · ECHO', short: 'SQUAD', side: 'usa', type: 'squad', x: 52, z: -25, heading: -0.42, branch: 'Пехота', speedLabel: '19 км/ч' },
  ];
  const units = unitConfigs.map((config) => createUnit(scene, config, random));

  // A subtle perimeter helps read the 6 km x 6 km generated test map.
  const boundaryMaterial = new THREE.LineDashedMaterial({ color: '#dce7c7', dashSize: 4, gapSize: 4, transparent: true, opacity: 0.13 });
  const boundaryPoints = [
    new THREE.Vector3(-WORLD_HALF, 0, -WORLD_HALF), new THREE.Vector3(WORLD_HALF, 0, -WORLD_HALF),
    new THREE.Vector3(WORLD_HALF, 0, WORLD_HALF), new THREE.Vector3(-WORLD_HALF, 0, WORLD_HALF), new THREE.Vector3(-WORLD_HALF, 0, -WORLD_HALF),
  ];
  boundaryPoints.forEach((point) => { point.y = terrainHeight(point.x, point.z) + 0.25; });
  const boundary = new THREE.Line(new THREE.BufferGeometry().setFromPoints(boundaryPoints), boundaryMaterial);
  boundary.computeLineDistances();
  scene.add(boundary);

  const resizeObserver = new ResizeObserver(() => {
    const width = Math.max(1, canvas.clientWidth);
    const height = Math.max(1, canvas.clientHeight);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  });
  resizeObserver.observe(canvas.parentElement || canvas);
  const initialWidth = Math.max(1, canvas.clientWidth);
  const initialHeight = Math.max(1, canvas.clientHeight);
  renderer.setSize(initialWidth, initialHeight, false);
  camera.aspect = initialWidth / initialHeight;
  camera.updateProjectionMatrix();

  const world = {
    scene,
    camera,
    renderer,
    controls,
    terrain,
    units: units.map((root) => root.userData.unit),
    unitRoots: units,
    buildings,
    targetBuilding,
    mapLines,
    worldHalf: WORLD_HALF,
    labelsVisible: true,
    playing: true,
    getObjectData(object) {
      let current = object;
      while (current) {
        if (current.userData?.unit) return current.userData.unit;
        if (current.userData?.building) return current.userData.building;
        current = current.parent;
      }
      return null;
    },
    recenter(x = 0, z = 0, duration = 0) {
      const target = new THREE.Vector3(x, terrainHeight(x, z), z);
      if (duration > 0) {
        this.cameraMove = { from: controls.target.clone(), to: target, elapsed: 0, duration };
      } else {
        controls.target.copy(target);
        controls.update();
      }
    },
    resetCamera() {
      camera.position.set(114, 137, 149);
      controls.target.set(0, 0, 0);
      controls.update();
    },
    selectUnit(unit) {
      this.units.forEach((current) => {
        current.selected = current === unit;
        current.selectionRing.visible = current.selected;
        current.label.material.opacity = current.selected ? 1 : 0.69;
        current.label.scale.set(current.selected ? 13.5 : 12, current.selected ? 2.55 : 2.25, 1);
      });
    },
    setLabelsVisible(visible) {
      this.labelsVisible = visible;
      this.units.forEach((unit) => { unit.label.visible = visible; });
    },
    moveUnit(unit, x, z) {
      if (!unit) return;
      unit.goal = new THREE.Vector3(clamp(x, -WORLD_HALF + 8, WORLD_HALF - 8), 0, clamp(z, -WORLD_HALF + 8, WORLD_HALF - 8));
    },
    consumeAmmo(unit) {
      if (!unit || unit.ammo.maximum <= 0 || unit.ammo.current <= 0 || unit.components.weapon <= 0) return 0;
      const rounds = unit.type === 'tank' ? 1 : unit.type === 'ifv' ? 5 : unit.type === 'squad' ? 3 : 0;
      unit.ammo.current = Math.max(0, unit.ammo.current - rounds);
      return rounds;
    },
    damageUnit(unit, component, amount = 42) {
      if (!unit) return { applied: false, ammoLost: 0, cookoff: false };
      const severity = clamp(amount, 5, 100);
      let ammoLost = 0;
      let cookoff = false;
      if (component === 'ammo') {
        if (unit.ammo.maximum <= 0) return { applied: false, ammoLost: 0, cookoff: false };
        ammoLost = Math.min(unit.ammo.current, Math.max(1, Math.round(unit.ammo.maximum * severity / 200)));
        unit.ammo.current = Math.max(0, unit.ammo.current - ammoLost);
        if (severity >= 85 && unit.ammo.current > 0) {
          cookoff = true;
          unit.ammoCookoff = true;
          unit.ammo.current = 0;
          unit.components.hull = Math.max(0, unit.components.hull - 28);
        }
      } else if (component === 'fuelSystem') {
        unit.components.fuelSystem = Math.max(0, unit.components.fuelSystem - severity);
        unit.fuel = Math.max(0, unit.fuel - Math.max(6, severity * 0.85));
      } else if (Object.hasOwn(unit.components, component)) {
        unit.components[component] = Math.max(0, unit.components[component] - severity);
      }
      unit.health = unit.components.hull;
      unit.destroyed = unit.components.hull <= 0 || unit.ammoCookoff;
      if (unit.components.engine <= 0 || unit.components.mobility <= 0 || unit.components.fuelSystem <= 0 || unit.destroyed) unit.goal = null;

      const side = unit.damageMarks.length % 2 === 0 ? 1 : -1;
      const halfWidth = unit.type === 'tank' ? 2.46 : unit.type === 'ifv' ? 2.2 : unit.type === 'truck' ? 1.16 : 1.3;
      const mark = new THREE.Mesh(new THREE.CircleGeometry(0.42 + Math.random() * 0.25, 12), new THREE.MeshBasicMaterial({ color: '#201e19', transparent: true, opacity: 0.76, side: THREE.DoubleSide, depthWrite: false }));
      mark.position.set(side * (halfWidth + 0.045), component === 'engine' ? 1.1 : 1.35, component === 'engine' ? -2.35 : -0.6 + Math.random() * 1.6);
      mark.rotation.y = side > 0 ? Math.PI / 2 : -Math.PI / 2;
      mark.renderOrder = 9;
      mark.name = `Scorch mark / ${component}`;
      unit.model.add(mark);
      unit.damageMarks.push(mark);
      return { applied: true, ammoLost, cookoff };
    },
    applyDamage(building, amount) {
      if (!building) return 0;
      const data = building.userData?.building || building;
      data.damage = clamp(data.damage + amount, 0, 100);
      const blend = data.damage / 100;
      data.bodyMaterial.color.copy(data.baseColor).lerp(new THREE.Color('#413e36'), blend * 0.82);
      data.roofMaterial.color.copy(data.baseRoofColor).lerp(new THREE.Color('#2f312d'), blend);
      data.soot.material.opacity = Math.min(0.76, blend * 0.84);
      if (data.damage >= 58) {
        data.roof.visible = false;
        data.rubble.visible = true;
        data.damageDetails.forEach((detail) => { detail.visible = false; });
      }
      if (data.damage >= 96) {
        data.body.visible = false;
        data.rubble.visible = true;
      }
      return data.damage;
    },
    resetDamage() {
      this.buildings.forEach((root) => {
        const data = root.userData.building;
        data.damage = 0;
        data.isBurning = false;
        data.body.visible = true;
        data.roof.visible = true;
        data.rubble.visible = false;
        data.damageDetails.forEach((detail) => { detail.visible = true; });
        data.soot.material.opacity = 0;
        data.bodyMaterial.color.copy(data.baseColor);
        data.roofMaterial.color.copy(data.baseRoofColor);
      });
    },
    resetUnits() {
      this.units.forEach((unit) => {
        unit.components = { hull: 100, engine: 100, mobility: 100, weapon: 100, fuelSystem: 100 };
        unit.health = 100;
        unit.ammo.current = unit.ammo.maximum;
        unit.fuel = 100;
        unit.ammoCookoff = false;
        unit.destroyed = false;
        unit.goal = null;
        unit.damageMarks.forEach((mark) => {
          unit.model.remove(mark);
          mark.geometry.dispose();
          mark.material.dispose();
        });
        unit.damageMarks.length = 0;
        unit.heading = unit.startHeading;
        unit.model.parent.position.set(unit.startX, terrainHeight(unit.startX, unit.startZ) - 0.1, unit.startZ);
        unit.model.parent.rotation.y = unit.startHeading;
        unit.turretPivot.rotation.y = 0;
        unit.wheels.forEach((wheel) => { wheel.rotation.x = 0; });
      });
    },
    update(delta, time) {
      controls.update();
      if (this.cameraMove) {
        const movement = this.cameraMove;
        movement.elapsed += delta;
        const progress = clamp(movement.elapsed / movement.duration, 0, 1);
        const eased = progress * progress * (3 - 2 * progress);
        controls.target.lerpVectors(movement.from, movement.to, eased);
        if (progress >= 1) this.cameraMove = null;
      }

      if (this.playing) {
        this.units.forEach((unit) => {
          const root = unit.model.parent;
          if (unit.goal) {
            const dx = unit.goal.x - root.position.x;
            const dz = unit.goal.z - root.position.z;
            const distance = Math.hypot(dx, dz);
            const targetHeading = Math.atan2(dx, dz);
            let angleDelta = ((targetHeading - unit.heading + Math.PI * 3) % (Math.PI * 2)) - Math.PI;
            unit.heading += angleDelta * Math.min(1, delta * 2.6);
            root.rotation.y = unit.heading;
            if (distance < 1.15) {
              unit.goal = null;
            } else {
              if (unit.destroyed || unit.fuel <= 0 || unit.components.engine <= 0 || unit.components.mobility <= 0) {
                unit.goal = null;
              } else {
                const engineFactor = 0.25 + 0.75 * unit.components.engine / 100;
                const mobilityFactor = 0.25 + 0.75 * unit.components.mobility / 100;
                const fuelFactor = 0.3 + 0.7 * unit.components.fuelSystem / 100;
                const step = Math.min(distance, unit.speed * engineFactor * mobilityFactor * fuelFactor * delta);
                root.position.x += dx / distance * step;
                root.position.z += dz / distance * step;
                root.position.y = terrainHeight(root.position.x, root.position.z) - 0.1;
                unit.fuel = Math.max(0, unit.fuel - step * (unit.type === 'squad' ? 0.001 : 0.018));
                unit.wheels.forEach((wheel) => { wheel.rotation.x += step * 0.85; });
              }
            }
          } else if (unit.turretPivot && unit.selected) {
            unit.turretPivot.rotation.y = Math.sin(time * 0.28 + unit.startX) * 0.12;
          }
        });
      }
      renderer.render(scene, camera);
    },
    dispose() {
      resizeObserver.disconnect();
      controls.dispose();
      renderer.dispose();
    },
  };

  return world;
}
