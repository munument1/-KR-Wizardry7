# 위저드리 7 DOS 한글화

GOG판 **Wizardry VII: Crusaders of the Dark Savant** DOS 버전을 한글화하는
프로젝트입니다. 현재 공개 버전은 **0.39**이며, 소스 내부의 `v39` 표기는
내부 빌드 39를 뜻합니다.

## 0.39 주요 내용

- 한글 메뉴와 캐릭터 생성 화면
- 한글 애니메이션 타이틀 로고
- 알레테이데스 오프닝과 첫 행성 이벤트 대사
- 2바이트 한글 글리프 렌더링과 한글 폭 계산
- 직업명과 UI 문구의 한글 경계 처리
- `저장 & 계속`, `저장 & 종료`, 새 저장 파일 재불러오기 정상화
- 가장 긴 `VMNPC.OVR`까지 포함한 오버레이 충돌 검사 통과
- 전체 81개 자동 테스트 통과

## 다운로드 및 설치

1. [GitHub 릴리스 v0.39](https://github.com/munument1/-KR-Wizardry7/releases/tag/v0.39)에서
   `Wizardry7_Korean_0.39_overlay_safe_resident.zip`을 받습니다.
2. 기존 위저드리 7 설치 폴더를 먼저 백업합니다.
3. ZIP을 풀어 나온 `DSAVANT` 폴더를 GOG 위저드리 7 설치 폴더에 복사합니다.
4. 같은 이름의 파일을 모두 **덮어쓰기** 합니다.
5. 평소처럼 GOG 실행기 또는 DOSBox 설정 파일로 게임을 실행합니다.

일반적인 설치 위치의 예는 다음과 같습니다.

```text
C:\GOG Games\Wizardry 7\DSAVANT
```

다른 판본이나 이미 별도 패치가 적용된 파일에서는 정상 동작을 보장하지 않습니다.
문제가 생기면 백업한 `DSAVANT` 폴더로 복원하십시오.

## 저장 오류 수정 내용

v20부터 v37까지 남아 있던 저장 실패의 원인은 저장 버퍼 초과가 아니었습니다.
폭 계산과 능력치 재도색을 담당하던 영구 헬퍼가 `0xF790`, `0xF7B0`에 있었고,
본게임 오버레이가 이 위치를 덮어쓴 뒤 저장 화면이 손상된 코드를 호출하면서
`Memory unavailable loading picture.` 오류가 발생했습니다.

0.39에서는 다음과 같이 영구 코드를 오버레이 범위 밖으로 옮겼습니다.

- 공용 폭 계산 어댑터: root CS `0x38F4`
- 장면 후행 ASCII 어댑터: root CS `0x38F8`
- 능력치 재도색 헬퍼: root CS `0x390C`
- 장면 검색·후행 문자 디스패처: resident `VBFONT0.VGA`의 `0x0AF0..0x0B6C`

`DS.EXE`, `VBFONT0.VGA`, 모든 OVR 파일의 크기는 유지됩니다. 실제 DOSBox에서
기존 저장 파일 불러오기, `저장 & 계속`, `저장 & 종료`, 방금 기록한 저장 파일의
재불러오기까지 확인했습니다.

## 소스에서 0.39 빌드

로컬에서 v37 산출물을 준비한 뒤 내부 v39 빌더를 실행합니다.

```powershell
python tools\build_dos_v39_overlay_safe_resident.py `
  --v37-dir outputs\v37_fixed_scene_helpers_final `
  --output-dir outputs\0.39_overlay_safe_resident_final `
  --zip-output outputs\Wizardry7_Korean_0.39_overlay_safe_resident.zip
```

전체 회귀 테스트:

```powershell
python -m unittest discover -s tests -v
```

오버레이 충돌 검사:

```powershell
python tools\audit_dos_overlay_resident_collisions.py
```

## DOS 메시지 추출

`MISC.HDR`는 `MSG.HDR` 옆에서 자동으로 찾습니다.

```powershell
python tools\extract_gold_messages.py `
  --hdr "D:\Wizardry 7\DSAVANT\MSG.HDR" `
  --data "D:\Wizardry 7\DSAVANT\MSG.DBS" `
  --output-dir outputs\dos_extracted\msg
```

생성되는 주요 파일:

- `messages_for_translation.csv`: UTF-8 BOM 번역 표
- `messages.json`: 전체 레코드와 무손실 Base64/16진수 데이터
- `messages.jsonl`: 레코드별 기계 판독 데이터
- `extraction_report.json`: 원본 해시와 구조 검증 결과

CSV에 표시되는 `<0xNN>`은 게임 제어 바이트입니다. 번역하거나 삭제하거나 순서를
바꾸면 안 됩니다.

## DOS 메시지 재구성

Google Sheets의 `Messages` 탭을 CSV로 내보낸 뒤 실행합니다.

```powershell
python tools\build_dos_messages.py `
  --hdr "D:\Wizardry 7\DSAVANT\MSG.HDR" `
  --data "D:\Wizardry 7\DSAVANT\MSG.DBS" `
  --misc "D:\Wizardry 7\DSAVANT\MISC.HDR" `
  --translations messages_translated.csv `
  --output-dir outputs\dos_patch\DSAVANT
```

빌더는 원문 불일치 여부를 검사하고, 번역문을 허프만 압축한 뒤 `MISC.HDR`,
`MSG.HDR`, `MSG.DBS`, `korean_codebook.json`을 생성합니다. DOS 서브인덱스가
레코드를 읽을 때 `0x400`바이트 뱅크 경계를 넘지 않도록 각 `MSG.HDR` 범위를
하나의 뱅크 안에 배치합니다. 빌드 보고서에서 다음 조건을 만족해야 합니다.

```text
record_start_crossings: 0
used_bank_count <= 256
```

기존 한글 메시지 계층의 허프만 데이터를 유지하면서 뱅크 배치만 복구하려면 다음
도구를 사용합니다.

```powershell
python tools\repack_dos_message_banks.py `
  --hdr translated\MSG.HDR `
  --data translated\MSG.DBS `
  --misc translated\MISC.HDR `
  --output-dir outputs\dos_patch\repacked
```

## 아이템·몬스터 이름 추출

DOS판에서는 `D:\Wizardry 7\DSAVANT\SCENARIO.DBS`를 입력 파일로 사용합니다.

```powershell
python tools\extract_gold_scenario_strings.py `
  --scenario original\SCENARIO.GLD `
  --output-dir extracted\scenario
```

번역 CSV에는 아이템 이름 600칸과 몬스터 250종의 16바이트 이름 변형 네 개가
포함됩니다. 빈 슬롯도 레코드 인덱스와 바이너리 오프셋을 유지하기 위해 보존합니다.
16바이트 제한은 유니코드 글자 수가 아니라 게임 인코딩 바이트 수입니다.

## 관련 문서

- [`docs/WEBGPT_HANDOFF_2026-08-31.md`](docs/WEBGPT_HANDOFF_2026-08-31.md): 최종 상태와 런타임 검증
- [`docs/VERSION_0.39_OVERLAY_SAFE_RESIDENT_2026-08-30.md`](docs/VERSION_0.39_OVERLAY_SAFE_RESIDENT_2026-08-30.md): 0.39 resident 구조
- [`docs/korean_rendering_plan.md`](docs/korean_rendering_plan.md): 한글 렌더링 구조와 구현 기록

## 주의 사항

- 원본 GOG 설치본은 별도로 보관하십시오.
- 다른 번역·실행 파일 패치와 함께 사용할 때는 충돌할 수 있습니다.
- 새 오버레이나 resident 헬퍼를 추가할 때는 반드시 실제 런타임 주소 충돌을 검사하십시오.
- 오버레이 길이를 임의로 늘리면 오프닝이나 이벤트 진행이 깨질 수 있습니다.
