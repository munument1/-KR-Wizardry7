# v0.45 SCENARIO.DBS 아이템/몬스터 한글화

## 범위

v0.45는 GOG DOS판 `SCENARIO.DBS`의 고정폭 이름 필드를 한국어화한다.

- 아이템 이름: 600 슬롯 중 실제 이름 568개
- 몬스터 이름: 250 레코드 × 4 변형 = 1,000 슬롯
- 각 이름 슬롯: 정확히 16바이트

번역 원본은 `translations/dos_scenario_ko.csv`에 보존한다.

## 초기 후보판에서 발견된 문제

메시지 본문은 `0x17 + rank + rank` 한글 스트림을 사용한다. 처음에는 SCENARIO 이름도
같은 방식을 섞어 사용했으나, 실제 아이템 화면에서 `지팡이`의 `팡`처럼 일부 글자가
`?`로 변환되는 현상이 확인됐다.

따라서 SCENARIO 고정폭 이름에는 메시지용 escape 스트림을 사용하지 않는다.

## v0.45 안전 인코딩

- 자주 쓰는 한글: 기존 글리프 테이블을 가리키는 1바이트 직접 코드
- 나머지 한글: `F0..F8 + 80..FF` 2바이트 안전 코드
- ASCII: 원래 ASCII 그대로
- 아이템/몬스터 번역 슬롯 내부 `0x17`: 0개

2바이트 코드는 다음 식으로 기존 resident 글리프 인덱스를 가리킨다.

```text
glyph_index = (lead - 0xF0) * 128 + (trail - 0x80)
```

`VBFONT0.VGA` resident 문자열/폭 계산 루틴은 이 코드를 해석하도록 확장됐다.

## 검증된 런타임 자산

```text
SCENARIO.DBS
SHA-256 8ff513e0469dd12b8b175c7a99b43029eba5b04f70b7794627cc644e1fe34875

VBFONT0.VGA
SHA-256 f7d31cb5afe492840d75eec8eafc87975867601772cc2290d08ffc77185aaa2f

korean_codebook.json
SHA-256 376d10c1031f1bc7ee125905b72675f14cfae604caa1dacbaf2001b732bce477
```

실제 게임에서 아이템 이름과 몬스터 이름 출력, 그리고 v0.44에서 수정한 초반
자네트 이벤트가 함께 정상 동작하는 것을 확인한 뒤 v0.45 릴리스 기준으로 채택했다.
