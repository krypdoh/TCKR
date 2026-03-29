#!/usr/bin/env python3
"""Simple analyzer for tckr_visibility.log monitor traces.
Usage: python tools/parse_monitor_traces.py [path/to/tckr_visibility.log]
Produces a short summary: counts of POSTSHOW vs INIT monitor mismatches and per-hwnd timeline.
"""
import sys, json, collections, os

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'tckr_visibility.log')

by_hwnd = collections.defaultdict(list)
init_monitor = {}
post_monitor = {}

appbar_events = []
with open(PATH, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        kind = rec.get('kind')
        title = rec.get('title')
        hwnd = rec.get('hwnd') or (rec.get('info') or {}).get('hwnd')
        ts = rec.get('ts')
        if kind == 'appbar_event':
            appbar_events.append(rec)
        if not hwnd:
            continue
        if kind == 'visibility' and title and title.startswith('POSTSHOW-MONITOR-TRACE'):
            # visibility record contains rect in args, but _trace_visibility_event writes kind 'visibility' earlier
            post_monitor[hwnd] = rec
            by_hwnd[hwnd].append(('postshow', ts, rec))
        elif kind == 'visibility' and title and title.startswith('INIT'):
            init_monitor[hwnd] = rec
            by_hwnd[hwnd].append(('init', ts, rec))
        elif kind == 'repair_attempt' and (rec.get('context') or '').startswith('PRE-SHOW'):
            by_hwnd[hwnd].append(('pre-show-repair', ts, rec))
        elif kind == 'repair_attempt' and (rec.get('context') or '').startswith('POSTSHOW'):
            by_hwnd[hwnd].append(('postshow-repair', ts, rec))

# Summarize
wrong_created = 0
moved_postshow = 0
for hw, items in by_hwnd.items():
    init = next((i for i in items if i[0]=='init'), None)
    post = next((i for i in items if i[0]=='postshow'), None)
    if init and post:
        # compare rect or monitor info
        try:
            init_rect = tuple(init[2].get('rect') or [])
            post_rect = tuple(post[2].get('rect') or [])
            if init_rect and post_rect and init_rect != post_rect:
                wrong_created += 1
                moved_postshow += 1
        except Exception:
            pass

print("Monitor trace analysis:")
print(f"  total hwnds with traces: {len(by_hwnd)}")
print(f"  windows created on one monitor then moved (approx): {moved_postshow}")
print("Per-hwnd timeline (latest events):")
for hw, items in sorted(by_hwnd.items(), key=lambda x: x[0]):
    print(f"  hwnd={hw}")
    for name, ts, rec in sorted(items, key=lambda x: x[1]):
        print(f"    {name} @ {ts}: {rec.get('context') or rec.get('title') or rec.get('state')}")

# AppBar event summaries
from collections import Counter
print('\nAppBar event summary:')
if appbar_events:
    action_counts = Counter([e.get('action') for e in appbar_events])
    monitor_counts = Counter([ (e.get('monitor') or {}).get('device') for e in appbar_events ])
    display1_events = [e for e in appbar_events if (e.get('monitor') or {}).get('device') and 'DISPLAY1' in (e.get('monitor') or {}).get('device')]
    owner_counts = Counter([e.get('owner_exe') or '<unknown>' for e in display1_events])
    print(f"  total appbar events: {len(appbar_events)}")
    print(f"  by action: {dict(action_counts)}")
    print(f"  by monitor.device (top): {monitor_counts.most_common(5)}")
    print(f"  events referencing DISPLAY1: {len(display1_events)}")
    print(f"  top owners for DISPLAY1 events: {owner_counts.most_common(5)}")
else:
    print("  no appbar_event records found")

print('\nDone.')
