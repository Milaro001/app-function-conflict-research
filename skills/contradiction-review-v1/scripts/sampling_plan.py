"""Plan the next bounded collection batch from reviewed counts; never crawl or label."""
import argparse
import calendar
import json
import math
from datetime import datetime
from pathlib import Path


def years_before(value, years):
    d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not d.tzinfo or years not in (1, 2, 3, 4):
        raise ValueError('a timezone-aware end and 1..4 calendar years are required')
    y = d.year - years
    return d.replace(year=y, day=min(d.day, calendar.monthrange(y, d.month)[1]),
                     hour=0, minute=0, second=0, microsecond=0).isoformat()


def raw_collection_plan(actual=None):
    """Planning band only: report observed IDs, never trim or randomize records."""
    if actual is not None and (type(actual) is not int or actual < 0):
        raise ValueError('actual raw count must be a non-negative integer or unknown')
    status='unknown' if actual is None else 'below_planning_band' if actual<1500 else 'within_planning_band' if actual<=2500 else 'above_planning_band'
    return dict(aim=2000, planning_min=1500, planning_max=2500, actual=actual, status=status,
                hard_cap=False, truncate_to_target=False, randomize_target=False,
                finish_at='bounded_page_thread_or_batch_boundary',
                effective_minimum_checked_separately=True,
                note='约2000条是原始量预算；按完整页/回复链/批次自然收尾，保留实际数。有效量不足时继续补采或核实条件，不在2000或2500处硬截断。')


def plan(data, years=1, exhausted=False):
    a = data.get('analytics', data)
    scope, m = a['scope'], a['metrics']
    effective = m['qualified_groups']
    minimum, preferred = 1000, 2000
    result = dict(app=scope['app'], years=years, minimum_effective=minimum,
                  preferred_effective=preferred, effective_count=effective,
                  minimum_met=effective >= minimum, preferred_met=effective >= preferred,
                  current_scope=scope, next_since=years_before(scope['end'], years),
                  requires_semantic_review_after_batch=True,
                  raw_count_is_not_completion=True,
                  raw_collection=raw_collection_plan(m.get('raw_comment_ids')))
    if effective >= preferred:
        result.update(action='complete', reason='preferred effective target met')
    elif data.get('all_available_paths_blocked'):
        result.update(action='stop_with_gap', reason='accessible sources blocked; do not retry or bypass to satisfy quantity')
    elif effective >= minimum:
        result.update(action='minimum_met_continue_current_window' if not exhausted else 'complete_minimum_with_preferred_gap',
                      reason='minimum met; approach 2000 within the current window where accessible')
    elif exhausted and years < 4:
        result.update(action='expand_window', next_years=years+1,
                      next_since=years_before(scope['end'], years+1),
                      reason='current window insufficient; expand one calendar year without relaxing other conditions')
    elif exhausted:
        result.update(action='stop_with_gap', reason='four-year window exhausted below minimum; report the actual gap')
    else:
        result.update(action='collect_current_window', reason='continue available current-window batches and review them')
    if effective == 0 and m.get('window_groups', 0):
        result['condition_check'] = '核实客户端、版本等条件或调整取证来源；不能用无限扩量替代条件核实。'
    denominator = m.get('text_groups', 0)
    if effective and denominator:
        rate = effective / denominator
        result['budget'] = dict(basis='qualified groups / reviewed non-symbol text groups',
                              numerator=effective, denominator=denominator,
                              estimated_additional_groups=math.ceil(max(0, preferred-effective)/rate),
                              note='This is a sample-based estimate, not an inventory or elapsed-time promise.')
    else:
        result['budget'] = None
    result['gap_to_minimum'] = max(0, minimum-effective)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path);p.add_argument('--years', type=int, choices=range(1,5), default=1)
    p.add_argument('--window-exhausted', action='store_true');p.add_argument('--output', type=Path)
    args=p.parse_args();result=plan(json.loads(args.input.read_text(encoding='utf-8')),args.years,args.window_exhausted)
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text,encoding='utf-8')
    else:print(text)


if __name__=='__main__':main()
