"""RAG 평가 러너 — 골드셋 all.jsonl을 봇 파이프라인에 통과시켜 채점한다.

문항마다 봇 핸들러를 헤드리스로 재현한다(Slack만 제외):
  classify_intent → retrieve(top_k=5) → answer*/answer_project/answer_general → judge(gpt-4o)

측정 지표:
  - Retrieval@5  : gold_files 가 상위 5개 chunk의 파일집합에 들어왔는가 (fraction)
  - Hit@1        : 검색 1순위 파일이 gold_file 인가
  - Correctness  : gpt-4o judge 0~5
  - IntentAcc    : classify_intent 가 gold intent 와 일치하는가

전체 평균과 persona/intent/difficulty/hop 축별 분해를 함께 낸다.
결과는 eval/results/<tag>/ 아래 per_question.jsonl + summary.{json,md} 로 저장.

사용:
  python eval/run_eval.py --tag v0
  python eval/run_eval.py --tag smoke --limit 5        # 빠른 점검
  python eval/run_eval.py --tag v0 --no-index          # 인덱싱 건너뛰기(이미 됨)
"""

from __future__ import annotations

import sys
from pathlib import Path

# repo 루트를 path 에 올려 `python -m eval.run_eval` / `python eval/run_eval.py` 양쪽 지원
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import json
import logging
import statistics
from collections import defaultdict
from datetime import datetime, timezone

import config
from agent import (
    retrieve,
    classify_intent,
    answer,
    answer_project,
    answer_general,
    StructuredAnswer,
)
from eval.judge import judge_answer, JUDGE_MODEL

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("eval")

GOLDSET_DEFAULT = Path(__file__).parent / "goldset" / "all.jsonl"
RESULTS_DIR = Path(__file__).parent / "results"
AXES = ("persona", "intent", "difficulty", "hop")


def render_answer(obj) -> str:
    """봇 답변(StructuredAnswer 또는 str)을 judge가 읽을 평문으로 변환."""
    if isinstance(obj, StructuredAnswer):
        return (
            f"[패턴] {obj.pattern}\n"
            f"[근거] {obj.rationale}\n"
            f"[장점] {', '.join(obj.pros)}\n"
            f"[단점] {', '.join(obj.cons)}\n"
            f"[적합] {obj.best_for}\n"
            f"[신뢰도] {obj.confidence}\n"
            f"[참조] {', '.join(obj.code_refs)}"
        )
    return str(obj)


def ordered_unique_files(chunks) -> list[str]:
    """검색된 chunk를 파일 단위로 환원(첫 등장 순서 유지 = 랭킹)."""
    seen: list[str] = []
    for c in chunks:
        if c.file_path and c.file_path not in seen:
            seen.append(c.file_path)
    return seen


def retrieval_metrics(gold_files: list[str], retrieved_files: list[str]) -> dict:
    """gold_files 가 없으면(none-hop 등) retrieval 지표는 N/A."""
    if not gold_files:
        return {"recall": None, "hit1": None, "all_found": None}
    gold = set(gold_files)
    found = gold & set(retrieved_files)
    return {
        "recall": len(found) / len(gold),                       # 부분 점수
        "all_found": len(found) == len(gold),                   # multi-hop AND 충족
        "hit1": bool(retrieved_files) and retrieved_files[0] in gold,
    }


def run_one(record: dict, repo, top_k: int) -> dict:
    q = record["question"]
    gold_intent = record.get("intent")

    pred_intent = classify_intent(q)
    chunks = retrieve(q, repo.chroma_dir, repo.collection_name, top_k=top_k)
    retrieved_files = ordered_unique_files(chunks)
    rm = retrieval_metrics(record.get("gold_files") or [], retrieved_files)

    # 봇 핸들러 디스패치를 예측 intent 기준으로 재현(엔드투엔드)
    if pred_intent == "project":
        ans_obj = answer_project(q, chunks, repo.display_name, repo.github_url)
    elif pred_intent == "chat":
        ans_obj = answer_general(q, repo.display_name, repo.github_url)
    else:  # code
        ans_obj = answer(q, chunks, repo.display_name)
    ans_text = render_answer(ans_obj)

    jr = judge_answer(record, ans_text)

    return {
        "id": record["id"],
        "persona": record.get("persona"),
        "intent_gold": gold_intent,
        "intent_pred": pred_intent,
        "intent_correct": pred_intent == gold_intent,
        "difficulty": record.get("difficulty"),
        "hop": record.get("hop"),
        "question": q,
        "gold_files": record.get("gold_files"),
        "retrieved_files": retrieved_files,
        "recall": rm["recall"],
        "all_found": rm["all_found"],
        "hit1": rm["hit1"],
        "correctness": jr.score,
        "judge_reason": jr.reason,
        "judge_satisfied": jr.satisfied,
        "judge_violations": jr.violations,
        "answer": ans_text,
    }


