"""직무(persona)별 골드셋 파일을 하나의 통합본 all.jsonl로 빌드한다.

저장은 직무별(backend.jsonl, frontend.jsonl, …)로 나누고, 평가 실행은 통합본
all.jsonl 기준으로 한다. 직무/난이도/intent/hop 태그가 모두 들어있으므로, 평가
후 어느 축으로든 점수를 쪼개 볼 수 있다.

사용:
    python eval/build_goldset.py            # eval/goldset/all.jsonl 생성
    python eval/build_goldset.py --check    # 빌드 없이 일관성만 점검
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

GOLDSET_DIR = Path(__file__).parent / "goldset"
OUT = GOLDSET_DIR / "all.jsonl"


def load_persona_files() -> list[dict]:
    records: list[dict] = []
    for path in sorted(GOLDSET_DIR.glob("*.jsonl")):
        if path.name == OUT.name:
            continue  # 생성물은 입력에서 제외
        persona_from_name = path.stem
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            # 파일명과 persona 필드가 어긋나면 사고 → 즉시 알림
            if rec.get("persona") != persona_from_name:
                raise SystemExit(
                    f"{path.name}:{lineno} persona='{rec.get('persona')}' 인데 파일명은 '{persona_from_name}'"
                )
            records.append(rec)
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description="직무별 골드셋 → all.jsonl 통합 빌드")
    ap.add_argument("--check", action="store_true", help="빌드하지 않고 일관성만 점검")
    args = ap.parse_args()

    records = load_persona_files()

    # id 중복 점검
    dup = [rid for rid, n in Counter(r["id"] for r in records).items() if n > 1]
    if dup:
        print(f"✗ 중복 id: {dup}")
        return 1

    if not args.check:
        with OUT.open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 분해 통계 — 평가 시 어느 축으로 쪼갤 수 있는지 미리 보여줌
    print(f"{'생성' if not args.check else '점검'}: {len(records)}문항 → {OUT.relative_to(Path.cwd()) if not args.check else '(check)'}")
    for axis in ("persona", "intent", "difficulty", "hop"):
        dist = dict(sorted(Counter(r.get(axis) for r in records).items(), key=lambda x: -x[1]))
        print(f"  {axis:11}: {dist}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
