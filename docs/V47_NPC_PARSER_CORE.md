# Wizardry VII DOS v0.47 NPC parser-core fix

## Symptom

After v0.46, progression matchers such as New City `PALUKE / ARMORY` were restored, but normal NPC conversation could still reject `BYE` and other basic English words.

## Root cause

`VMNPC.OVR` uses two layers of message data for typed conversation input.

1. **Canonical grammar tables** loaded from fixed message IDs:
   - `7000..7009`
   - `7030..7036`
   - `7040..7041`
   - `7050..7056`
   - `7070..7079`
   - `7090..7100`
   - `7120..7129`
   - `7140..7146`
2. **Synonym/normalization table** `7160..7197`.

For example, `7161` contains `BYE/GOODBYE/QUIT/FAREWELL/`. The parser normalizes one of those inputs to `BYE`, then compares it against canonical token `7121`, which must also be `BYE`.

v0.46 restored the slash-delimited synonym record but missed the non-slash canonical records because the matcher audit intentionally searched for slash-delimited logic data. In the Korean message bank, `7121` was still translated. Therefore the normalized ASCII token and the canonical parser token could never compare equal.

## v0.47 fix

v0.47 restores all 64 canonical parser-core records to their original DOS ASCII, in addition to the 186 runtime matcher records already handled by v0.46. Total protected parser/logic records: **250**.

Regression checks explicitly require:

- `7161 == BYE/GOODBYE/QUIT/FAREWELL/`
- `7121 == BYE`
- first synonym token of each linked global synonym row equals its canonical parser token
- exactly 64 newly changed records when building from the published v0.46 package
- the existing 186 v0.46 matcher records remain byte-equivalent to their original values
- decoded records outside the 250 protected logic IDs do not change
- `VMNPC.OVR`, `MISC.HDR`, `SCENARIO.DBS`, and `VBFONT0.VGA` remain unchanged from v0.46

Display prose remains Korean. Only non-display parser logic is restored to original ASCII.
