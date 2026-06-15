#!/usr/bin/env python
"""把 xhs JSON 导入 Qdrant。用法：python scripts/rag_import.py --data out/rag/xhs_beijing.json"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="JSON 文件或目录")
    args = ap.parse_args()

    from app.rag.config import RAGConfig
    from app.rag.embeddings import EmbeddingService, ModelScopeDenseEmbedder
    from app.rag.importer import RAGImporter, load_posts
    from app.rag.vector_store import QdrantVectorStore

    cfg = RAGConfig.from_env()
    store = QdrantVectorStore(cfg)
    store.ensure_collection()
    emb = EmbeddingService(dense=ModelScopeDenseEmbedder(cfg))
    stats = RAGImporter(cfg, emb, store).import_posts(load_posts(args.data))
    print(f"导入完成：{stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
