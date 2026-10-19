"""SU-3.2 中文领域分词与本地 BM25 测试（离线）。"""

from pathlib import Path

from app.rag.pipeline import text_tokenizer as tk


def test_domain_terms_are_loaded():
    terms = tk.load_domain_terms()
    assert terms
    assert "番茄炒蛋" in terms
    assert "红烧肉" in terms


def test_domain_dish_name_is_not_split():
    tokens = tk.tokenize("番茄炒蛋怎么做")
    assert "番茄炒蛋" in tokens
    assert "番茄" not in tokens
    assert "炒蛋" not in tokens


def test_stopwords_are_removed():
    tokens = tk.tokenize("我想做一个简单的番茄炒蛋")
    assert "我" not in tokens
    assert "想" not in tokens
    assert "一个" not in tokens
    assert "的" not in tokens
    assert "番茄炒蛋" in tokens


def test_stopwords_can_be_kept():
    tokens = tk.tokenize("我想做番茄炒蛋", drop_stopwords=False)
    assert "我" in tokens
    assert "想" in tokens


def test_empty_input_returns_empty_list():
    assert tk.tokenize("") == []
    assert tk.tokenize("   ") == []
    assert tk.tokenize(None) == []


def test_punctuation_is_dropped():
    tokens = tk.tokenize("番茄炒蛋，好吃！")
    assert "，" not in tokens
    assert "！" not in tokens
    assert "番茄炒蛋" in tokens


def test_latin_tokens_are_lowercased():
    tokens = tk.tokenize("BBQ Chicken")
    assert "bbq" in tokens
    assert "chicken" in tokens


def test_bm25_rank_puts_matching_doc_first():
    docs = [
        "清蒸鲈鱼的做法：鲈鱼处理干净后上锅蒸八分钟。",
        "红烧肉需要五花肉、冰糖和酱油，小火慢炖。",
        "番茄炒蛋：先把鸡蛋炒散，再下番茄翻炒。",
    ]
    ranked = tk.bm25_rank("番茄炒蛋怎么做", docs, top_k=3)

    assert ranked[0][0] == 2
    assert ranked[0][1] > 0
    assert ranked[0][1] >= ranked[1][1] >= ranked[2][1]


def test_bm25_scores_length_matches_docs():
    docs = ["红烧肉", "番茄炒蛋", ""]
    scores = tk.bm25_scores("红烧肉", docs)

    assert len(scores) == 3
    assert scores[0] > 0


def test_bm25_scores_empty_docs():
    assert tk.bm25_scores("红烧肉", []) == []


def test_bm25_scores_empty_query_returns_zeros():
    assert tk.bm25_scores("", ["红烧肉", "番茄炒蛋"]) == [0.0, 0.0]


def test_bm25_rank_top_k_zero_returns_empty():
    assert tk.bm25_rank("红烧肉", ["红烧肉"], top_k=0) == []
    assert tk.bm25_rank("红烧肉", ["红烧肉"], top_k=-1) == []


def test_bm25_rank_top_k_truncates():
    docs = ["红烧肉", "番茄炒蛋", "清蒸鱼"]
    assert len(tk.bm25_rank("红烧肉", docs, top_k=2)) == 2


def test_missing_dict_degrades_gracefully(monkeypatch):
    missing = Path(__file__).resolve().parent / "_no_such_domain_dict_.txt"
    assert not missing.exists()

    monkeypatch.setattr(tk, "DOMAIN_DICT_PATH", missing)
    monkeypatch.setattr(tk, "_dict_loaded", False)
    tk.load_domain_terms.cache_clear()

    try:
        assert tk.load_domain_terms() == ()
        tokens = tk.tokenize("番茄炒蛋怎么做")
        assert tokens
    finally:
        tk.load_domain_terms.cache_clear()
        monkeypatch.undo()
        tk._dict_loaded = False
