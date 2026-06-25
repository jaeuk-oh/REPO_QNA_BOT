"""골드셋 무결성 검증기 (사람 손 안 타는 기계 검증 단계).

각 골드 레코드에 대해:
  1. gold_files 가 대상 레포에 실제로 존재하는지
  2. gold_symbols 가 해당 파일에 실제로 정의돼 있는지 (AST 파싱)
를 확인한다. LLM이 생성/작성한 골드셋의 '존재하지 않는 파일/함수' 환각을
배포 전에 차단하는 게 목적이다. 정답성(must_include 등)은 여기서 보지 않는다.

사용:
    python eval/verify_goldset.py \
        --goldset eval/goldset/api_backend.jsonl \
        --repo-root /path/to/Leadership-Training-Service
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path


def collect_defined_symbols(source: str) -> set[str]:
    """파일에서 참조 가능한 모든 심볼 이름을 수집한다.

    - 함수/비동기함수/클래스: 중첩·메서드 포함 (ast.walk)
    - 모듈 레벨 상수: 단순 대입(Assign)과 타입주석 대입(AnnAssign)의 이름
    """
    tree = ast.parse(source)
    names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)

    # 모듈 최상위 대입만 상수로 인정 (MAX_TURNS_PER_SESSION, EVALUATION_PROMPT 등)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)

    return names


def verify(goldset_path: Path, repo_root: Path) -> int:
    records = []
    with goldset_path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append((lineno, json.loads(line)))
            except json.JSONDecodeError as e:
                print(f"  ✗ line {lineno}: JSON 파싱 실패 — {e}")
                return 2

    symbol_cache: dict[Path, set[str]] = {}
    failures: list[str] = []
    file_checks = symbol_checks = 0
    seen_ids: set[str] = set()

    VALID_INTENT = {"code", "project", "chat"}
    VALID_HOP = {"single", "multi", "none"}
    VALID_DIFF = {"easy", "medium", "hard"}

    for lineno, rec in records:
        rid = rec.get("id", f"line{lineno}")
        if rid in seen_ids:
            failures.append(f"[{rid}] 중복 id")
        seen_ids.add(rid)

        # 스키마: 필수 필드 + enum 값 검증
        if rec.get("intent") not in VALID_INTENT:
            failures.append(f"[{rid}] intent 누락/오류: {rec.get('intent')!r}")
        if rec.get("hop") not in VALID_HOP:
            failures.append(f"[{rid}] hop 누락/오류: {rec.get('hop')!r}")
        if rec.get("difficulty") not in VALID_DIFF:
            failures.append(f"[{rid}] difficulty 누락/오류: {rec.get('difficulty')!r}")
        if not str(rec.get("question", "")).strip():
            failures.append(f"[{rid}] question 비어있음")
        # hop은 gold_files 개수와 일관돼야 함
        n = len(rec.get("gold_files", []))
        expected_hop = "none" if n == 0 else "single" if n == 1 else "multi"
        if rec.get("hop") != expected_hop:
            failures.append(f"[{rid}] hop={rec.get('hop')} 인데 gold_files {n}개 (기대: {expected_hop})")

        for rel in rec.get("gold_files", []):
            file_checks += 1
            path = repo_root / rel
            if not path.is_file():
                failures.append(f"[{rid}] 파일 없음: {rel}")
                continue

            if path not in symbol_cache:
                try:
                    symbol_cache[path] = collect_defined_symbols(
                        path.read_text(encoding="utf-8")
                    )
                except SyntaxError as e:
                    failures.append(f"[{rid}] {rel} 파싱 실패: {e}")
                    symbol_cache[path] = set()

        # 심볼은 같은 레코드의 gold_files 어딘가에 존재하면 통과
        available: set[str] = set()
        for rel in rec.get("gold_files", []):
            available |= symbol_cache.get(repo_root / rel, set())

        for sym in rec.get("gold_symbols", []):
            symbol_checks += 1
            if sym not in available:
                files = ", ".join(rec.get("gold_files", [])) or "(없음)"
                failures.append(f"[{rid}] 심볼 '{sym}' 미발견 (탐색: {files})")

    print(f"레코드 {len(records)}개 | 파일 검증 {file_checks} | 심볼 검증 {symbol_checks}")
    if failures:
        print(f"\n✗ 검증 실패 {len(failures)}건:")
        for msg in failures:
            print(f"  - {msg}")
        return 1

    print("✓ 모든 gold_file 존재 + 모든 gold_symbol 정의 확인")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="골드셋 무결성(파일/심볼 존재) 검증")
    p.add_argument("--goldset", required=True, type=Path)
    p.add_argument("--repo-root", required=True, type=Path,
                   help="골드셋이 가리키는 대상 레포의 루트")
    args = p.parse_args()

    if not args.goldset.is_file():
        print(f"골드셋 파일 없음: {args.goldset}")
        return 2
    if not args.repo_root.is_dir():
        print(f"레포 루트 없음: {args.repo_root}")
        return 2

    return verify(args.goldset, args.repo_root)


if __name__ == "__main__":
    sys.exit(main())
