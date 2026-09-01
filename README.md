# 위저드리 7 DOS 한글화 패치

**Wizardry VII: Crusaders of the Dark Savant** GOG DOS판을 위한 한글화
패치입니다. 현재 배포 버전은 **0.44**입니다.

> 이 패치는 **GOG에 포함된 DOS판**용입니다. Wizardry 7 Gold에는 적용하지
> 마십시오.

## 다운로드

### [위저드리 7 DOS 한글화 0.44 받기](https://github.com/munument1/-KR-Wizardry7/releases/download/v0.44/Wizardry7_Korean_0.44_event_state_fix.zip)

- [릴리스 설명 보기](https://github.com/munument1/-KR-Wizardry7/releases/tag/v0.44)
- 파일명: `Wizardry7_Korean_0.44_event_state_fix.zip`
- SHA-256: `9E1B27E2EBC617A0B4400D656B548FA4D7CD65D9F1DF23852AD8B82DF1702C1D`

## 설치 방법

1. 위 ZIP 파일을 내려받습니다.
2. 기존 위저드리 7 설치 폴더를 통째로 백업합니다.
3. ZIP을 풉니다.
4. 압축 안의 `DSAVANT` 폴더를 GOG 위저드리 7 설치 폴더에 복사합니다.
5. 같은 이름의 파일을 모두 **덮어쓰기** 합니다.
6. GOG 바로가기 또는 기존 DOSBox 실행 파일로 게임을 시작합니다.

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

## 0.44 주요 수정

- 초반 초보 던전 방향에서 **자네트(Jan-Ette) 대신 H'Jenn-Ra/T'Rang 장면이
  나오는 문제의 실제 원인 수정**
- `VBASE.OVR + 0x667B`에서 v0.35부터 사용하던 강제 성공 코드 `B8 01 00`을
  원래 GOG 호출 `E8 4C 73`으로 복구
- 원래 resident 루틴이 성공 반환 외에도 수행하던 `DS:1008 <- DS:59F8` 상태
  초기화를 다시 보존
- 한글 코어 + 순정 OVR, VMNPC 단독, VBASE 단독, 3바이트 원복, 전체 v0.43 원복
  비교를 통해 실제 실행에서 원인 범위를 확인
- 전체 v0.43 구성에 해당 3바이트만 복구한 빌드에서 새 게임 자네트 정상 등장 확인
- v0.43의 parser-neutral 한글 인코딩과 장면 텍스트 깨짐 수정 유지

## 0.43에서 유지되는 수정

- 한글 `0x17 + rank + rank` 내부에서 DOS 장면 파서가 구조적으로 사용하는
  `SPACE _ $ ^ ! % & ] @ # |` 11개 바이트를 전부 제외
- 전체 한글 rank 구조 바이트 충돌 0개
- 자네트 메시지 구간 `29600..29756` 구조 바이트 충돌 0개
- `VBFONT0.VGA`의 rank 역변환 테이블 및 글리프 대응 갱신
- v0.41 캐릭터 목록 M/F 경계 수정과 v0.39 저장/오버레이 안전 수정 유지

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

저장 관련 기능은 이전 버전에서 실제 DOSBox로 기존 저장 불러오기 → 저장 및 계속 →
저장 및 종료 → 방금 기록한 파일 재불러오기 순서로 검증했습니다.

0.44 빌드는 GitHub Actions에서 v0.43 공개 ZIP의 SHA-256을 먼저 검증한 다음 정확한
`VBASE.OVR` 3바이트만 수정하며, 나머지 v0.43 payload는 그대로 유지합니다.

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

### 초반 필드에서 다른 NPC/그림이 나오는 경우

- 패치 버전이 0.44인지 확인합니다.
- 특히 `VBASE.OVR`가 0.44 ZIP의 파일로 실제 덮어써졌는지 확인합니다.
- 가능하면 새 게임으로 같은 지점을 재현하고 스크린샷과 직전 행동을 함께
  제보해 주십시오.

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

패치를 사용하는 데 아래 문서를 읽을 필요는 없습니다. 번역이나 실행 파일 패치
개발을 이어갈 때만 참고하십시오.

- [`docs/V44_JAN_ETTE_EVENT_ROOT_CAUSE.md`](docs/V44_JAN_ETTE_EVENT_ROOT_CAUSE.md)
- [`docs/WEBGPT_HANDOFF_2026-08-31.md`](docs/WEBGPT_HANDOFF_2026-08-31.md)
- [`docs/VERSION_0.39_OVERLAY_SAFE_RESIDENT_2026-08-30.md`](docs/VERSION_0.39_OVERLAY_SAFE_RESIDENT_2026-08-30.md)
- [`docs/korean_rendering_plan.md`](docs/korean_rendering_plan.md)

## 면책

Wizardry 및 관련 상표·게임 데이터의 권리는 각 권리자에게 있습니다. 이 저장소는
비공식 팬 번역 프로젝트이며 원 제작사나 GOG와 관련이 없습니다.
