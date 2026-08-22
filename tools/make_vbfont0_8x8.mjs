import fs from "node:fs";
import path from "node:path";

const workspace = process.cwd();
const source = path.join(workspace, "original", "VBFONT0.VGA");
const outputDir = path.join(workspace, "outputs", "hangul_smoke_patch");
const output = path.join(outputDir, "VBFONT0.VGA");
const original = fs.readFileSync(source);

if (original.length !== 1040 || original[0] !== 6 || original[1] !== 6 || original[5] !== 128) {
  throw new Error("Unexpected VBFONT0.VGA layout");
}

const glyphCount = 128;
const tableSize = glyphCount * 2;
const headerSize = 16;
const oldBitmapOffset = headerSize + tableSize;
const newGlyphSize = 8;
const result = Buffer.alloc(headerSize + tableSize + glyphCount * newGlyphSize);
original.copy(result, 0, 0, oldBitmapOffset);

result[0] = 8;
result[1] = 8;
result[3] = 1;
result.writeUInt16LE(newGlyphSize, 10);
result.writeUInt16LE(result.length, 12);
result.writeUInt16LE(newGlyphSize, 14);

for (let glyph = 0; glyph < glyphCount; glyph++) {
  const oldBase = oldBitmapOffset + glyph * 6;
  const newBase = oldBitmapOffset + glyph * newGlyphSize;
  for (let y = 0; y < 6; y++) {
    // Move the original six high bits one pixel right and one pixel down.
    result[newBase + y + 1] = original[oldBase + y] >> 1;
  }
}

fs.mkdirSync(outputDir, { recursive: true });
fs.writeFileSync(output, result);
console.log(JSON.stringify({ output, width: 8, height: 8, glyphCount, size: result.length }, null, 2));
