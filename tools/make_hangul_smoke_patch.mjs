import fs from "node:fs";
import path from "node:path";

const workspace = process.cwd();
const source = path.join(workspace, "original", "MSG.GLD");
const outputDir = path.join(workspace, "outputs", "hangul_smoke_patch");
const output = path.join(outputDir, "MSG.GLD");
const data = fs.readFileSync(source);

const expected = Buffer.from([0x05, 0x48, 0x55, 0x4D, 0x41, 0x4E]);
if (!data.subarray(0, expected.length).equals(expected)) {
  throw new Error("MSG.GLD does not start with the expected HUMAN record");
}

// Galmuri7 KS X 1001 glyph map: '한' = index 2210.
// Encoding: lead 0x80 + floor(index/96), trail 0xA0 + index%96.
const glyphIndex = 2210;
const lead = 0x80 + Math.floor(glyphIndex / 96);
const trail = 0xA0 + (glyphIndex % 96);
data.set([lead, trail, 0x20, 0x20, 0x20], 1);

// Also replace the main-menu CREATE label (record at absolute offset 3118)
// so the 8x8 VBFONT0 test can be verified without navigating character creation.
const createRecordOffset = 3118;
const createExpected = Buffer.from([0x06, 0x43, 0x52, 0x45, 0x41, 0x54, 0x45]);
if (!data.subarray(createRecordOffset, createRecordOffset + createExpected.length).equals(createExpected)) {
  throw new Error("MSG.GLD does not contain the expected CREATE record");
}
data.set([lead, trail, 0x20, 0x20, 0x20, 0x20], createRecordOffset + 1);

fs.mkdirSync(outputDir, { recursive: true });
fs.writeFileSync(output, data);
console.log(JSON.stringify({ output, glyph: "한", glyphIndex, bytes: [lead, trail], recordLength: data[0] }, null, 2));
