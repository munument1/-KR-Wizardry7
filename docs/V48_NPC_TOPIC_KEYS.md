# Wizardry VII DOS Korean v0.48 — NPC topic-key restore

## Symptom

After v0.47, basic parser words such as `BYE` work again, but asking Paluke about
`RUMORS` still produces the generic unknown-topic reply instead of the prisoner
rumor.

## Root cause

The DOS NPC parser has a third runtime-data layer in addition to the canonical
parser tokens and slash-delimited synonym tables restored by v0.47.

`VMNPC.OVR` loads global and per-NPC knowledge/topic records in a fixed stride of
five message IDs. The first record of each five-message group is a **lookup key**;
the following records are responses/metadata. These keys are game logic, not
visible prose.

For Paluke the relevant records include:

- `9210 = "ARMOR%`
- `9215 =  WAR%`
- `9220 =  PRISONER%`
- `9221` = the visible response about the captured Gorn officer

The Korean message rebuild translated `9220` to the Korean word for prisoner.
Thus `7177 = WHAT TELL YOU/RUMOR/RUMORS/NEWS/INFO/HINT/HINTS/` could correctly
recognize the typed word `RUMORS`, but the subsequent NPC knowledge lookup no
longer matched the original `PRISONER` topic key and fell through to the generic
"what?" response.

The same problem affects direct topic queries and rumor/knowledge resolution for
many names, places and concepts such as `ARMOR`, `WAR`, `BLACK MARKET`, `LORE`,
`NEW CITY`, NPC names, faction names and location names.

## Fix

v0.48 restores every known global/per-NPC topic lookup key to the exact original
DOS decoded byte string while retaining the Korean response records.

- global topic keys: `8000..8330`, stride 5 — 67 records
- per-NPC topic keys: 553 records across the VMNPC topic blocks
- total topic keys: 620
- translated keys restored in v0.48: 613
- keys already original in v0.47: 7
- v0.47 parser/runtime records retained: 250
- total protected runtime-logic records after v0.48: 870

The key/response distinction is intentional: for example `9220` returns to
` PRISONER%`, while `9221` remains Korean so the player still sees the localized
prisoner rumor.

## Regression checks

The release build must verify all of the following:

1. all 870 protected records decode exactly to their original DOS strings;
2. all records outside the protected set are byte-identical to v0.47;
3. `7177` remains the original `RUMORS` synonym table;
4. Paluke's `9220` key is exactly ` PRISONER%`;
5. Paluke's visible response `9221` is unchanged from v0.47;
6. `VMNPC.OVR`, `MISC.HDR`, `SCENARIO.DBS` and `VBFONT0.VGA` are byte-identical to v0.47;
7. `MSG.DBS` remains within the DOS 256 KiB limit.

No new game should be required. After overwriting the `DSAVANT` folder, fully
exit and restart the game before testing the NPC conversation again.
