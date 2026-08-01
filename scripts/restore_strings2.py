"""한글 substring subsequBP 매칭으로 깨진 app.py 부분 복구."""

import marshal
import re
import sys
from collections import defaultdict

APP_PATH = "src/lol_coach/gui/app.py"
PYC_LOCAL = "src/lol_coach/gui/__pycache__/app.cpython-312.pyc"

# 1) PYC에서 모든 한국어 문자열 추출 (정상)
with open(PYC_LOCAL, "rb") as f:
    pyc_data = f.read()
co = marshal.loads(pyc_data[16:])


def walk_strings(co, acc):
    for c in co.co_consts:
        if isinstance(c, str) and c:
            acc.add(c)
        if hasattr(c, "co_consts"):
            walk_strings(c, acc)


all_strings = set()
walk_strings(co, all_strings)
korean_strings = [s for s in all_strings if any("\uac00" <= ch <= "\ud7a3" for ch in s)]
print(f"PYC strings: korean={len(korean_strings)} total={len(all_strings)}")

# 2) 깨진 app.py 읽기
with open(APP_PATH, "rb") as f:
    data = f.read()
text = data.decode("utf-8", errors="replace")

# 3) 매칭 helper: 깨진 부분의 글자와 PYC 정상 string의 해당 글자가
#    - 둘 다 ASCII 같은 종류인 경우 같아야 함
#    - 한쪽이 ASCII, 다른 쪽이 한국어 -> mismatch (낮은 점수)
#    - 한국어 또는 `?` 또는 `U+FFFD` 는 모두 'unmapped non-ascii'로 처리하여 일치


def classify(ch):
    if ord(ch) < 128:
        return ("ascii", ch)
    return ("ko", ch)


def broken_to_struct(s):
    """깨진 str에서 한국어 영역의 ASCII 양끝 anchor 추출: anchor_seq."""
    # ASCII segment 시퀀스 추출 + position 힌트
    anchors = []
    for m in re.finditer(r"[\x20-\x7e]+", s):
        anchors.append((m.start(), m.end(), m.group()))
    return anchors


def pyc_anchors(s):
    anchors = []
    for m in re.finditer(r"[\x20-\x7e]+", s):
        anchors.append((m.start(), m.end(), m.group()))
    return anchors


# 각 PYC string에 대해 anchor 시퀀스 캐싱
pyc_anchor_db = [(s, broken_to_struct(s)) for s in korean_strings]
# 길이당 인덱싱
by_len = defaultdict(list)
for s, anchors in pyc_anchor_db:
    by_len[len(s)].append((s, anchors))

# 깨진 따옴표 안 블록들
broken_pattern = re.compile(r'"((?:[^"\\]|\\.)*)"')
all_matches = list(broken_pattern.finditer(text))
print(f"all quoted blocks: {len(all_matches)}")

# 깨진 block 식별: U+FFFD 또는 한국어/영문 혼재하는 잘린 패턴
def is_garbled(s):
    return "\ufffd" in s or (any("\uac00" <= c <= "\ud7a3" for c in s) and "?" in s)


broken_matches = [m for m in all_matches if is_garbled(m.group(1))]
print(f"garbled quoted blocks: {len(broken_matches)}")


def match_score(broken, pyc_str):
    """block 길이 가 animal OK + anchor 시퀀스 일치율."""
    bs = broken_to_struct(broken)
    ps = broken_to_struct(pyc_str)
    # anchor 개수 불일치면 skip (but partial 깨짐에 의해 영어가 잘렸을 수 있으니까
    # anchor 개수가 같으면 가장 높은 점수, 부분 집합이면 차등 점수)
    score = 0
    # 1) anchor 시퀀스 매칭 — 동일 anchor word의 개수
    pa = [a[2] for a in ps]
    ba = [a[2] for a in bs]
    # 큼직한 ASCII 영어 전체 시퀀스 일치 검사
    if pa == ba:
        score += 1000
    elif set(pa) >= set(ba):
        # partial — bs는 ps의 subsequence of anchors
        i = 0
        seq_ok = True
        for b in ba:
            while i < len(pa) and pa[i] != b:
                i += 1
            if i >= len(pa) or pa[i] != b:
                seq_ok = False
                break
            i += 1
        if seq_ok:
            score += 500
    # 길이 차이 패널티
    score -= abs(len(broken) - len(pyc_str))
    return score


# 각 broken block에 대해 PYC string 중 가장 점수 높은 것 선택
replaced = 0
unreplaced = []
result_parts = []
last_end = 0
for m in broken_matches:
    result_parts.append(text[last_end:m.start()])
    broken_inner = m.group(1)
    best_score = -1
    best_str = None
    # 길이 근접한 PYC string만 후보로 검사
    for delta in (0, 1, -1, 2, -2, 3, -3, 4, -4):
        candidates = by_len.get(len(broken_inner) + delta, [])
        for s, _anchors in candidates:
            sc = match_score(broken_inner, s)
            if sc > best_score:
                best_score = sc
                best_str = s
        if best_score > 500:
            break
    if best_str is not None and best_score > 0:
        result_parts.append('"' + best_str + '"')
        replaced += 1
    else:
        result_parts.append(m.group(0))
        unreplaced.append((m.start(), broken_inner[:120]))
    last_end = m.end()
result_parts.append(text[last_end:])
new_text = "".join(result_parts)

# 저장
with open(APP_PATH, "w", encoding="utf-8") as f:
    f.write(new_text)

print(f"replaced: {replaced}, unreplaced: {len(unreplaced)}")
print(f"remaining U+FFFD: {new_text.count(chr(0xfffd))}")
for pos, txt in unreplaced[:30]:
    sys.stdout.buffer.write(f"  ~{pos}: {txt!r}\n".encode())
