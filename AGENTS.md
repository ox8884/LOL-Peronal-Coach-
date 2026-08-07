# lol-coach — 작업 규칙 (AGENTS.md)

## 필수 워크플로: 사용자-facing 릴리스 커밋

**기능/버그픽스를 배포용으로 커밋·푸시할 때는 아래 3가지를 함께 완료한다.**

1. **README.md** — `### vX.Y.Z` 릴리스 노트 섹션에 이번 변경 요약 작성
2. **docs/features.html** — 기능 소개 페이지에 해당 변경 반영 (신규 섹션/카드/수치 갱신)
3. **exe 재빌드** — `scripts/build_exe.ps1` (그리고 `scripts/build_installer.ps1`) 실행

순서 (권장):
```
README 작성 → 버전 갱신(scripts/release.py --version X.Y.Z --skip-build) →
features.html 반영 → 빌드(build_exe.ps1 → build_installer.ps1) → 커밋 → 푸시
```

### 예외 (전체 릴리스 세트 생략 가능)

- `chore:` / 순수 리팩터 / 테스트만 / 내부 문서(AGENTS·BUILD)만 — **버전 올리기·exe 빌드 생략 가능**
- 단, 사용자에게 보이는 동작·UI·설치본이 바뀌면 예외 없음

부가 규칙:
- 버전은 이전 버전의 다음 패치 (예: 1.6.0 → 1.6.1). `release.py`가 pyproject/`__init__.py`/`롤실전코치.iss`/features.html 버전/`BUILD.md`를 일괄 갱신
- 커밋 메시지: 한국어, `feat:`/`fix:`/`docs:`/`chore:` 프리픽스 + 상세 요약
- GitHub Release(태그 + 인스톨러 + **`.sha256` 사이드카**)는 사용자가 명시할 때만. 커밋 시점엔 로컬 빌드까지만
- `release.py`의 `github_release()`가 인스톨러와 함께 `LOL-Coach-Setup-vX.Y.Z.exe.sha256` 을 업로드한다
- API 키/비밀은 저장소에 절대 커밋 금지 (`.env`는 .gitignore됨, 키는 런타임에 각 사용자 PC에서만)
