# lol-coach — 작업 규칙 (AGENTS.md)

## 필수 워크플로: 커밋 = 릴리스 세트

**코드를 커밋하고 푸시할 때는 반드시 아래 3가지를 항상 함께 완료한다.**
예외 없음. 코드만 푸시하는 것은 금지.

1. **README.md** — `### vX.Y.Z` 릴리스 노트 섹션에 이번 변경 요약 작성
2. **docs/features.html** — 기능 소개 페이지에 해당 변경 반영 (신규 섹션/카드/수치 갱신)
3. **exe 재빌드** — `scripts/build_exe.ps1` (그리고 `scripts/build_installer.ps1`) 실행

순서 (권장):
```
README 작성 → 버전 갱신(scripts/release.py --version X.Y.Z --skip-build) →
features.html 반영 → 빌드(build_exe.ps1 → build_installer.ps1) → 커밋 → 푸시
```

부가 규칙:
- 버전은 이전 버전의 다음 패치 (예: 1.6.0 → 1.6.1). `release.py`가 pyproject/`__init__.py`/`롤실전코치.iss`/features.html 버전/`BUILD.md`를 일괄 갱신
- 커밋 메시지: 한국어, `feat:`/`fix:`/`docs:` 프리픽스 + 상세 요약
- GitHub Release(태그+자산 업로드)는 사용자가 명시할 때만. 커밋 시점엔 로컬 빌드까지만
- API 키/비밀은 저장소에 절대 커밋 금지 (`.env`는 .gitignore됨, 키는 런타임에 각 사용자 PC에서만)
