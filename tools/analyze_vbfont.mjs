import fs from "node:fs";
import path from "node:path";
import sharp from "sharp";

const root = process.cwd();
const input = process.argv[2] ?? path.join(root, "original", "VBFONT2.VGA");
const output = process.argv[3] ?? path.join(root, "outputs", "font_analysis", `${path.basename(input)}.png`);
const data = fs.readFileSync(input);

const width = data[0];
const height = data[1];
const bytesPerRow = data[3];
const planes = data[4];
const glyphCount = data[5];
const bytesPerPlaneGlyph = data.readUInt16LE(10);
const declaredSize = data.readUInt16LE(12);
const lineHeight = data.readUInt16LE(14);
const tableOffset = 16;
const bitmapOffset = tableOffset + glyphCount * 2;
const bytesPerGlyph = bytesPerPlaneGlyph * planes;

if (bitmapOffset + glyphCount * bytesPerGlyph !== data.length) {
  throw new Error(`Unexpected layout: calculated ${bitmapOffset + glyphCount * bytesPerGlyph}, actual ${data.length}`);
}

const columns = 16;
const scale = 3;
const cellWidth = width + 2;
const cellHeight = height + 2;
const rows = Math.ceil(glyphCount / columns);
const rgba = Buffer.alloc(columns * cellWidth * rows * cellHeight * 4, 255);
const palette = [255, 176, 88, 0];

for (let glyph = 0; glyph < glyphCount; glyph++) {
  const gx = (glyph % columns) * cellWidth + 1;
  const gy = Math.floor(glyph / columns) * cellHeight + 1;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let value = 0;
      for (let plane = 0; plane < planes; plane++) {
        const glyphBase = bitmapOffset + plane * glyphCount * bytesPerPlaneGlyph + glyph * bytesPerPlaneGlyph;
        const byte = data[glyphBase + y * bytesPerRow + Math.floor(x / 8)];
        value |= ((byte >> (7 - (x % 8))) & 1) << plane;
      }
      const c = palette[value] ?? 0;
      const idx = ((gy + y) * columns * cellWidth + gx + x) * 4;
      rgba[idx] = rgba[idx + 1] = rgba[idx + 2] = c;
    }
  }
}

fs.mkdirSync(path.dirname(output), { recursive: true });
await sharp(rgba, { raw: { width: columns * cellWidth, height: rows * cellHeight, channels: 4 } })
  .resize({ width: columns * cellWidth * scale, height: rows * cellHeight * scale, kernel: "nearest" })
  .png()
  .toFile(output);

console.log(JSON.stringify({
  input,
  output,
  width,
  height,
  bytesPerRow,
  planes,
  glyphCount,
  bytesPerPlaneGlyph,
  bytesPerGlyph,
  declaredSize,
  lineHeight,
  bitmapOffset,
  actualSize: data.length,
}, null, 2));
