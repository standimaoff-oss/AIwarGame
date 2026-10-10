import { copyFile, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const outputDir = path.join(root, 'dist');
const templatePath = path.join(outputDir, 'index.html');
let html = await readFile(templatePath, 'utf8');

const stylesheetTag = html.match(/<link\b[^>]*rel="stylesheet"[^>]*>/i)?.[0];
const entryScriptTag = html.match(/<script\b[^>]*type="module"[^>]*src="[^"]+"[^>]*>\s*<\/script>/i)?.[0]
  || html.match(/<script\b[^>]*src="[^"]+"[^>]*type="module"[^>]*>\s*<\/script>/i)?.[0];
if (!stylesheetTag || !entryScriptTag) {
  throw new Error('Could not locate the built stylesheet or module entry in dist/index.html');
}

const cssPath = stylesheetTag.match(/href="([^"]+)"/i)?.[1];
const jsPath = entryScriptTag.match(/src="([^"]+)"/i)?.[1];
if (!cssPath || !jsPath) throw new Error('Could not resolve built asset paths.');

const toAssetPath = (assetPath) => path.join(outputDir, assetPath.replace(/^\//, ''));
const [css, javascript] = await Promise.all([
  readFile(toAssetPath(cssPath), 'utf8'),
  readFile(toAssetPath(jsPath), 'utf8'),
]);

html = html.replace(stylesheetTag, () => `<style>\n${css.replace(/<\/style/gi, '<\\/style')}\n</style>`);
html = html.replace(/<link\b[^>]*rel="modulepreload"[^>]*>/gi, '');
html = html.replace(entryScriptTag, () => `<script type="module">\n${javascript.replace(/<\/script/gi, '<\\/script')}\n</script>`);
html = html.replace(/\s+crossorigin(?:="[^"]*")?/gi, '');

const remainingRuntimeReferences = [...html.matchAll(/<(script|link)\b[^>]*\b(src|href)=["']([^"']+)["'][^>]*>/gi)]
  .map(([, tagName, attributeName, url]) => ({ tagName, attributeName, url }))
  .filter(({ url }) => !/^(?:data:|blob:|#)/i.test(url));
if (remainingRuntimeReferences.length) {
  throw new Error(`Standalone HTML still references external runtime assets: ${JSON.stringify(remainingRuntimeReferences)}`);
}
if ((html.match(/<script\b/gi) || []).length !== 1 || (html.match(/<style\b/gi) || []).length !== 1) {
  throw new Error('Standalone HTML must contain exactly one inline script and one inline stylesheet.');
}

const singleFilePath = path.join(root, 'AI_WAR_GAME.html');
await writeFile(singleFilePath, html, 'utf8');
await copyFile(singleFilePath, path.join(outputDir, 'AI_WAR_GAME.html'));
const size = (Buffer.byteLength(html) / 1024).toFixed(0);
console.log(`Standalone game written: AI_WAR_GAME.html (${size} KB, no external runtime assets)`);
