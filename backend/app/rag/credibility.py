"""帖子可信度四维评分卡（★每维归一到 [0,1] 再加权，修复原版满分撞不过阈值的 bug）。

原版各维原始满分：creator 0.6 / content 0.75 / community 0.3 / freshness 1.0，
加权后最高仅 ≈0.64，撞不过 0.65 阈值。这里每维除以各自满分归一到 [0,1]，
final = 0.3*creator + 0.4*content + 0.2*community + 0.1*freshness ∈ [0,1]。
"""
from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

from .models import CredibilityScore

AD_KEYWORDS = ["合作", "赞助", "广告", "推广", "福利", "抽奖", "品牌方", "商单", "恰饭", "植入", "代言"]
STRUCTURED_PATTERNS = [
    r"地址[：:]", r"营业时间[：:]", r"票价[：:]", r"门票[：:]", r"价格[：:]",
    r"人均[：:]", r"交通[：:]", r"路线[：:]", r"\d+路[公交地]车", r"地铁\d+号线",
]

# 各维子分满分（用于归一化）
_CREATOR_MAX = 0.6
_CONTENT_MAX = 0.75
_COMMUNITY_MAX = 0.3


class CredibilityCalculator:
    def __init__(self, creator_w=0.3, content_w=0.4, community_w=0.2, freshness_w=0.1,
                 max_age_days=730, min_images=3, min_desc_len=200):
        self.creator_w, self.content_w = creator_w, content_w
        self.community_w, self.freshness_w = community_w, freshness_w
        self.max_age_days, self.min_images, self.min_desc_len = max_age_days, min_images, min_desc_len

    def calculate(self, post: dict[str, Any]) -> CredibilityScore:
        creator, cd = self._creator(post)
        content, cnd = self._content(post)
        community, cmd = self._community(post)
        freshness, fd = self._freshness(post)
        # ★归一化：每维 /各自满分
        creator_n = creator / _CREATOR_MAX
        content_n = content / _CONTENT_MAX
        community_n = community / _COMMUNITY_MAX
        final = (creator_n * self.creator_w + content_n * self.content_w
                 + community_n * self.community_w + freshness * self.freshness_w)
        return CredibilityScore(
            final=round(final, 3), creator=round(creator_n, 3), content=round(content_n, 3),
            community=round(community_n, 3), freshness=round(freshness, 3),
            details={"creator": cd, "content": cnd, "community": cmd, "freshness": fd},
        )

    def _creator(self, p):
        s, d = 0.0, {}
        if p.get("is_verified", False):
            s += 0.3
        f = p.get("followers", 0) or 0
        fs = min(0.2, 0.2 * math.log10(f + 1) / math.log10(50001))
        s += fs
        if (p.get("report_rate", 0) or 0) < 0.05:
            s += 0.1
        d["follower_score"] = round(fs, 3)
        return s, d

    def _content(self, p):
        s, d = 0.0, {}
        ic = p.get("image_count", len(p.get("image_urls", []) or []))
        if ic >= self.min_images and p.get("has_real_photos", True):
            s += 0.25
        desc = p.get("desc", "") or p.get("content", "") or ""
        if len(desc) > self.min_desc_len:
            s += 0.15
        if any(re.search(pat, desc) for pat in STRUCTURED_PATTERNS):
            s += 0.2
        if not any(k in desc.lower() for k in AD_KEYWORDS):
            s += 0.15
        d["image_count"], d["desc_len"] = ic, len(desc)
        return s, d

    def _community(self, p):
        s, d = 0.0, {}
        likes = p.get("likes", 0) or 0
        collects = p.get("collects", 0) or 0
        ratio = collects / max(likes, 1)
        if ratio > 0.3:
            s += 0.2
        useful = p.get("useful_comments_ratio", 0.5)
        useful_ok = useful >= 0.5  # ★修复：原版 >0.5 + 默认 0.5 → 永不得分
        if useful_ok:
            s += 0.1
        d["engagement_ratio"] = round(ratio, 3)
        d["useful_ok"] = useful_ok
        return s, d

    def _freshness(self, p):
        d = {}
        pt = p.get("publish_time")
        if pt is None:
            days = 365
        elif isinstance(pt, (int, float)):
            days = (datetime.now() - datetime.fromtimestamp(pt)).days
        elif isinstance(pt, datetime):
            days = (datetime.now() - pt).days
        else:
            days = 365
        score = max(0.0, 1.0 - days / self.max_age_days)
        d["days_old"] = days
        return score, d
