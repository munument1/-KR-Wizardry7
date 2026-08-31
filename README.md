# Wizardry 7 Gold 한국어화 작업 공간

로컬 GOG 설치 파일은 이 저장소에 절대 커밋하지 않습니다. 분석이나 패치 실험을 시작하기 전에 원본 번역 관련 파일을 Git에서 무시되는 `original/` 디렉터리에 복사합니다.

## 프로젝트 상태

- GOG Wizardry 7 Gold의 메시지 및 시나리오 문자열 추출 기능을 구현했습니다.
- 번역용 CSV 및 워크북 생성 기능을 로컬에서 구현했습니다.
- x86 WinMM 프록시를 통해 게임의 기존 VBFONT 렌더러로 2바이트 KS X 1001 한글을 출력할 수 있습니다.
- 실행 중인 게임에서 8x8 `한` 스모크 테스트를 확인했습니다.
- 게임의 기본 문자열 폭 계산 루틴을 후킹하여 2바이트 한글 코드를 하나의 글리프로 계산하도록 했습니다.
- 다음 작업: 메시지 제어 코드/줄바꿈 검증 및 CSV 재삽입 도구 구현.

이 공개 저장소에는 구매한 게임 파일, 추출된 게임 텍스트, 로컬에서 생성한 패치, API 인증 정보 및 빌드 결과물을 의도적으로 포함하지 않습니다. 도구를 실행하려면 본인이 소유한 GOG 설치본을 준비해야 합니다.

## 메인 메시지 데이터베이스 추출

```powershell
python tools\extract_gold_messages.py `
  --hdr original\MSG.HDR `
  --gld original\MSG.GLD `
  --output-dir extracted\msg
```

출력 파일:

- `messages_for_translation.csv`: UTF-8 BOM 형식의 스프레드시트용 번역 테이블.
- `messages.json`: 메타데이터와 전체 레코드, 무손실 Base64/16진수 페이로드.
- `messages.jsonl`: 한 줄에 하나의 기계 판독용 레코드.
- `extraction_report.json`: 원본 해시와 구조 검증 결과 수치.

CSV에서는 출력할 수 없는 게임 제어 바이트를 `<0xNN>` 형식으로 표시합니다. 이 마커는 번역하거나 삭제하거나 순서를 바꾸면 안 됩니다. JSON 출력에는 이후 바이트 단위로 완전히 동일한 재구성을 검증할 수 있도록 원본 페이로드가 그대로 보존됩니다.

## 아이템 및 몬스터 이름 추출

```powershell
python tools\extract_gold_scenario_strings.py `
  --scenario original\SCENARIO.GLD `
  --output-dir extracted\scenario
```

시나리오 번역 CSV에는 아이템 이름 슬롯 600개와 몬스터 250종 각각에 대한 16바이트 이름 변형 4개가 포함됩니다. 레코드 인덱스와 바이너리 오프셋을 안정적으로 유지하기 위해 빈 슬롯도 그대로 보존합니다. 한국어를 삽입하려면 게임용 사용자 정의 인코딩이 필요하며, 16바이트 제한은 유니코드 문자 수가 아니라 인코딩된 바이트 수를 의미합니다.

## 한글 렌더링 프로토타입

x86 WinMM 프록시는 현재 실행 중인 GOG Gold 게임에서 API로 전달한 KS X 1001 한글 글리프를 렌더링할 수 있습니다. 2바이트 게임 인코딩을 사용하며, 게임의 기존 그리기 루틴을 호출하기 전에 활성 VBFONT 안의 예약 글리프 하나를 동적으로 교체하는 방식입니다.

Visual Studio 개발자 환경에서 다음 명령으로 프록시를 빌드합니다:

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_winmm_proxy.ps1
```

현재 스모크 테스트용 자산은 다음 명령으로 빌드합니다:

```powershell
node tools\make_vbfont0_8x8.mjs
node tools\make_hangul_smoke_patch.mjs
```

생성된 파일은 `outputs/` 아래에 저장됩니다. 스모크 패치는 `HUMAN`과 메인 메뉴의 `CREATE` 라벨을 `한`으로 교체합니다. 이는 테스트 데이터이며 번역 배포판이 아닙니다. 검증된 주소, 인코딩 방식, 현재 제한 사항 및 다음 구현 단계는 `docs/korean_rendering_plan.md`를 참고하세요.
