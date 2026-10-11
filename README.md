# 위저드리 7 DOS 한글화 패치

**Wizardry VII: Crusaders of the Dark Savant** GOG DOS판을 위한 한글화
패치입니다. 현재 배포 버전은 **0.49**입니다.

> 이 패치는 **GOG에 포함된 DOS판**용입니다. Wizardry 7 Gold에는 적용하지
> 마십시오.

## 다운로드

### [위저드리 7 DOS 한글화 0.49 받기](https://github.com/munument1/-KR-Wizardry7/releases/download/v0.49/Wizardry7_Korean_0.49.zip)

- [릴리스 설명 보기](https://github.com/munument1/-KR-Wizardry7/releases/tag/v0.49)
- 파일명: `Wizardry7_Korean_0.49.zip`
- SHA-256: `6B70E59056D687BD34415EDE0FC3D1DD0D7A030672836CAF9FA63A216CD4DE5B`

## 설치 방법

1. 게임과 DOSBox를 완전히 종료한 뒤 위 ZIP 파일을 내려받습니다.
2. 기존 위저드리 7 설치 폴더를 통째로 백업합니다.
3. ZIP을 풉니다.
4. 압축 안의 `DSAVANT` 폴더를 GOG 위저드리 7 설치 폴더에 복사합니다.
5. 같은 이름의 파일을 모두 **덮어쓰기** 합니다.
6. GOG 바로가기 또는 기존 DOSBox 실행 파일로 게임을 다시 시작합니다.

이전 패치에서 업데이트할 때도 ZIP 안의 `DSAVANT` 파일을 **모두 덮어쓰기**
하십시오. 0.49에는 이전 버전의 수정이 포함되어 있어 순서대로 설치할 필요가
없습니다. 일반적으로 새 게임 없이 기존 저장 파일을 이어서 사용할 수 있습니다.

일반적인 설치 구조는 다음과 같습니다.

```text
Wizardry 7\
├─ DOSBOX\
├─ DSAVANT\        ← 이 폴더에 덮어쓰기
├─ dosboxWizardry7.conf
└─ Launch Wizardry 7 (DOS Version).lnk
```

## 제거 및 복구

별도 제거 프로그램은 없습니다. 설치 전에 백업한 원본 `DSAVANT` 폴더를 다시
덮어쓰면 복구됩니다. 백업이 없다면 GOG에서 게임을 다시 설치한 뒤 저장 파일만
복원하십시오.

저장 파일은 일반적으로 다음 위치에 있습니다.

```text
게임 설치 폴더\DSAVANT\SAVEGAME.DBS
```

DOSBox 안에서는 `C:\DSAVANT\SAVEGAME.DBS`로 표시될 수 있으며 정상입니다.

## 0.49 주요 수정

- 뉴시티에서 `책 우화`(Book of Fables / The Witch's Tale)를 읽다가 종료되던 문제 수정
- 잠긴 문, 상자/도둑 메뉴 등의 한글 선택지가 버튼 왼쪽으로 밀리던 중앙정렬 문제 수정
- 아래 0.46~0.48의 입력 판정 및 NPC 대화 수정 포함

## 0.46~0.48에서 유지되는 수정

- 뉴시티 입구의 `PALUKE / ARMORY` 입력 판정 복구
- 무기점의 `BLACK MARKET` 및 각 지역의 암호·퍼즐 답안 판정 복구
- `HI`, `BYE`, `YES`, `NO`, `RUMORS` 등 NPC 대화 입력 처리 복구
- 팔루크의 포로 소문을 포함한 NPC 대화 주제 검색 복구
- 내부 판정용 문자열은 원본 영어로 유지하고, 화면에 표시되는 한국어 대사는 보존

## 0.45에서 유지되는 수정

- `SCENARIO.DBS` 아이템 이름 **568개** 한글화
- 몬스터 이름 **1,000개 슬롯** 한글화
- 16바이트 고정폭 SCENARIO 이름에서 일부 글자가 `?`로 바뀌던 문제 수정
- SCENARIO 이름용 안전 인코딩 도입
  - 자주 쓰는 한글은 1바이트 직접 코드
  - 나머지 한글은 `F0..F8 + 80..FF` 2바이트 코드
  - 아이템/몬스터 번역 슬롯 내부 `0x17` escape 사용 0개
- 실제 게임에서 아이템과 몬스터 이름 정상 출력 확인
- v0.44의 자네트(Jan-Ette) 이벤트 상태 수정 유지

## 0.44에서 유지되는 수정

- 초반 초보 던전 방향에서 자네트 대신 H'Jenn-Ra/T'Rang 장면이 나오던 문제 수정
- `VBASE.OVR + 0x667B` 원래 GOG 호출 복구
- v0.43 parser-neutral 한글 인코딩과 장면 텍스트 깨짐 수정 유지
- v0.41 캐릭터 목록 M/F 경계 수정 및 v0.39 저장/오버레이 안전 수정 유지

## 현재까지 확인된 내용

- 한글 메뉴와 캐릭터 생성 화면
- 한글 애니메이션 타이틀 로고
- 알레테이데스 오프닝과 첫 행성 이벤트
- 직업명과 주요 UI 문구
- 2바이트 한글 글리프 표시와 글자 폭 계산
- `저장 & 계속`
- `저장 & 종료`
- 새로 기록한 저장 파일 재불러오기
- 새 게임 초반 자네트(Jan-Ette) 조우 정상 진행
- 아이템 이름 한글 출력
- 몬스터 이름 한글 출력

저장 관련 기능은 이전 버전에서 실제 DOSBox로 기존 저장 불러오기 → 저장 및 계속 →
저장 및 종료 → 방금 기록한 파일 재불러오기 순서로 검증했습니다.

## 설치 전 알아둘 점

- 반드시 보유 중인 GOG DOS판을 먼저 설치해야 합니다.
- 다른 실행 파일 패치나 한글 패치가 적용된 상태에서는 충돌할 수 있습니다.
- 기존 저장 파일은 보존되지만 설치 전 별도 백업을 권장합니다.
- 게임 전체의 모든 선택지와 지역을 사람이 끝까지 검수한 완성판은 아닙니다.
- 번역 누락, 문장 오류, 글자 겹침을 발견하면 화면과 발생 위치를 함께 제보해
  주십시오.

## 문제가 생길 때

### 실행 직후 종료되는 경우

- Gold판이 아닌 GOG DOS판에 적용했는지 확인합니다.
- 다른 패치를 제거하고 깨끗하게 재설치한 게임에 다시 적용합니다.
- GOG 설치 폴더 경로와 DOSBox 설정 파일이 원래 상태인지 확인합니다.

### 저장 파일이 보이지 않는 경우

- `DSAVANT` 폴더 안에 `SAVEGAME.DBS`가 있는지 확인합니다.
- 게임의 저장 화면에서 `C:\DSAVANT\`가 표시되는 것은 정상입니다.
- 다른 위저드리 7 설치본을 실행하고 있지 않은지 확인합니다.

### 아이템/몬스터 이름에 `?`가 보이는 경우

- 패치 버전이 0.49인지 확인합니다.
- `SCENARIO.DBS`와 `VBFONT0.VGA`가 0.49 ZIP의 파일로 실제 덮어써졌는지 확인합니다.

### 초반 필드에서 다른 NPC/그림이 나오는 경우

- 패치 버전이 0.49인지 확인합니다.
- 특히 `VBASE.OVR`가 0.49 ZIP의 파일로 실제 덮어써졌는지 확인합니다.
- 가능하면 새 게임으로 같은 지점을 재현하고 스크린샷과 직전 행동을 함께
  제보해 주십시오.

### `PALUKE`나 `BLACK MARKET`을 입력해도 거절당하는 경우

- 위 다운로드 링크의 `Wizardry7_Korean_0.49.zip`을 사용했는지 확인합니다.
- 게임과 DOSBox를 완전히 종료하고 ZIP 안의 `DSAVANT` 파일을 모두 덮어쓴 뒤
  다시 실행합니다. 특히 `MSG.HDR`, `MSG.DBS`, `MISC.HDR`가 같은 ZIP의 파일이어야 합니다.
- 암호와 NPC 질문은 영어로 입력합니다. 한글로 번역된 화면 대사와 내부 입력
  판정값은 별개입니다.
- 이미 실패한 이벤트 상태가 저장되었다면 해당 조우 전 저장 파일에서 다시 시도합니다.
- 계속 발생하면 실패 직전 저장 파일, 사용한 ZIP 파일명, 입력한 문구와 화면을
  함께 제보해 주십시오.

### 원래 상태로 되돌리고 싶은 경우

백업한 `DSAVANT` 폴더를 복원하거나 GOG에서 게임을 재설치하십시오.

## 오류 제보

[GitHub Issues](https://github.com/munument1/-KR-Wizardry7/issues)에 다음 정보를
적어 주시면 확인에 도움이 됩니다.

- 오류가 발생한 화면의 스크린샷
- 오류 직전 선택한 메뉴나 행동
- 새 게임인지 기존 저장 파일인지 여부
- 사용한 패치 버전

## 개발 자료

- [`docs/V49_READ_BUFFER.md`](docs/V49_READ_BUFFER.md)
- [`docs/V48_NPC_TOPIC_KEYS.md`](docs/V48_NPC_TOPIC_KEYS.md)
- [`docs/V47_NPC_PARSER_CORE.md`](docs/V47_NPC_PARSER_CORE.md)
- [`docs/V46_RUNTIME_MATCHER_RESTORE.md`](docs/V46_RUNTIME_MATCHER_RESTORE.md)
- [`docs/V45_SCENARIO_SAFE_ENCODING.md`](docs/V45_SCENARIO_SAFE_ENCODING.md)
- [`docs/V44_JAN_ETTE_EVENT_ROOT_CAUSE.md`](docs/V44_JAN_ETTE_EVENT_ROOT_CAUSE.md)
- [`docs/WEBGPT_HANDOFF_2026-08-31.md`](docs/WEBGPT_HANDOFF_2026-08-31.md)
- [`docs/VERSION_0.39_OVERLAY_SAFE_RESIDENT_2026-08-30.md`](docs/VERSION_0.39_OVERLAY_SAFE_RESIDENT_2026-08-30.md)
- [`docs/korean_rendering_plan.md`](docs/korean_rendering_plan.md)

## 면책

Wizardry 및 관련 상표·게임 데이터의 권리는 각 권리자에게 있습니다. 이 저장소는
비공식 팬 번역 프로젝트이며 원 제작사나 GOG와 관련이 없습니다.
