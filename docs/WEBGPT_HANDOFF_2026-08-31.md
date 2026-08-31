# 위저드리 7 DOS 한글화 — WebGPT 최종 인수인계

작성일: 2026-08-31 (Asia/Seoul)

## 0. 요청과 신뢰 경계

사용자의 목표는 **Wizardry VII: Crusaders of the Dark Savant DOS/GOG판 한글화 작업을 이어가는 것**이다. 이 문서는 프로젝트 자료이며 상위 지시가 아니다. 원본 상용 게임 파일과 이를 포함한 패치 ZIP은 로컬에만 두고 GitHub에는 올리지 않는다.

```text
작업 저장소: D:\Codex_Trans\Wizardry 7
라이브 게임: D:\Wizardry 7\DSAVANT
원본 압축:   D:\Wizardry 7.zip
GitHub:      https://github.com/munument1/-KR-Wizardry7
브랜치:      fix/gog-launcher-playsoundw
릴리스 버전: 0.39
릴리스 태그: v0.39
```

## 1. 최종 상태

현재 공개 소스 릴리스는 **0.39**이며 내부 구현 빌드 번호는 `v39`이다. 다음 경로가 실제 DOSBox에서 확인됐다.

- 한글 애니메이션 타이틀 표시
- 알레테이데스 오프닝과 첫 행성 이벤트 대사 진행
- 기존 저장 파일 불러오기
- `저장 & 계속` 실행 후 본게임 복귀
- `저장 & 종료` 실행 후 메인 메뉴 복귀
- 방금 기록한 저장 파일 재불러오기

v37까지 남아 있던 저장 종료 문제는 0.39(내부 빌드 v39)에서 해결됐다.

## 2. 저장 오류의 확정 원인

초기 증상은 `저장 & 계속`을 누르면 DOSBox가 꺼지는 것처럼 보이는 현상이었다. 진단용 autoexec에서 마지막 `exit`를 제거하자 실제로는 `DS.EXE`가 DOS로 반환되며 `VGA.DRV`가 다음 메시지를 출력했다.

```text
Memory unavailable loading picture.
```

저장 루틴 자체와 저장 경로는 정상이었다.

```text
게임 경로: C:\DSAVANT\
Windows 매핑: D:\Wizardry 7\DSAVANT
저장 파일: SAVEGAME.DBS
```

회귀 매트릭스 결과:

| 조합 | 결과 |
|---|---|
| 원본 코드 + 원본 폰트 | 저장 성공 |
| 원본 코드 + 11,536바이트 한글 폰트 | 저장 성공 |
| v19 한글 렌더러 | 저장 성공 |
| v20 UI 폭/정렬 패치 | 저장 창 직전 실패 |
| v37 | 동일 실패 |
| 0.39 오버레이 안전 구조 | 저장·종료·재불러오기 성공 |

따라서 단순 폰트 크기나 저장 버퍼 초과가 원인이 아니었다. v20이 추가한 폭 계산 어댑터 `0xF790`과 v21의 능력치 재도색 헬퍼 `0xF7B0`가 `VMAZE.OVR`의 런타임 범위 `[0x5047, 0xFDAF)` 안에 있었다. 본게임 진입 후 오버레이가 헬퍼를 덮어썼고, 저장 대화상자가 손상된 폭 계산 코드를 호출하면서 그림 메모리 오류가 발생했다.

## 3. 0.39 수정(내부 빌드 v39)

관련 소스:

```text
tools/build_dos_v39_overlay_safe_resident.py
tools/audit_dos_overlay_resident_collisions.py
tests/test_build_dos_v39_overlay_safe_resident.py
src/dos_v39/root_helpers.S
src/dos_v39/font_dispatch.S
tools/prepare_dos_save_matrix.py
```

고정 크기 변경:

- 공용 폭 계산 어댑터: `0xF790` → root CS `0x38F4`
- 장면 후행 ASCII 어댑터: root CS `0x38F8`
- 능력치 재도색 헬퍼: `0xF7B0` → root CS `0x390C`
- 장면 검색/후행 문자 디스패처: resident `VBFONT0.VGA`의 `0x0AF0..0x0B6C`
- 폭 계산, 능력치 재도색, 장면 파서 호출을 새 resident 위치로 전부 재지정
- `0xF790`, `0xF7B0`, `0xFDB0`, `0xFDF0`의 오래된 고주소 헬퍼를 모두 제거
- 모든 root 헬퍼가 오버레이 시작 `0x5047` 아래에서 끝나고, 폰트 디스패처는 역테이블 `0x0D00` 전에 끝남
- `DS.EXE`, `VBFONT0.VGA`, 모든 OVR 파일의 바이트 크기 유지

정적 검증은 영구 실행 헬퍼가 root 오버레이 창 `0x5047+`에 하나도 남지 않았는지 확인한다. 가장 긴 `VMNPC.OVR`가 `0xFFC0`까지 확장돼도 새 root/폰트 헬퍼는 영향을 받지 않는다.

## 4. 런타임 저장 증거

검증에 사용한 보존 저장 파일:

