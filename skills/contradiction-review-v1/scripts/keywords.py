#!/usr/bin/env python3
"""Build an N2 search-keyword matrix: neutral, problem, request and comparison wording.

One fixed keyword ("<App> 功能") misses most feedback; users write "闪退", "能不能",
"取件码" rather than "功能". This only plans search phrases; relevance is still
judged per post and per comment later.
"""
import sys
import argparse
import json
from pathlib import Path

INTENTS = {
    'neutral': ['{app}', '{app} 体验'],
    'problem': ['{app} 吐槽', '{app} bug', '{app} 难用', '{app} 闪退 卡顿'],
    'request': ['{app} 建议', '{app} 希望', '{app} 能不能'],
    'compare': ['{app} 对比', '{app} 替代'],
}
# Platform phrasing differs: Zhihu users ask questions, Weibo/XHS users vent or share tips.
PLATFORM_EXTRA = {
    'zhihu': ['如何评价{app}', '{app} 为什么'],
    'xhs': ['{app} 避雷', '{app} 好用吗'],
    'wb': ['{app} 客服', '{app} 无语'],
    'bili': ['{app} 测评', '{app} 教程'],
    'douyin': ['{app} 好用吗'],
}


def build(app, features=(), competitors=(), per_platform=12):
    base = [t.format(app=app) for group in INTENTS.values() for t in group]
    feature_terms = [f'{app} {f}' for f in features] + [f'{app} {f} 问题' for f in features[:3]]
    compare_terms = [f'{app} {c}' for c in competitors]
    shared = list(dict.fromkeys(feature_terms + base + compare_terms))
    platforms = {}
    for platform, extra in PLATFORM_EXTRA.items():
        terms = [t.format(app=app) for t in extra]
        # Feature terms first: they are the most decision-specific searches.
        platforms[platform] = list(dict.fromkeys(feature_terms + terms + base + compare_terms))[:per_platform]
    return dict(app=app, features=list(features), competitors=list(competitors), keywords=shared[:per_platform],
                intents={k: [t.format(app=app) for t in v] for k, v in INTENTS.items()}, platforms=platforms,
                note='Search phrases only. A hit is a lead; each post/comment is screened for the App and decision object.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--app', required=True)
    p.add_argument('--feature', action='append', default=[], help='feature or decision object, e.g. 取件码; repeatable')
    p.add_argument('--competitor', action='append', default=[])
    p.add_argument('--per-platform', type=int, default=12)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    if not 4 <= a.per_platform <= 12:p.error('per-platform must be 4..12 (recent_sample accepts at most 12)')
    plan = build(a.app, a.feature, a.competitor, a.per_platform)
    text = json.dumps(plan, ensure_ascii=False, indent=2) + '\n'
    if a.output:a.output.parent.mkdir(parents=True, exist_ok=True);a.output.write_text(text,encoding='utf-8')
    print(text, end='')


if __name__ == '__main__':
    # Windows consoles often use GBK; never crash on characters they cannot show.
    for _s in (sys.stdout,sys.stderr):
        if hasattr(_s,'reconfigure'):_s.reconfigure(errors='backslashreplace')
    main()
