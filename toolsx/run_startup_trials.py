#!/usr/bin/env python3
"""Run multiple startup trials and collect tckr_visibility.log per run.
Usage: python tools/run_startup_trials.py [--runs N] [--duration S]

This will launch the main TCKR script, wait `duration` seconds, then terminate it and copy
`TCKR.Visibility.log` to `tools/output/run-<i>.log` for later analysis.
"""
import argparse, subprocess, shutil, os, time

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, '..'))
LOG = os.path.join(ROOT, 'tckr_visibility.log')
OUT_DIR = os.path.join(HERE, 'output')
SCRIPT = os.path.join(ROOT, 'TCKR-v1.0.2026.0121.1526.py')

parser = argparse.ArgumentParser()
parser.add_argument('--runs', type=int, default=10)
parser.add_argument('--duration', type=float, default=6.0)
args = parser.parse_args()

os.makedirs(OUT_DIR, exist_ok=True)

for i in range(1, args.runs + 1):
    # clear previous log
    try:
        if os.path.exists(LOG):
            os.remove(LOG)
    except Exception:
        pass

    print(f"Run {i}/{args.runs}: launching {SCRIPT} (will run {args.duration}s)")
    p = subprocess.Popen(["python", SCRIPT], cwd=ROOT)
    try:
        time.sleep(args.duration)
    except KeyboardInterrupt:
        p.terminate(); p.wait(); raise
    # Terminate if still running
    try:
        p.terminate()
        p.wait(timeout=5)
    except Exception:
        try:
            p.kill(); p.wait(timeout=2)
        except Exception:
            pass
    # Copy log
    out = os.path.join(OUT_DIR, f"run-{i}.log")
    try:
        if os.path.exists(LOG):
            shutil.copy2(LOG, out)
            print(f"  wrote {out}")
        else:
            print("  no log produced for this run")
    except Exception as e:
        print(f"  failed to copy log: {e}")
    time.sleep(0.5)

print("Done. To analyze, run: python tools/parse_monitor_traces.py <path>")
