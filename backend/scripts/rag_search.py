#!/usr/bin/env python
"""检索验证。用法：python scripts/rag_search.py --query "北京免费公园" --top-k 5"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--city", default=None)
    args = ap.parse_args()

    from app.rag.service import RAGService
    svc = RAGService.from_env()
    for r in svc.search(args.query, top_k=args.top_k, city=args.city):
        print(f"[{r.score:.3f}] cred={r.credibility} | {r.title}  {r.url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
