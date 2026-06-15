from app.rag.credibility import CredibilityCalculator

C = CredibilityCalculator()

PERFECT = {
    "is_verified": True, "followers": 100000, "report_rate": 0.0,
    "image_count": 9, "desc": "地址：北京 营业时间：9-17 " + "好玩" * 200,
    "likes": 100, "collects": 60, "comments": 30,
    "useful_comments_ratio": 0.9,
    "publish_time": __import__("time").time(),  # 当下
}


def test_perfect_post_can_pass_065_threshold():
    """★核心：修复后满分可达 1.0，0.65 阈值才有意义（原版最高≈0.64）。"""
    s = C.calculate(PERFECT)
    assert s.final > 0.65
    assert 0.0 <= s.final <= 1.0


def test_each_dimension_normalized_0_1():
    s = C.calculate(PERFECT)
    for v in (s.creator, s.content, s.community, s.freshness):
        assert 0.0 <= v <= 1.0


def test_useful_comments_ratio_default_no_longer_breaks():
    """★修复：默认 0.5 用 >=0.5 判定应得分（原版 >0.5 永远拿不到）。"""
    post = dict(PERFECT)
    post.pop("useful_comments_ratio")  # 走默认 0.5
    s = C.calculate(post)
    assert s.details["community"]["useful_ok"] is True


def test_low_quality_post_below_threshold():
    poor = {"is_verified": False, "followers": 5, "report_rate": 0.2,
            "image_count": 0, "desc": "好", "likes": 1, "collects": 0,
            "comments": 0, "useful_comments_ratio": 0.0, "publish_time": None}
    assert C.calculate(poor).final < 0.65
