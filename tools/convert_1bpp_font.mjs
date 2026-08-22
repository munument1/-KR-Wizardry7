import fs from "node:fs";
import path from "node:path";

function option(name, fallback = null) {
  const index = process.argv.indexOf(`--${name}`);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

const input = option("input");
const output = option("output");
const sourceWidth = Number(option("source-width"));
const sourceHeight = Number(option("source-height"));
const targetWidth = Number(option("target-width", "8"));
const targetHeight = Number(option("target-height", "8"));
const canvasWidth = Number(option("canvas-width", String(targetWidth)));
const canvasHeight = Number(option("canvas-height", String(targetHeight)));
const offsetX = Number(option("offset-x", "0"));
const offsetY = Number(option("offset-y", "0"));
const mode = option("mode", "majority");

if (!input || !output || !sourceWidth || !sourceHeight) {
  throw new Error("Required: --input --output --source-width --source-height");
}
if (canvasWidth > 8) throw new Error("This converter currently emits one byte per canvas row");
if (targetWidth + offsetX > canvasWidth || targetHeight + offsetY > canvasHeight) {
  throw new Error("Target glyph does not fit inside the requested canvas");
}
if (!["nearest", "majority", "crop"].includes(mode)) {
  throw new Error(`Unsupported mode: ${mode}`);
}

const source = fs.readFileSync(input);
const sourceRowBytes = Math.ceil(sourceWidth / 8);
const sourceGlyphBytes = sourceRowBytes * sourceHeight;
if (source.length % sourceGlyphBytes !== 0) {
  throw new Error(`Input size ${source.length} is not divisible by ${sourceGlyphBytes}`);
}

const glyphCount = source.length / sourceGlyphBytes;
const result = Buffer.alloc(glyphCount * canvasHeight);

function sourceBit(glyph, x, y) {
  const offset = glyph * sourceGlyphBytes + y * sourceRowBytes + Math.floor(x / 8);
  return (source[offset] & (0x80 >> (x & 7))) !== 0;
}

for (let glyph = 0; glyph < glyphCount; glyph++) {
  for (let targetY = 0; targetY < targetHeight; targetY++) {
    let row = 0;
    for (let targetX = 0; targetX < targetWidth; targetX++) {
      let on = false;
      if (mode === "crop") {
        const x = targetX + Math.floor((sourceWidth - targetWidth) / 2);
        const y = targetY + Math.floor((sourceHeight - targetHeight) / 2);
        on = sourceBit(glyph, x, y);
      } else if (mode === "nearest") {
        const x = Math.min(sourceWidth - 1, Math.floor((targetX + 0.5) * sourceWidth / targetWidth));
        const y = Math.min(sourceHeight - 1, Math.floor((targetY + 0.5) * sourceHeight / targetHeight));
        on = sourceBit(glyph, x, y);
      } else {
        const x0 = Math.floor(targetX * sourceWidth / targetWidth);
        const x1 = Math.ceil((targetX + 1) * sourceWidth / targetWidth);
        const y0 = Math.floor(targetY * sourceHeight / targetHeight);
        const y1 = Math.ceil((targetY + 1) * sourceHeight / targetHeight);
        let active = 0;
        let total = 0;
        for (let y = y0; y < y1; y++) {
          for (let x = x0; x < x1; x++) {
            active += sourceBit(glyph, x, y) ? 1 : 0;
            total++;
          }
        }
        on = active * 2 >= total;
      }
      if (on) row |= 0x80 >> targetX;
    }
    result[glyph * canvasHeight + targetY + offsetY] |= row >> offsetX;
  }
}

fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, result);
console.log(JSON.stringify({ input, output, mode, glyphCount, sourceWidth, sourceHeight, targetWidth, targetHeight, canvasWidth, canvasHeight, offsetX, offsetY }, null, 2));
