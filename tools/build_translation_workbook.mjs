import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = path.resolve(".");
const outputDir = path.join(root, "outputs", "wizardry7_translation");
await fs.mkdir(outputDir, { recursive: true });

const messagesCsv = (await fs.readFile(path.join(root, "extracted", "msg", "messages_for_translation.csv"), "utf8")).replace(/^\uFEFF/, "");
const scenarioCsv = (await fs.readFile(path.join(root, "extracted", "scenario", "scenario_strings_for_translation.csv"), "utf8")).replace(/^\uFEFF/, "");
const promptText = await fs.readFile(path.join(root, "translation_prompt.md"), "utf8");

const messagesImport = await Workbook.fromCSV(messagesCsv, { sheetName: "Messages" });
const scenarioImport = await Workbook.fromCSV(scenarioCsv, { sheetName: "Scenario" });
const messagesValues = messagesImport.worksheets.getItem("Messages").getUsedRange(true).values;
const scenarioValues = scenarioImport.worksheets.getItem("Scenario").getUsedRange(true).values;

const workbook = Workbook.create();
const instructions = workbook.worksheets.add("Instructions");
const messages = workbook.worksheets.add("Messages");
const scenario = workbook.worksheets.add("Scenario");
messages.getRangeByIndexes(0, 0, messagesValues.length, messagesValues[0].length).values = messagesValues;
scenario.getRangeByIndexes(0, 0, scenarioValues.length, scenarioValues[0].length).values = scenarioValues;
const glossary = workbook.worksheets.add("Glossary");

const headerStyle = {
  fill: "#E5E7EB",
  font: { bold: true, color: "#111827" },
  borders: { preset: "outside", style: "thin", color: "#BFC5CC" },
  verticalAlignment: "center",
};

instructions.showGridLines = false;
instructions.getRange("A1:B1").merge();
instructions.getRange("A1").values = [["Wizardry 7 Gold 한국어 번역 작업"]];
instructions.getRange("A1:B1").format = {
  fill: "#E5E7EB",
  font: { bold: true, color: "#111827", size: 16 },
  rowHeightPx: 34,
  verticalAlignment: "center",
};
instructions.getRange("A3:B8").values = [
  ["항목", "값"],
  ["Messages 원문 행", null],
  ["Messages 번역 완료", null],
  ["Scenario 원문 행", null],
  ["Scenario 번역 완료", null],
  ["주의", "번역 열만 편집하고 <0xNN> 및 특수기호를 보존하세요."],
];
instructions.getRange("B4").formulas = [["=COUNTIF('Messages'!$G$2:$G$11019,\"<>\")"]];
instructions.getRange("B5").formulas = [["=COUNTIF('Messages'!$H$2:$H$11019,\"<>\")"]];
instructions.getRange("B6").formulas = [["=COUNTIF('Scenario'!$F$2:$F$1601,\"<>\")"]];
instructions.getRange("B7").formulas = [["=COUNTIF('Scenario'!$G$2:$G$1601,\"<>\")"]];
instructions.getRange("A3:B3").format = headerStyle;
instructions.getRange("A3:A8").format.font = { bold: true };
instructions.getRange("A10:B10").merge();
instructions.getRange("A10").values = [["웹 ChatGPT 작업 프롬프트"]];
instructions.getRange("A10:B10").format = headerStyle;
const promptLines = promptText.split(/\r?\n/).filter((line) => line.trim().length > 0);
instructions.getRangeByIndexes(10, 0, promptLines.length, 2).values = promptLines.map((line) => [line, null]);
instructions.getRangeByIndexes(10, 0, promptLines.length, 2).format = { wrapText: true, verticalAlignment: "top" };
instructions.getRange(`A1:A${promptLines.length + 10}`).format.columnWidthPx = 210;
instructions.getRange(`B1:B${promptLines.length + 10}`).format.columnWidthPx = 690;
instructions.freezePanes.freezeRows(1);