def _mean(vals: list) -> float | None:
    vals = [v for v in vals if v is not None]
    return round(statistics.mean(vals), 3) if vals else None


def aggregate(rows: list[dict]) -> dict:
    def block(rs: list[dict]) -> dict:
        return {
            "n": len(rs),
            "recall@5": _mean([r["recall"] for r in rs]),
            "all_found@5": _mean([1.0 if r["all_found"] else 0.0 for r in rs if r["all_found"] is not None]),
            "hit@1": _mean([1.0 if r["hit1"] else 0.0 for r in rs if r["hit1"] is not None]),
            "correctness": _mean([r["correctness"] for r in rs]),
            "intent_acc": _mean([1.0 if r["intent_correct"] else 0.0 for r in rs]),
        }

    summary: dict = {"overall": block(rows), "by": {}}
    for axis in AXES:
        groups: dict[str, list] = defaultdict(list)
        for r in rows:
            key = r.get("intent_gold") if axis == "intent" else r.get(axis)
            groups[str(key)].append(r)
        summary["by"][axis] = {k: block(v) for k, v in sorted(groups.items())}
    return summary


def to_markdown(summary: dict, meta: dict) -> str:
    def line(name: str, b: dict) -> str:
        def f(x):
            return "  –  " if x is None else f"{x:.2f}"
        return (f"| {name} | {b['n']} | {f(b['recall@5'])} | {f(b['all_found@5'])} "
                f"| {f(b['hit@1'])} | {f(b['correctness'])} | {f(b['intent_acc'])} |")

    header = "| group | n | Recall@5 | AllFound@5 | Hit@1 | Correct(0-5) | IntentAcc |\n" \
             "|---|---|---|---|---|---|---|"
    out = [
        f"# RAG Eval — {meta['tag']}",
        f"- run: {meta['timestamp']}  |  repo: {meta['repo']}  |  judge: {meta['judge_model']}  "
        f"|  top_k={meta['top_k']}  |  n={summary['overall']['n']}",
        "",
        header,
        line("**OVERALL**", summary["overall"]),
    ]
    for axis in AXES:
        out.append(f"| _by {axis}_ | | | | | | |")
        for k, b in summary["by"][axis].items():
            out.append(line(k, b))
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="RAG 평가 러너")
    ap.add_argument("--tag", default="v0", help="결과 폴더 이름 (eval/results/<tag>)")
    ap.add_argument("--goldset", type=Path, default=GOLDSET_DEFAULT)
    ap.add_argument("--repo", default="REPO_A", help="config 의 repo name (기본 Leadership=REPO_A)")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0, help="앞 N개만 (0=전체)")
    ap.add_argument("--no-index", action="store_true", help="인덱싱 건너뛰기")
    args = ap.parse_args()

    if not config.OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY 미설정 — 검색/답변/judge 호출 불가. .env 또는 환경변수 설정 필요.")
        return 2

    repo = next((r for r in config.load_repos() if r.name == args.repo), None)
    if repo is None:
        logger.error("repo '%s' 를 config 에서 못 찾음", args.repo)
        return 2

    config.ensure_dirs()
    if not args.no_index:
        from scheduler.reindexer import initial_index_if_empty
        logger.info("인덱스 확인/생성: %s", repo.name)
        initial_index_if_empty(repo)

    records = [json.loads(l) for l in args.goldset.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        records = records[: args.limit]
    logger.info("%d 문항 평가 시작 (judge=%s, top_k=%d)", len(records), JUDGE_MODEL, args.top_k)

    rows: list[dict] = []
    for i, rec in enumerate(records, 1):
        try:
            rows.append(run_one(rec, repo, args.top_k))
        except Exception:
            logger.exception("[%s] 평가 실패", rec.get("id"))
            rows.append({**{k: None for k in (
                "persona", "intent_gold", "intent_pred", "intent_correct", "difficulty",
                "hop", "recall", "all_found", "hit1", "correctness")},
                "id": rec.get("id"), "question": rec.get("question"),
                "judge_reason": "RUNNER ERROR", "answer": ""})
        logger.info("  (%d/%d) %s", i, len(records), rec.get("id"))

    summary = aggregate([r for r in rows if r.get("correctness") is not None])
    meta = {
        "tag": args.tag,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo": repo.name,
        "judge_model": JUDGE_MODEL,
        "top_k": args.top_k,
    }

    out_dir = RESULTS_DIR / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "per_question.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out_dir / "summary.json").write_text(
        json.dumps({"meta": meta, "summary": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
    md = to_markdown(summary, meta)
    (out_dir / "summary.md").write_text(md, encoding="utf-8")

    print("\n" + md)
    logger.info("결과 저장: %s", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
