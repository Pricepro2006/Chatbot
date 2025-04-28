#!/usr/bin/env python
# multi_model_tester_v6_0.py – sequential model comparison harness
# ---------------------------------------------------------------------------
"""
Spins up `local_bot_server_v6_0.py` once per LLM model (mistral / mixtral / openchat),
runs an inner test harness (`test_harness_v6_0.py`), and aggregates the resulting
Markdown summaries into a single comparison report.

It keeps the interface flags from the v5 script but is trimmed for clarity.
Python ≥ 3.13   |   Requires: psutil, pandas, requests
"""
from __future__ import annotations

import argparse, os, signal, subprocess, sys, time
from pathlib import Path
from datetime import datetime
import textwrap

import pandas as pd
import psutil

# ---------------------------------------------------------------------------
VERSION = "6.0.0"

def parse_args():
    p = argparse.ArgumentParser(description="Compare multiple LLM models with v6 harness")
    p.add_argument("--server-script", default="local_bot_server_v6_0.py")
    p.add_argument("--test-script", default="test_harness_v6_0.py")
    p.add_argument("--models", nargs="+", default=["mistral", "mixtral", "openchat"])
    p.add_argument("--questions-per-model", type=int, default=100)
    p.add_argument("--output-folder", default="test_results/model_comparison")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--timeout", type=int, default=20)
    return p.parse_args()

# ---------------------------------------------------------------------------
def kill_port(port: int):
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            for conn in proc.connections(kind="inet"):
                if conn.laddr.port == port:
                    print(f"⚠ Killing pid {proc.pid} on port {port}")
                    proc.kill()
        except psutil.AccessDenied:
            pass

def launch_server(script: str, port: int, model: str) -> subprocess.Popen | None:
    cmd = [sys.executable, script, "--port", str(port), "--model", model]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    # wait until health endpoint ready
    import requests, time
    for _ in range(30):
        try:
            if requests.get(f"http://localhost:{port}/health", timeout=1).ok:
                print(f"✅ {model} server up")
                return proc
        except requests.RequestException:
            pass
        time.sleep(1)
    print(f"❌ {model} server failed to start")
    proc.kill()
    return None

def run_test(model: str, args):
    # ensure port is free
    kill_port(args.port)
    proc = launch_server(args.server_script, args.port, model)
    if not proc:
        return None

    out_folder = Path(args.output_folder) / model
    cmd = [
        sys.executable, args.test_script,
        "--test-size", str(args.questions_per_model),
        "--output-folder", str(out_folder),
        "--port", str(args.port),
    ]
    print("▶", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    proc.terminate()
    return out_folder

def collect_summary(folder: Path):
    md_files = sorted(folder.glob("summary_*.md"))
    return md_files[-1] if md_files else None

def main():
    args = parse_args()
    Path(args.output_folder).mkdir(parents=True, exist_ok=True)
    summary_paths = {}

    for model in args.models:
        print(f"\n=== Testing model: {model} ===")
        out = run_test(model, args)
        if not out:
            continue
        summary = collect_summary(out)
        if summary:
            summary_paths[model] = summary
            print("Summary:", summary)
        time.sleep(2)  # small cool‑down

    # build comparison report
    if not summary_paths:
        print("No summaries produced; exiting")
        sys.exit(1)

    rows = []
    for model, md in summary_paths.items():
        text = md.read_text(encoding="utf-8")
        total = int(text.split("Total: ")[1].split("\n")[0])
        passed = int(text.split("Passed: ")[1].split("\n")[0])
        rate = float(text.split("Pass rate: ")[1].split("%")[0])
        rows.append({"Model": model, "Total": total, "Passed": passed, "Rate": rate})

    df = pd.DataFrame(rows).sort_values("Rate", ascending=False)
    comp_path = Path(args.output_folder) / f"model_comparison_{datetime.now():%Y%m%d_%H%M%S}.md"
    lines = ["# Model Comparison", "", df.to_markdown(index=False), "", "## Detailed Summaries"]
    for model, md in summary_paths.items():
        rel = md.relative_to(args.output_folder)
        lines.append(f"- [{model}]({rel})")
    comp_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n🏁 Comparison saved to", comp_path)

if __name__ == "__main__":
    main()
