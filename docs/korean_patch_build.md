# 한국어 패치 빌드

번역 데이터는 `translations/wizardry7_ko_payload.zip`에 묶여 있고 검증 정보는 `translations/manifest.json`에서 확인할 수 있습니다. 공개 저장소에는 영문 원문을 넣지 않고, 레코드 식별자·원문 CRC32·한국어 번역만 저장합니다.

## 1. 원본 파일 준비

GOG Wizardry 7 Gold 설치에서 다음 파일을 `original/`에 복사합니다.

- `MSG.HDR`
- `MSG.GLD`
- `SCENARIO.GLD`
- `VBFONT0.VGA`

패처는 입력 파일을 수정하지 않습니다. 번역 데이터의 CRC와 원본 레코드가 맞지 않으면 즉시 중단합니다.

## 2. 데이터 패치 생성

```powershell
python tools\build_korean_patch.py `
  --original-dir original `
  --translation-dir translations\wizardry7_ko_payload.zip `
  --output-dir outputs\korean_patch
```

생성 파일:

- `MSG.HDR`, `MSG.GLD`: 모든 메시지를 전용 2바이트 한글 코드로 재빌드
- `SCENARIO.GLD`: 아이템/몬스터 16바이트 이름 슬롯을 인플레이스 패치
- `VBFONT0.VGA`: 검증된 6x6 → 8x8 컨테이너 변환
- `patch_manifest.json`: 입력/출력 SHA-256, 레코드 수, 런타임 포함 여부

## 3. 런타임 포함

실제 한글 표시에는 기존 프록시 런타임 두 파일이 추가로 필요합니다.

- 32비트 `winmm.dll` (`tools/build_winmm_proxy.ps1`로 빌드)
- `wizardry7_ksx1001_8x8.bin` (KS X 1001 2,350자 8x8 글리프 파일)

두 파일을 함께 패키징하려면:

```powershell
python tools\build_korean_patch.py `
  --original-dir original `
  --winmm build\winmm_proxy\winmm.dll `
  --hangul-font path\to\wizardry7_ksx1001_8x8.bin
```

`patch_manifest.json`의 `ready_to_install`이 `true`이면 게임 폴더에 복사할 런타임까지 모두 포함된 상태입니다.

## 번역 워크북 갱신

Google Sheets를 `.xlsx`로 내려받은 뒤 다음 명령으로 GitHub용 번역 페이로드 ZIP을 다시 만들 수 있습니다.

```powershell
python tools\import_translation_xlsx.py Wizardry7_translation.xlsx --output-dir translations
```

임포터는 제어코드 순서, `$ ^ % @ # * /` 개수, KS X 1001 지원 여부, 메시지 255바이트 제한, Scenario 16바이트 제한을 검사합니다.
