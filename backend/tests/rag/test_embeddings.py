from app.rag.embeddings import SparseEncoder


def test_sparse_encoder_tokenizes_chinese():
    enc = SparseEncoder()
    v = enc.encode("北京免费的公园")
    # 至少切出 公园/免费/北京 这类词，indices 与 values 等长
    assert len(v.indices) == len(v.values)
    assert len(v.indices) >= 2


def test_sparse_same_token_same_id_cross_call():
    enc = SparseEncoder()
    a = enc.encode("公园")
    b = enc.encode("公园 公园")
    assert a.indices[0] == b.indices[0]          # 确定性 id
    assert b.values[0] == 2.0                      # 词频累加


def test_sparse_empty_text():
    assert SparseEncoder().encode("").indices == []
