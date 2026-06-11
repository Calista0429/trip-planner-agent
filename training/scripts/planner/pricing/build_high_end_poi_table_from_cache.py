"""Build/extend the curated high-end POI table from local Amap cache only.

This script never calls Amap. It reads cached `/place/text` responses and
extracts auditable high-end candidates for long-tail cities.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CACHE_DIR = PROJECT_ROOT / "training/data/cache/planner_context/amap_api/place_text"
DEFAULT_TABLE = PROJECT_ROOT / "backend/app/planner/high_end_poi_table.json"

SOURCE_PROVIDER = "amap_place_text_cache"
SOURCE_COLLECTED_AT = "2026-05-11"
DEFAULT_MAX_PER_CITY_CATEGORY = 6

MAJOR_CITY_BLOCKLIST = {
    "北京",
    "上海",
    "广州",
    "深圳",
    "杭州",
    "成都",
    "西安",
    "南京",
    "苏州",
    "重庆",
}
FOOD_HIGH_END_KEYWORDS = [
    "米其林",
    "黑珍珠",
    "omakase",
    "Omakase",
    "法餐",
    "高端餐厅",
    "高端",
    "商务宴请",
    "商务餐厅",
    "私房菜",
    "精致餐厅",
    "品质餐厅",
    "创意菜",
    "融合菜",
    "海鲜餐厅",
    "日料",
    "牛排",
    "酒店中餐厅",
    "酒楼",
]
HOTEL_HIGH_END_KEYWORDS = [
    "奢华",
    "豪华",
    "五星",
    "五星级",
    "高端酒店",
    "高端",
    "度假酒店",
    "度假",
    "精品酒店",
    "四星",
    "四星级",
    "华邑",
    "香格里拉",
    "凯宾斯基",
    "希尔顿",
    "洲际",
    "万豪",
    "喜来登",
    "悦华",
    "皇冠假日",
    "英迪格",
    "铂尔曼",
    "温德姆",
    "豪生",
    "丽笙",
]
HOTEL_BOUTIQUE_STAY_KEYWORDS = [
    "野奢",
    "轻奢",
    "精品",
    "设计师",
    "度假",
    "海景",
    "山景",
    "Villa",
    "别墅",
    "庄园",
    "温泉",
]
HOTEL_LOW_END_KEYWORDS = [
    "经济",
    "快捷",
    "青年",
    "旅舍",
    "如家",
    "汉庭",
    "7天",
    "七天",
    "锦江之星",
    "格林豪泰",
    "速8",
    "布丁",
    "城市便捷",
]
HOTEL_NOISE_KEYWORDS = [
    "电竞",
    "公寓",
    "舒适型",
    "优选",
    "智能",
]
SCENIC_HIGH_END_KEYWORDS = [
    "主题公园",
    "旅游度假区",
    "度假区",
    "大型景区",
    "索道",
    "游船",
    "夜游",
    "滑雪",
    "温泉景区",
    "海洋馆",
]
EXPERIENCE_HIGH_END_KEYWORDS = [
    "演出",
    "实景演出",
    "沉浸式剧场",
    "剧本杀",
    "剧本",
    "推理",
    "会所",
    "剧场",
    "剧院",
    "游船",
    "夜游",
    "温泉",
    "滑雪场",
    "索道",
]
EXPERIENCE_STRONG_KEYWORDS = [
    "演出",
    "剧院",
    "剧场",
    "大剧院",
    "实景",
    "沉浸式",
    "温泉",
    "滑雪",
    "夜游",
    "游船",
    "索道",
    "乐园",
    "千古情",
    "剧本杀",
    "剧本",
    "推理",
    "桌游",
    "会所",
]
EXPERIENCE_NOISE_KEYWORDS = [
    "KTV",
    "酒吧",
    "棋牌",
    "轰趴",
    "团建",
    "密室",
    "逃脱",
    "VR",
    "SPA",
    "按摩",
]
FOOD_QUERY_KEYWORDS = ["餐厅", "美食", "本地菜", "特色餐厅", "精致餐厅", "商务餐厅", "商务宴请"]
LIGHT_FOOD_KEYWORDS = ["早餐", "早点", "包子", "粥", "小吃", "快餐", "简餐", "咖啡", "奶茶"]


def main() -> None:
    parser = argparse.ArgumentParser(description="从本地高德缓存离线抽取长尾高端 POI 表")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--output", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--summary", type=Path, default=None)
    parser.add_argument("--max-per-city-category", type=int, default=DEFAULT_MAX_PER_CITY_CATEGORY)
    parser.add_argument("--include-major-cities", action="store_true")
    parser.add_argument(
        "--append-cache-derived",
        action="store_true",
        help="默认会先移除旧的缓存抽取行再重建；传入该参数则只追加。",
    )
    args = parser.parse_args()

    table = read_json(args.table, default=empty_table())
    cities = table.setdefault("cities", {})
    update_metadata(table)
    if not args.append_cache_derived:
        remove_cache_derived_rows(cities)

    candidates = collect_candidates(args.cache_dir, include_major=args.include_major_cities)
    added = merge_candidates(cities, candidates, args.max_per_city_category)
    sort_table(cities)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = build_summary(candidates, added, args.output)
    print(summary)
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(summary + "\n", encoding="utf-8")


def collect_candidates(cache_dir: Path, include_major: bool) -> dict[str, dict[str, list[dict[str, Any]]]]:
    results: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for path in sorted(cache_dir.glob("*.json")):
        city, query = parse_cache_filename(path)
        if not city or not query:
            continue
        if not include_major and city in MAJOR_CITY_BLOCKLIST:
            continue

        payload = read_json(path, default={})
        raw = payload.get("data") or {}
        for poi in raw.get("pois") or []:
            category = classify_poi(poi, query)
            if not category:
                continue
            row = normalize_row(poi, category, query)
            if row:
                results[city][category].append(row)

    for city, categories in results.items():
        for category, rows in list(categories.items()):
            categories[category] = dedupe_and_rank(rows, category)
    return results


def classify_poi(poi: dict[str, Any], query: str) -> str:
    name = str(poi.get("name") or "")
    poi_type = str(poi.get("type") or "")
    text = f"{name};{poi_type};{query}"
    rating = parse_float((poi.get("biz_ext") or {}).get("rating")) or 0
    cost = parse_float((poi.get("biz_ext") or {}).get("cost"))

    if "餐饮服务" in poi_type:
        if any(keyword in text for keyword in LIGHT_FOOD_KEYWORDS):
            return ""
        if cost is not None and 120 <= cost <= 1000:
            return "food"
        if cost is not None and 100 <= cost <= 1000 and has_any(text, FOOD_HIGH_END_KEYWORDS):
            return "food"
        return ""

    if "住宿服务" in poi_type:
        if has_any(text, HOTEL_LOW_END_KEYWORDS):
            return ""
        if has_any(text, HOTEL_NOISE_KEYWORDS):
            return ""
        has_hotel_type_signal = any(keyword in poi_type for keyword in ["五星级宾馆", "四星级宾馆"])
        has_name_signal = has_any(f"{name};{poi_type}", HOTEL_HIGH_END_KEYWORDS)
        has_boutique_stay_signal = (
            "民宿" in poi_type
            and has_any(name, HOTEL_BOUTIQUE_STAY_KEYWORDS)
            and not has_any(name, ["客栈", "公寓", "电竞"])
        )
        if rating >= 4.6 and (has_hotel_type_signal or has_name_signal or has_boutique_stay_signal):
            return "hotel"
        return ""

    has_experience_signal = has_any(f"{name};{query}", EXPERIENCE_STRONG_KEYWORDS)
    if has_experience_signal and not has_any(text, EXPERIENCE_NOISE_KEYWORDS):
        if "风景名胜" in poi_type and rating >= 4.2:
            return "experience"
        if ("体育休闲服务" in poi_type or "影剧院" in poi_type or "休闲场所" in poi_type) and rating >= 4.2:
            if cost is None or 80 <= cost <= 600:
                return "experience"

    if "风景名胜" in poi_type:
        if has_any(query, FOOD_QUERY_KEYWORDS):
            return ""
        if cost is not None and 80 <= cost <= 500 and rating >= 4.2:
            return "scenic"
        if rating >= 4.5 and has_any(text, SCENIC_HIGH_END_KEYWORDS):
            return "scenic"
        return ""

    if "体育休闲服务" in poi_type or "影剧院" in poi_type or "休闲场所" in poi_type:
        if has_any(query, FOOD_QUERY_KEYWORDS):
            return ""
        if rating >= 4.5 and has_any(text, EXPERIENCE_HIGH_END_KEYWORDS) and not has_any(text, EXPERIENCE_NOISE_KEYWORDS):
            return "experience"
        return ""

    return ""


def remove_cache_derived_rows(cities: dict[str, Any]) -> None:
    """Drop old cache-derived rows so stricter extraction can rebuild them."""
    empty_cities = []
    for city, city_data in cities.items():
        for category, rows in list(city_data.items()):
            if not isinstance(rows, list):
                continue
            city_data[category] = [
                row for row in rows if row.get("source_provider") != SOURCE_PROVIDER
            ]
        if all(not city_data.get(category) for category in ("food", "hotel", "scenic", "experience")):
            empty_cities.append(city)
    for city in empty_cities:
        cities.pop(city, None)


def normalize_row(poi: dict[str, Any], category: str, query: str) -> dict[str, Any]:
    location = parse_location(poi.get("location"))
    biz_ext = poi.get("biz_ext") or {}
    row = {
        "id": poi.get("id", ""),
        "name": poi.get("name", ""),
        "type": poi.get("type", ""),
        "typecode": poi.get("typecode", ""),
        "address": poi.get("address") if isinstance(poi.get("address"), str) else "",
        "location": location,
        "cityname": poi.get("cityname", ""),
        "adname": poi.get("adname", ""),
        "rating": biz_ext.get("rating", ""),
        "source_keyword": source_keyword_for(category, query),
        "source_provider": SOURCE_PROVIDER,
        "source_query": query,
        "source_collected_at": SOURCE_COLLECTED_AT,
    }
    cost = parse_float(biz_ext.get("cost"))
    if cost is not None and cost >= 0:
        row["cost"] = f"{cost:.2f}"
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}


def dedupe_and_rank(rows: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row.get("id") or normalize_name(row.get("name"))
        if not key:
            continue
        if key not in best or rank_key(row, category) < rank_key(best[key], category):
            best[key] = row
    return sorted(best.values(), key=lambda row: rank_key(row, category))


def rank_key(row: dict[str, Any], category: str) -> tuple[Any, ...]:
    cost = parse_float(row.get("cost")) or 0
    rating = parse_float(row.get("rating")) or 0
    has_location = 1 if row.get("location") else 0
    if category == "food":
        return (-cost, -rating, -has_location, str(row.get("name") or ""))
    if category == "hotel":
        return (-rating, -has_location, str(row.get("name") or ""))
    return (-cost, -rating, -has_location, str(row.get("name") or ""))


def merge_candidates(
    cities: dict[str, Any],
    candidates: dict[str, dict[str, list[dict[str, Any]]]],
    max_per_city_category: int,
) -> Counter:
    added: Counter = Counter()
    for city in sorted(candidates):
        city_table = cities.setdefault(city, {})
        for category in ("food", "hotel", "scenic", "experience"):
            existing = city_table.setdefault(category, [])
            existing_keys = {row_key(row) for row in existing}
            for row in candidates[city].get(category, []):
                if len(existing) >= max_per_city_category:
                    break
                key = row_key(row)
                if key in existing_keys:
                    continue
                existing.append(row)
                existing_keys.add(key)
                added[(city, category)] += 1
    return added


def sort_table(cities: dict[str, Any]) -> None:
    for city_data in cities.values():
        for category, rows in city_data.items():
            if isinstance(rows, list):
                rows.sort(key=lambda row: rank_key(row, category))


def build_summary(
    candidates: dict[str, dict[str, list[dict[str, Any]]]],
    added: Counter,
    output: Path,
) -> str:
    lines = [
        "# 离线高端 POI 表抽取摘要",
        "",
        f"- 输出：`{output}`",
        f"- 候选城市数：{len(candidates)}",
        f"- 新增条目数：{sum(added.values())}",
        "- 来源：本地 `training/data/cache/planner_context/amap_api/place_text/*.json`，未调用高德 API",
        "",
        "| 城市 | 餐饮 | 酒店 | 景点 | 体验 |",
        "|---|---:|---:|---:|---:|",
    ]
    cities = sorted({city for city, _category in added})
    for city in cities:
        lines.append(
            "| {city} | {food} | {hotel} | {scenic} | {experience} |".format(
                city=city,
                food=added.get((city, "food"), 0),
                hotel=added.get((city, "hotel"), 0),
                scenic=added.get((city, "scenic"), 0),
                experience=added.get((city, "experience"), 0),
            )
        )
    return "\n".join(lines)


def update_metadata(table: dict[str, Any]) -> None:
    table["version"] = "2026-05-11_high_end_long_tail"
    table["description"] = (
        "Curated high-end POI recall supplements for long-tail cities. "
        "Seed rows were manually checked from Amap place/text; additional rows are extracted offline "
        "from local Amap place/text cache without calling Amap. Rows without cost keep price blank."
    )
    source = table.setdefault("source", {})
    source["provider"] = "amap_place_text + amap_place_text_cache"
    source["endpoint"] = "/v3/place/text"
    source["extensions"] = "all"
    source["collected_at"] = SOURCE_COLLECTED_AT
    source["last_offline_cache_merge_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_cache_filename(path: Path) -> tuple[str, str]:
    match = re.match(r"^(.+?)_(.+?)_all_[0-9a-f]+\.json$", path.name)
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def source_keyword_for(category: str, query: str) -> str:
    if category == "food":
        return query if has_any(query, FOOD_HIGH_END_KEYWORDS) else "高端餐厅"
    if category == "hotel":
        return query if has_any(query, HOTEL_HIGH_END_KEYWORDS) else "高端酒店"
    if category == "scenic":
        return query if has_any(query, SCENIC_HIGH_END_KEYWORDS) else "大型景区"
    if category == "experience":
        return query if has_any(query, EXPERIENCE_HIGH_END_KEYWORDS) else "高端体验"
    return query


def row_key(row: dict[str, Any]) -> str:
    return str(row.get("id") or normalize_name(row.get("name")) or "")


def normalize_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[\s·•\-_\(\)（）【】\[\]<>《》「」『』]", "", text)


def parse_float(value: Any) -> float | None:
    if value in (None, "", []):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_location(value: Any) -> dict[str, float] | None:
    if not isinstance(value, str) or "," not in value:
        return None
    try:
        longitude, latitude = value.split(",", 1)
        return {"longitude": float(longitude), "latitude": float(latitude)}
    except ValueError:
        return None


def has_any(text: Any, keywords: list[str]) -> bool:
    value = str(text or "")
    return any(keyword in value for keyword in keywords)


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


def empty_table() -> dict[str, Any]:
    return {
        "version": "2026-05-11_high_end_long_tail",
        "description": "",
        "source": {},
        "cities": {},
    }


if __name__ == "__main__":
    main()