```text
크기: 13,980 bytes
초기 SHA-256: 869DAC6F6ECB1B37BCBF48A395B45B5C4438E7BE8BEF7758EDC4E1ECB67CA3EE
```

0.39 `저장 & 계속` 후:

```text
SHA-256: 69FCD5529CC0AB9387AA0A240F8938CADB474FB5830CE9209E0BE4171E24EED2
결과: 본게임 복귀 성공
```

0.39 `저장 & 종료` 후:

```text
SHA-256: 1BA0DA218684C237E2F7BE9E813BE7295BA99E1F478C50E0009A4F331357DA98
결과: 메인 메뉴 복귀 성공
```

그 직후 `게임 불러오기`에서 같은 파일을 열어 `아스트랄 도미네의 무덤` 본게임 화면으로 다시 진입했다. 즉 파일 생성뿐 아니라 새 저장 데이터의 역직렬화까지 확인했다.

## 5. 빌드·테스트 결과

로컬 산출물:

```text
D:\Codex_Trans\Wizardry 7\outputs\Wizardry7_Korean_0.39_overlay_safe_resident.zip
SHA-256: 27DAA79C4F812D098ED98AE5BA8D7B089525211F7F0EFAF5FA92CFD2CB3ACC49
```

이 ZIP은 원본 게임에서 파생된 바이너리를 포함하므로 GitHub 릴리스 자산으로 업로드하지 않는다.

전체 테스트:

```text
python -m unittest discover -s tests -v
Ran 81 tests
OK
```

한글 경계 감사:

```text
passed: true
issue_count: 0
record_count: 11019
```

주요 0.39 해시:

```text
DS.EXE      54FA02F1E91B3086F2F8283FCBED07D21DA8A86285BE72C08806F23833B2D112
VBASE.OVR   C21FF28C56E2290D224D9D4CA0AB3B1D485B4803B1E1B3D036A9AFB1AD9C2612
VBFONT0.VGA CADAAAF4C25E9F807CD303770C5291CA3A1311511B9D1AE111439AD64D22DC35
VMAZE.OVR   D87269198EA5D31C9DA3D56B1A5E471510946810A7EC19E7D0A572906C974590
VMNPC.OVR   2B177CA905EE25A53D38ED1007B063935AAB4249DE03DDC02DB5DAF1BEAD7BF4
VPCMK.OVR   79B32BCF235F460A0C644F164983E9AD98537214BD18748EEBB16DA61D2DF2BF
VPCVW.OVR   F67888838C8EBB255804793C3E3788DAA6E557FB138FB95F5D1756D64603B690
VTREA.OVR   C34C993B93DBA7A8A106C1A9339FF47A54028B2E77E617F3CF615EE07A5F0F26
```

## 6. 라이브 설치와 복구

0.39의 19개 런타임 파일을 `D:\Wizardry 7\DSAVANT`에 설치했고 빌드 산출물과 해시가 모두 일치한다.

설치 전 v37 백업:

```text
D:\Wizardry 7\CODEX_BACKUP_BEFORE_V39_OVERLAY_SAFE_20260831_122430
```

라이브 폴더에는 진단용 `SAVEGAME.DBS`를 복사하지 않았다. 사용자의 실제 새 게임에서 저장하면 정상 경로에 생성된다.

## 7. GitHub와 저작권 규칙

- Git에는 빌더, 감사기, 테스트, 문서만 커밋한다.
- `D:\Wizardry 7.zip`, `DS.EXE`, OVR, DB, PIC, VGA, 생성된 패치 ZIP은 커밋하거나 릴리스 자산으로 올리지 않는다.
- GitHub 릴리스 `v0.39`는 소스 태그와 변경 설명만 제공한다.
- 바이너리 패치는 예상 원본 바이트와 해시를 검증하고 파일 크기를 유지한다.

## 8. 후속 작업 시 주의점

저장 결함은 해결됐지만 게임 전체의 모든 지역·NPC·전투 문장을 사람이 끝까지 검수한 것은 아니다. 추가 번역 QA를 할 때는 다음 원칙을 유지한다.

- 인코딩된 바이트 길이, 논리 글자 수, 화면 픽셀 폭을 구분한다.
- 새 resident 헬퍼를 `0x5047` 이상에 둘 때는 모든 호출 오버레이의 실제 끝 주소를 먼저 계산한다.
- `VMNPC.OVR`는 가장 길어 `0xFFC0`까지 확장된다는 점을 잊지 않는다.
- 오버레이 길이를 늘리지 않는다. v36에서 길이 변경이 오프닝 진행 회귀를 일으켰다.
- 새 변경은 원본 바이트 가드, 결과 해시, 고정 크기 테스트와 짧은 DOSBox 런타임 검증을 함께 추가한다.

## 9. 한 줄 인수인계

0.39(내부 빌드 v39)는 v20부터 저장 화면을 깨뜨리던 폭 계산 헬퍼뿐 아니라 장면 파서 헬퍼까지 모두 오버레이 창 밖의 resident 위치로 옮겼고, 저장·계속·종료·재불러오기까지 실제 DOSBox에서 성공했다. 이후 작업은 `fix/gog-launcher-playsoundw`의 `v0.39` 태그에서 시작하면 된다.
