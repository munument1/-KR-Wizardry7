# v0.46 런타임 입력 판정 문자열 복구

## 증상

DOS/GOG판 한국어 0.45에서 뉴 시티 입구 경비병이 `뉴 시티에서 무슨 용무가 있지?`라고
질문한 뒤 정상 답을 입력해도 통과하지 못하는 제보가 있었다.

원본 DOS 메시지 15180은 표시용 문장이 아니라 다음과 같은 입력 판정 테이블이다.

```text
<0x02>PALUKE/<0x02>ARMORY/
```

기존 번역 원고는 이를 `팔루크/갑옷점/`으로 번역했다. DOS 게임은 한국어 번역 문장을
의미적으로 비교하지 않고 입력 문자열을 이 테이블의 ASCII 토큰과 직접 대조하므로,
`PALUKE`, `ARMORY`, `PALUKE'S ARMORY`를 입력해도 더 이상 분기 조건을 만족할 수 없었다.

## 범위

원본 GOG/DOS `MSG.HDR + MSG.DBS + MISC.HDR`를 디코드해 다음 보수적 규칙에 맞는
레코드를 런타임 판정 데이터로 분리했다.

- `/`로 구분되는 답안/동의어 테이블
- 영문자는 원본에서 대문자로 저장된 로직 문자열
- `<0xNN>` 분기 제어 바이트를 포함하거나 둘 이상의 후보 토큰을 포함
- 일반 표시 문장(소문, 대사, 상태창 등)은 제외

확정 manifest는 `data/dos_runtime_matchers.json`이며 **186개** 레코드를 담는다.
대표 범위는 다음과 같다.

- 1690: 공통 YES/NO 판정
- 7160~7197: NPC 대화 문법/동의어
- 8902 이후: NPC·지역·소문 키워드
- 15180: 뉴 시티 `PALUKE/ARMORY`
- 이후 YES/NO, 암호, 퍼즐 정답, 컴퓨터 명령 및 이벤트 선택 판정

## 구현

`tools/build_dos_v46_runtime_matchers.py`는 공개 0.45 ZIP을 기준으로 다음만 변경한다.

1. 현재 `MSG.HDR/MSG.DBS`를 0.45 `MISC.HDR`로 디코드한다.
2. manifest에 있는 186개 레코드만 원본 DOS 바이트로 교체한다.
3. 기존 Huffman 트리를 그대로 사용해 다시 인코딩한다.
4. DOS의 실제 규칙대로 각 범위의 **모든 레코드 시작점**은 같은 1 KiB bank에 유지하되,
   마지막 payload가 다음 bank로 넘어가는 것은 허용한다.
5. `MSG.HDR` 크기와 `MSG.DBS` 256 KiB 크기를 유지한다.
6. 재디코드하여 manifest 밖 레코드의 decoded byte 변경이 0개인지 검증한다.

`MISC.HDR`, `SCENARIO.DBS`, `VBFONT0.VGA`는 0.45와 동일하게 유지된다.

## 회귀 방지

테스트와 릴리스 workflow는 다음을 강제한다.

- manifest 레코드 수 186
- 15180이 정확히 `<0x02>PALUKE/<0x02>ARMORY/`
- 7160 `HI/HELLO/HAIL/`, 7162 `YES/SURE/OK/YEA/YEAH/` 보존
- manifest 밖 전체 메시지 decoded byte 동일
- 0.45의 폰트/SCENARIO/Huffman 자산 보존

앞으로 번역 원고를 다시 빌드할 때도 이 manifest의 레코드는 **번역 대상이 아니라 게임 로직 데이터**로 취급해야 한다.
