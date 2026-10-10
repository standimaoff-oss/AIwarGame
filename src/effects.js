import * as THREE from 'three';
import { terrainHeight } from './engine.js';

const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const randomBetween = (min, max) => min + Math.random() * (max - min);

function makeTexture(kind) {
  const canvas = document.createElement('canvas');
  canvas.width = 128;
  canvas.height = 128;
  const context = canvas.getContext('2d');
  context.clearRect(0, 0, 128, 128);

  if (kind === 'smoke' || kind === 'dust') {
    const shift = kind === 'dust' ? 5 : 0;
    const clouds = [
      [62, 67, 56, 0.46], [42, 74, 34, 0.23], [82, 76, 39, 0.25], [64, 42, 34, 0.29],
      [45, 45, 22, 0.12], [79, 49, 28, 0.15],
    ];
    clouds.forEach(([x, y, radius, strength], index) => {
      const gradient = context.createRadialGradient(x, y, radius * 0.08, x, y, radius);
      const alpha = strength * (kind === 'dust' ? 0.95 : 1);
      gradient.addColorStop(0, `rgba(${171 + shift}, ${178 + shift}, ${167 + shift}, ${alpha})`);
      gradient.addColorStop(0.48, `rgba(${113 + shift}, ${124 + shift}, ${116 + shift}, ${alpha * 0.78})`);
      gradient.addColorStop(1, `rgba(${84 + shift}, ${94 + shift}, ${88 + shift}, 0)`);
      context.fillStyle = gradient;
      context.beginPath();
      context.arc(x + (index % 2 ? 3 : -2), y, radius, 0, Math.PI * 2);
      context.fill();
    });
  } else if (kind === 'flame') {
    const gradient = context.createRadialGradient(64, 77, 2, 64, 69, 61);
    gradient.addColorStop(0, 'rgba(255, 246, 209, 1)');
    gradient.addColorStop(0.18, 'rgba(255, 218, 111, .97)');
    gradient.addColorStop(0.42, 'rgba(255, 139, 43, .88)');
    gradient.addColorStop(0.7, 'rgba(211, 65, 25, .54)');
    gradient.addColorStop(1, 'rgba(95, 28, 18, 0)');
    context.fillStyle = gradient;
    context.beginPath();
    context.ellipse(64, 68, 39, 59, 0, 0, Math.PI * 2);
    context.fill();
    context.globalCompositeOperation = 'destination-out';
    const core = context.createLinearGradient(0, 20, 0, 118);
    core.addColorStop(0, 'rgba(0,0,0,0)');
    core.addColorStop(0.28, 'rgba(0,0,0,.04)');
    core.addColorStop(0.76, 'rgba(0,0,0,.28)');
    core.addColorStop(1, 'rgba(0,0,0,.76)');
    context.fillStyle = core;
    context.fillRect(0, 0, 128, 128);
    context.globalCompositeOperation = 'source-over';
  } else if (kind === 'spark') {
    const gradient = context.createRadialGradient(64, 64, 1, 64, 64, 63);
    gradient.addColorStop(0, 'rgba(255, 251, 222, 1)');
    gradient.addColorStop(0.16, 'rgba(255, 204, 96, .97)');
    gradient.addColorStop(0.42, 'rgba(250, 108, 35, .58)');
    gradient.addColorStop(1, 'rgba(235, 77, 28, 0)');
    context.fillStyle = gradient;
    context.fillRect(0, 0, 128, 128);
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  return texture;
}

export class EffectsSystem {
  constructor(world) {
    this.world = world;
    this.scene = world.scene;
    this.root = new THREE.Group();
    this.root.name = 'Procedural VFX / smoke / fire / impacts';
    this.scene.add(this.root);
    this.textures = {
      smoke: makeTexture('smoke'),
      dust: makeTexture('dust'),
      flame: makeTexture('flame'),
      spark: makeTexture('spark'),
    };
    this.particles = [];
    this.rings = [];
    this.tracers = [];
    this.emitters = new Map();
    this.vehicleEmitters = new Map();
    this.maxParticles = 340;
    this.smokeEnabled = true;
    this.fireEnabled = true;
    this.windSpeed = 12;
    this.time = 0;
  }

  createMaterial(kind, color, opacity = 1) {
    const map = kind === 'flame' || kind === 'flash' ? this.textures.flame
      : kind === 'spark' ? this.textures.spark
        : kind === 'dust' ? this.textures.dust : this.textures.smoke;
    return new THREE.SpriteMaterial({
      map,
      color: color || '#ffffff',
      transparent: true,
      opacity,
      depthWrite: false,
      blending: kind === 'spark' || kind === 'flash' ? THREE.AdditiveBlending : THREE.NormalBlending,
      toneMapped: kind !== 'spark' && kind !== 'flash',
    });
  }

  spawn(kind, position, options = {}) {
    if (this.particles.length >= this.maxParticles) this.removeParticle(0);
    const sprite = new THREE.Sprite(this.createMaterial(kind, options.color, options.opacity ?? 0.92));
    sprite.position.copy(position);
    const scale = options.scale ?? 1;
    sprite.scale.set(scale, scale, 1);
    sprite.rotation = options.rotation ?? randomBetween(-Math.PI, Math.PI);
    sprite.renderOrder = kind === 'smoke' || kind === 'dust' ? 11 : 13;
    this.root.add(sprite);
    this.particles.push({
      sprite,
      kind,
      velocity: options.velocity?.clone?.() || new THREE.Vector3(...(options.velocity || [0, 1, 0])),
      life: options.life ?? 1.5,
      age: 0,
      startScale: scale,
      endScale: options.endScale ?? scale * 1.8,
      opacity: options.opacity ?? 0.92,
      gravity: options.gravity ?? (kind === 'spark' ? 5.4 : kind === 'smoke' || kind === 'dust' ? -0.28 : -1.8),
      windFactor: options.windFactor ?? (kind === 'smoke' ? 0.58 : kind === 'dust' ? 0.28 : 0.08),
      color: options.color || '#ffffff',
      rotationSpeed: options.rotationSpeed ?? randomBetween(-0.3, 0.3),
      fadePower: options.fadePower ?? 1.2,
    });
    return sprite;
  }

  removeParticle(index) {
    const particle = this.particles[index];
    if (!particle) return;
    this.root.remove(particle.sprite);
    particle.sprite.material.dispose();
    this.particles.splice(index, 1);
  }

  spawnSmoke(position, count = 1, tint = '#858b83', size = 2.4) {
    if (!this.smokeEnabled) return;
    for (let i = 0; i < count; i += 1) {
      this.spawn('smoke', new THREE.Vector3(
        position.x + randomBetween(-0.9, 0.9),
        position.y + randomBetween(-0.5, 0.8),
        position.z + randomBetween(-0.9, 0.9),
      ), {
        color: tint,
        scale: size * randomBetween(0.65, 1.18),
        endScale: size * randomBetween(2.3, 3.5),
        life: randomBetween(2.8, 4.8),
        opacity: randomBetween(0.32, 0.54),
        velocity: [randomBetween(-0.65, 0.65), randomBetween(1.3, 2.25), randomBetween(-0.55, 0.55)],
        gravity: -0.15,
        windFactor: 0.9,
      });
    }
  }

  spawnFlame(position, count = 1, scale = 2.1) {
    if (!this.fireEnabled) return;
    for (let i = 0; i < count; i += 1) {
      this.spawn('flame', new THREE.Vector3(
        position.x + randomBetween(-1.3, 1.3),
        position.y + randomBetween(-0.7, 0.9),
        position.z + randomBetween(-1.2, 1.2),
      ), {
        color: i % 3 === 0 ? '#fff2cd' : i % 2 === 0 ? '#ffbd5f' : '#ff7c31',
        scale: scale * randomBetween(0.52, 1.1),
        endScale: scale * randomBetween(0.12, 0.4),
        life: randomBetween(0.46, 0.98),
        opacity: randomBetween(0.74, 1),
        velocity: [randomBetween(-0.55, 0.55), randomBetween(2.0, 4.2), randomBetween(-0.48, 0.48)],
        gravity: -1.25,
        windFactor: 0.16,
      });
    }
  }

  spawnSparks(position, count = 10) {
    for (let i = 0; i < count; i += 1) {
      const angle = Math.random() * Math.PI * 2;
      const speed = randomBetween(2.4, 8.5);
      this.spawn('spark', new THREE.Vector3(position.x, position.y + randomBetween(0.4, 1.4), position.z), {
        color: i % 2 ? '#ffc56f' : '#ff8944',
        scale: randomBetween(0.36, 0.88),
        endScale: randomBetween(0.04, 0.16),
        life: randomBetween(0.35, 0.95),
        opacity: randomBetween(0.65, 0.96),
        velocity: [Math.cos(angle) * speed, randomBetween(2.5, 8), Math.sin(angle) * speed],
        gravity: 8.5,
        windFactor: 0.12,
      });
    }
  }

  addShockwave(position, maximum = 11) {
    const geometry = new THREE.RingGeometry(0.85, 1.18, 56);
    const material = new THREE.MeshBasicMaterial({ color: '#ffc176', transparent: true, opacity: 0.72, side: THREE.DoubleSide, depthWrite: false, toneMapped: false });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.set(position.x, terrainHeight(position.x, position.z) + 0.28, position.z);
    mesh.scale.setScalar(0.2);
    mesh.renderOrder = 12;
    this.root.add(mesh);
    this.rings.push({ mesh, age: 0, life: 0.92, maximum });
  }

  startFire(buildingRoot) {
    if (!buildingRoot) return;
    const data = buildingRoot.userData?.building;
    if (!data) return;
    data.isBurning = true;
    if (this.emitters.has(data.id)) return;
    const worldY = buildingRoot.position.y + data.height;
    const light = new THREE.PointLight('#ff772f', 1.6, 21, 1.9);
    light.position.set(data.x, worldY + 0.7, data.z);
    light.castShadow = false;
    this.scene.add(light);
    this.emitters.set(data.id, {
      id: data.id,
      building: buildingRoot,
      anchor: new THREE.Vector3(data.x, worldY + 0.6, data.z),
      elapsedFire: randomBetween(0, 0.2),
      elapsedSmoke: randomBetween(0, 0.8),
      light,
      lightPhase: randomBetween(0, Math.PI * 2),
    });
  }

  stopFire(buildingRoot) {
    if (!buildingRoot) return;
    const data = buildingRoot.userData?.building;
    if (data) data.isBurning = false;
    const id = data?.id;
    const emitter = this.emitters.get(id);
    if (!emitter) return;
    this.scene.remove(emitter.light);
    emitter.light.dispose?.();
    this.emitters.delete(id);
  }

  startVehicleSmoke(unit, burning = false) {
    if (!unit) return;
    const existing = this.vehicleEmitters.get(unit.id);
    if (existing) {
      existing.burning ||= burning;
      return;
    }
    const light = new THREE.PointLight('#ff6d2f', burning ? 1.6 : 0.15, burning ? 15 : 7, 2);
    light.castShadow = false;
    this.scene.add(light);
    const localOffset = unit.type === 'tank' || unit.type === 'ifv'
      ? new THREE.Vector3(0, 1.8, -2.9)
      : new THREE.Vector3(0, 1.6, -1.8);
    this.vehicleEmitters.set(unit.id, { unit, localOffset, light, burning, fireTimer: 0, smokeTimer: 0, phase: randomBetween(0, 7) });
  }

  vehicleHit(unit, component, intensity = 42) {
    if (!unit) return;
    const root = unit.model.parent;
    const local = component === 'engine'
      ? new THREE.Vector3(0, 1.6, -2.7)
      : component === 'ammo' ? new THREE.Vector3(0, 2.8, -0.7) : new THREE.Vector3(0, 1.4, 0.8);
    const point = root.localToWorld(local);
    this.spawn('flash', point, { color: '#ffe0a0', scale: 2.2, endScale: 5.8, life: 0.27, opacity: 0.8, velocity: [0, 0.3, 0], gravity: 0, windFactor: 0 });
    this.spawnSparks(point, Math.max(3, Math.round(intensity / 8)));
    this.spawnSmoke(point, 3, '#5e625d', 1.1);
    if (component === 'engine' || component === 'hull' || (component === 'fuelSystem' && unit.components.fuelSystem < 55)) this.startVehicleSmoke(unit, false);
    if (unit.ammoCookoff) {
      this.startVehicleSmoke(unit, true);
      this.spawnFlame(point, 14, 3.2);
      this.spawnSparks(point, 24);
    }
  }

  fireTestShot(unit) {
    if (!unit) return null;
    const root = unit.model.parent;
    const muzzleLocal = unit.type === 'tank'
      ? new THREE.Vector3(0, 2.37, 4.95)
      : unit.type === 'ifv' ? new THREE.Vector3(0, 2.38, 3.45)
        : unit.type === 'squad' ? new THREE.Vector3(0.2, 1.15, 3.15) : new THREE.Vector3(0, 1.8, 3.2);
    const start = root.localToWorld(muzzleLocal);
    const end = this.world.targetBuilding
      ? new THREE.Vector3(this.world.targetBuilding.userData.building.x, this.world.targetBuilding.position.y + this.world.targetBuilding.userData.building.height * 0.58, this.world.targetBuilding.userData.building.z)
      : new THREE.Vector3(start.x + 15, start.y, start.z + 20);
    const geometry = new THREE.BufferGeometry().setFromPoints([start.clone(), end.clone()]);
    const material = new THREE.LineBasicMaterial({ color: '#ffe7a3', transparent: true, opacity: 0.92, depthTest: false, toneMapped: false });
    const tracer = new THREE.Line(geometry, material);
    tracer.renderOrder = 17;
    this.scene.add(tracer);
    this.tracers.push({ line: tracer, age: 0, life: 0.22 });
    this.spawnFlame(start, 2, 1.05);
    this.spawnSparks(start, 3);
    return end;
  }

  impact(position, buildingRoot, intensity = 42, allowFire = true) {
    const groundY = terrainHeight(position.x, position.z);
    const buildingData = buildingRoot?.userData?.building;
    const hitY = buildingData ? buildingRoot.position.y + buildingData.height * 0.62 : groundY + 0.8;
    const point = new THREE.Vector3(position.x, hitY, position.z);
    const severity = clamp(intensity / 100, 0.1, 1);

    this.spawn('flash', new THREE.Vector3(position.x, hitY + 1.6, position.z), {
      color: '#fff1c6', scale: 4 + severity * 9, endScale: 17 + severity * 14,
      life: 0.46, opacity: 0.92, velocity: [0, 1.2, 0], gravity: 0.1, windFactor: 0,
    });
    this.addShockwave(position, 8 + severity * 9);
    for (let i = 0; i < 19 + Math.round(severity * 14); i += 1) {
      const angle = Math.random() * Math.PI * 2;
      const speed = randomBetween(1.5, 7 + severity * 5);
      this.spawn('dust', new THREE.Vector3(position.x, groundY + 0.6, position.z), {
        color: i % 2 ? '#998d70' : '#727264',
        scale: randomBetween(1.3, 2.6) * (0.65 + severity * 0.5),
        endScale: randomBetween(4.5, 7.5),
        life: randomBetween(1.7, 3.0),
        opacity: randomBetween(0.4, 0.68),
        velocity: [Math.cos(angle) * speed, randomBetween(1.2, 5), Math.sin(angle) * speed],
        gravity: -0.05,
        windFactor: 0.28,
      });
    }
    this.spawnSparks(point, Math.round(9 + severity * 24));
    this.spawnFlame(point, Math.round(7 + severity * 8), 2.8 + severity * 2.1);

    if (buildingRoot) {
      const data = buildingRoot.userData.building;
      const anchor = new THREE.Vector3(data.x, buildingRoot.position.y + data.height + 0.6, data.z);
      for (let i = 0; i < 10; i += 1) {
        this.spawn('dust', new THREE.Vector3(anchor.x + randomBetween(-3, 3), anchor.y + randomBetween(-1, 1), anchor.z + randomBetween(-2, 2)), {
          color: i % 2 ? '#5f625b' : '#877c68', scale: randomBetween(1.4, 2.6), endScale: randomBetween(4.8, 7.4),
          life: randomBetween(2.0, 3.8), opacity: randomBetween(0.38, 0.58), velocity: [randomBetween(-1.8, 1.8), randomBetween(0.9, 2.2), randomBetween(-1.4, 1.4)], gravity: -0.18, windFactor: 0.65,
        });
      }
      if (allowFire && data.damage > 5) this.startFire(buildingRoot);
    }
  }

  reset() {
    for (const emitter of this.emitters.values()) {
      this.scene.remove(emitter.light);
      emitter.light.dispose?.();
    }
    this.emitters.clear();
    for (const emitter of this.vehicleEmitters.values()) {
      this.scene.remove(emitter.light);
      emitter.light.dispose?.();
    }
    this.vehicleEmitters.clear();
    this.tracers.forEach(({ line }) => {
      this.scene.remove(line);
      line.geometry.dispose();
      line.material.dispose();
    });
    this.tracers.length = 0;
    while (this.particles.length) this.removeParticle(this.particles.length - 1);
    this.rings.forEach(({ mesh }) => {
      this.root.remove(mesh);
      mesh.geometry.dispose();
      mesh.material.dispose();
    });
    this.rings.length = 0;
    this.time = 0;
  }

  update(delta) {
    this.time += delta;
    const wind = this.windSpeed / 12;
    this.emitters.forEach((emitter) => {
      emitter.elapsedFire += delta;
      emitter.elapsedSmoke += delta;
      const data = emitter.building.userData.building;
      const fireHeight = data.damage >= 96 ? 2.2 : data.damage >= 58 ? data.height * 0.55 : data.height;
      emitter.anchor.set(data.x, emitter.building.position.y + fireHeight + 0.6, data.z);
      emitter.light.position.copy(emitter.anchor);
      const anchor = emitter.anchor;
      if (this.fireEnabled && emitter.elapsedFire > 0.075) {
        emitter.elapsedFire = 0;
        const firePosition = new THREE.Vector3(anchor.x + randomBetween(-data.width * 0.16, data.width * 0.16), anchor.y - randomBetween(0.4, 1.1), anchor.z + randomBetween(-data.depth * 0.16, data.depth * 0.16));
        this.spawnFlame(firePosition, Math.random() > 0.6 ? 2 : 1, 2.1 + data.damage * 0.019);
        if (Math.random() > 0.74) this.spawnSparks(firePosition, 2);
      }
      if (this.smokeEnabled && emitter.elapsedSmoke > 0.27) {
        emitter.elapsedSmoke = 0;
        const data = emitter.building.userData.building;
        const smokePosition = new THREE.Vector3(anchor.x + randomBetween(-data.width * 0.11, data.width * 0.11), anchor.y + randomBetween(0.1, 1.3), anchor.z + randomBetween(-data.depth * 0.1, data.depth * 0.1));
        this.spawnSmoke(smokePosition, 1, data.damage > 70 ? '#5f625f' : '#858880', 2.5 + data.damage * 0.012);
      }
      emitter.lightPhase += delta * 7.2;
      emitter.light.intensity = this.fireEnabled ? 1.2 + Math.sin(emitter.lightPhase) * 0.35 + Math.random() * 0.2 : 0.06;
      emitter.light.visible = this.fireEnabled;
    });

    this.vehicleEmitters.forEach((emitter) => {
      const unit = emitter.unit;
      const root = unit.model.parent;
      root.updateWorldMatrix(true, false);
      const exhaust = root.localToWorld(emitter.localOffset.clone());
      emitter.fireTimer += delta;
      emitter.smokeTimer += delta;
      if (this.smokeEnabled && emitter.smokeTimer > 0.34) {
        emitter.smokeTimer = 0;
        this.spawnSmoke(exhaust, emitter.burning ? 2 : 1, emitter.burning ? '#565a56' : '#727873', emitter.burning ? 1.9 : 1.1);
      }
      if (emitter.burning && this.fireEnabled && emitter.fireTimer > 0.17) {
        emitter.fireTimer = 0;
        this.spawnFlame(exhaust, 1, 1.35);
      }
      emitter.phase += delta * 5;
      emitter.light.position.copy(exhaust);
      emitter.light.intensity = emitter.burning && this.fireEnabled ? 1.1 + Math.sin(emitter.phase) * 0.3 : 0.07;
      emitter.light.visible = emitter.burning && this.fireEnabled;
    });

    for (let i = this.tracers.length - 1; i >= 0; i -= 1) {
      const tracer = this.tracers[i];
      tracer.age += delta;
      tracer.line.material.opacity = Math.max(0, 0.92 * (1 - tracer.age / tracer.life));
      if (tracer.age >= tracer.life) {
        this.scene.remove(tracer.line);
        tracer.line.geometry.dispose();
        tracer.line.material.dispose();
        this.tracers.splice(i, 1);
      }
    }

    for (let i = this.particles.length - 1; i >= 0; i -= 1) {
      const particle = this.particles[i];
      particle.age += delta;
      if (particle.age >= particle.life) {
        this.removeParticle(i);
        continue;
      }
      const progress = particle.age / particle.life;
      particle.velocity.y -= particle.gravity * delta;
      particle.velocity.x += wind * particle.windFactor * delta * 0.46;
      particle.sprite.position.addScaledVector(particle.velocity, delta);
      const scale = THREE.MathUtils.lerp(particle.startScale, particle.endScale, Math.pow(progress, 0.84));
      particle.sprite.scale.set(scale, scale, 1);
      particle.sprite.material.opacity = particle.opacity * Math.pow(Math.max(0, 1 - progress), particle.fadePower);
      particle.sprite.rotation += particle.rotationSpeed * delta;
      if (particle.kind === 'smoke') {
        const lift = 0.08 + progress * 0.14;
        particle.sprite.material.color.setRGB(0.82 + lift, 0.84 + lift, 0.82 + lift);
      }
    }

    for (let i = this.rings.length - 1; i >= 0; i -= 1) {
      const ring = this.rings[i];
      ring.age += delta;
      const progress = clamp(ring.age / ring.life, 0, 1);
      ring.mesh.scale.setScalar(0.3 + progress * ring.maximum);
      ring.mesh.material.opacity = (1 - progress) * 0.74;
      if (progress >= 1) {
        this.root.remove(ring.mesh);
        ring.mesh.geometry.dispose();
        ring.mesh.material.dispose();
        this.rings.splice(i, 1);
      }
    }
  }

  dispose() {
    this.reset();
    this.scene.remove(this.root);
    Object.values(this.textures).forEach((texture) => texture.dispose());
  }
}