messages.freezePanes.freezeRows(1);
messages.getRange("A1:I1").format = headerStyle;
messages.getRange("A2:F11019").format = { verticalAlignment: "top" };
messages.getRange("G2:I11019").format = { wrapText: true, verticalAlignment: "top" };
messages.getRange("A1:A11019").format.columnWidthPx = 90;
messages.getRange("B1:B11019").format.columnWidthPx = 90;
messages.getRange("C1:C11019").format.columnWidthPx = 70;
messages.getRange("D1:D11019").format.columnWidthPx = 95;
messages.getRange("E1:E11019").format.columnWidthPx = 115;
messages.getRange("F1:F11019").format.columnWidthPx = 95;
messages.getRange("G1:G11019").format.columnWidthPx = 420;
messages.getRange("H1:H11019").format.columnWidthPx = 420;
messages.getRange("I1:I11019").format.columnWidthPx = 240;

scenario.freezePanes.freezeRows(1);
scenario.getRange("A1:H1").format = headerStyle;
scenario.getRange("A2:E1601").format = { verticalAlignment: "top" };
scenario.getRange("F2:H1601").format = { wrapText: true, verticalAlignment: "top" };
scenario.getRange("A1:A1601").format.columnWidthPx = 90;
scenario.getRange("B1:B1601").format.columnWidthPx = 100;
scenario.getRange("C1:C1601").format.columnWidthPx = 135;
scenario.getRange("D1:D1601").format.columnWidthPx = 125;
scenario.getRange("E1:E1601").format.columnWidthPx = 75;
scenario.getRange("F1:F1601").format.columnWidthPx = 300;
scenario.getRange("G1:G1601").format.columnWidthPx = 300;
scenario.getRange("H1:H1601").format.columnWidthPx = 240;

const glossaryRows = [
  ["source_term", "korean_term", "category", "notes"],
  ["HUMAN", "인간", "race", ""],
  ["ELF", "엘프", "race", ""],
  ["DWARF", "드워프", "race", ""],
  ["GNOME", "노움", "race", ""],
  ["HOBBIT", "호빗", "race", ""],
  ["FAERIE", "페어리", "race", ""],
  ["LIZARDMAN", "리저드맨", "race", ""],
  ["DRACON", "드라콘", "race", ""],
  ["FELPURR", "펠퍼", "race", ""],
  ["RAWULF", "라울프", "race", ""],
  ["MOOK", "무크", "race", ""],
  ["FIGHTER", "전사", "class", ""],
  ["MAGE", "마법사", "class", ""],
  ["PRIEST", "사제", "class", ""],
  ["THIEF", "도적", "class", ""],
  ["RANGER", "레인저", "class", ""],
  ["ALCHEMIST", "연금술사", "class", ""],
  ["BARD", "바드", "class", ""],
  ["PSIONIC", "사이오닉", "class", ""],
  ["VALKYRIE", "발키리", "class", ""],
  ["BISHOP", "비숍", "class", ""],
  ["LORD", "로드", "class", ""],
  ["SAMURAI", "사무라이", "class", ""],
  ["MONK", "몽크", "class", ""],
  ["NINJA", "닌자", "class", ""],
];
glossary.getRangeByIndexes(0, 0, glossaryRows.length, 4).values = glossaryRows;
glossary.getRange("A1:D1").format = headerStyle;
glossary.getRange("A2:D26").format = { verticalAlignment: "top", wrapText: true };
glossary.getRange("A1:A26").format.columnWidthPx = 180;
glossary.getRange("B1:B26").format.columnWidthPx = 180;
glossary.getRange("C1:C26").format.columnWidthPx = 110;
glossary.getRange("D1:D26").format.columnWidthPx = 300;
glossary.freezePanes.freezeRows(1);

const checks = [];
for (const [sheetName, range] of [
  ["Instructions", "A1:B30"],
  ["Messages", "A1:I24"],
  ["Scenario", "A1:H24"],
  ["Glossary", "A1:D26"],
]) {
  checks.push((await workbook.inspect({ kind: "table", range: `${sheetName}!${range}`, include: "values,formulas", tableMaxRows: 30, tableMaxCols: 10 })).ndjson);
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, `${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
await fs.writeFile(path.join(outputDir, "inspection.txt"), `${checks.join("\n")}\n${errors.ndjson}\n`, "utf8");

const output = await SpreadsheetFile.exportXlsx(workbook);
const outputPath = path.join(outputDir, "Wizardry7_Korean_Translation.xlsx");
await output.save(outputPath);
console.log(outputPath);
