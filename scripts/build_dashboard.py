"""Build a static HTML dashboard snapshot from data/logs.jsonl.

Reads the same source of truth as config/dashboard.yaml (data/logs.jsonl) and
computes exactly the six panels defined by that contract: latency (P50/P95/P99
+ TTFT), traffic, errors (+ retrieval success), cost, tokens, quality. This is
the "công cụ tương đương" dashboard tool referenced in docs/DASHBOARD_SETUP.md
(the contract itself is not runnable, it is checked separately by
scripts/validate_dashboard.py).

Usage:
    python scripts/build_dashboard.py [--out submission/evidence/11-dashboard-overview.html]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio  # noqa: E402

LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
DASHBOARD_CONFIG_PATH = REPO_ROOT / "config" / "dashboard.yaml"


def percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    items = sorted(values)
    idx = max(0, min(len(items) - 1, round((p / 100) * len(items) + 0.5) - 1))
    return float(items[idx])


def load_records(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def compute_panels(records: list[dict]) -> dict:
    received = [r for r in records if r.get("event") == "request_received"]
    sent = [r for r in records if r.get("event") == "response_sent"]
    failed = [r for r in records if r.get("event") == "request_failed"]

    latencies = [r["latency_ms"] for r in sent if r.get("latency_ms") is not None]
    ttfts = [r["ttft_ms"] for r in sent if r.get("ttft_ms") is not None]
    costs = [r["cost_usd"] for r in sent if r.get("cost_usd") is not None]
    tokens_in = [r["tokens_in"] for r in sent if r.get("tokens_in") is not None]
    tokens_out = [r["tokens_out"] for r in sent if r.get("tokens_out") is not None]
    quality = [r["quality_score"] for r in sent if r.get("quality_score") is not None]

    total_requests = len(received)
    error_count = len(failed)
    error_rate_pct = round((error_count / total_requests * 100), 2) if total_requests else 0.0

    tool_records = [r for r in records if r.get("tool_success") is not None]
    tool_success_count = sum(1 for r in tool_records if r.get("tool_success") is True)
    tool_success_rate_pct = (
        round(tool_success_count / len(tool_records) * 100, 2) if tool_records else 0.0
    )
    error_breakdown = Counter(r.get("error_type", "unknown") for r in failed)

    if received:
        start = min(r["ts"] for r in received)
        end = max(r["ts"] for r in received)
    else:
        start = end = None

    return {
        "latency": {
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "p99": percentile(latencies, 99),
            "ttft_p95": percentile(ttfts, 95),
            "threshold_p95_ms": 3000,
        },
        "traffic": {
            "count": total_requests,
            "window_start": start,
            "window_end": end,
        },
        "errors": {
            "error_rate_pct": error_rate_pct,
            "error_count": error_count,
            "breakdown": dict(error_breakdown),
            "tool_success_rate_pct": tool_success_rate_pct,
            "threshold_error_rate_pct": 2,
        },
        "cost": {
            "total_usd": round(sum(costs), 6) if costs else 0.0,
            "avg_usd": round(mean(costs), 6) if costs else 0.0,
            "threshold_total_usd": 2.5,
        },
        "tokens": {
            "tokens_in_total": sum(tokens_in),
            "tokens_out_total": sum(tokens_out),
            "threshold_max": 50000,
        },
        "quality": {
            "mean": round(mean(quality), 4) if quality else 0.0,
            "threshold_min": 0.75,
        },
        "meta": {
            "total_records": len(records),
            "total_requests": total_requests,
            "total_responses": len(sent),
        },
    }


def render_html(panels: dict, dashboard_cfg: dict) -> str:
    d = dashboard_cfg["dashboard"]
    lat, traf, err, cost, tok, qual, meta = (
        panels["latency"],
        panels["traffic"],
        panels["errors"],
        panels["cost"],
        panels["tokens"],
        panels["quality"],
        panels["meta"],
    )

    def status(ok: bool) -> str:
        return "ok" if ok else "breach"

    lat_ok = lat["p95"] <= lat["threshold_p95_ms"]
    err_ok = err["error_rate_pct"] <= err["threshold_error_rate_pct"]
    cost_ok = cost["total_usd"] <= cost["threshold_total_usd"]
    tok_ok = (tok["tokens_in_total"] + tok["tokens_out_total"]) <= tok["threshold_max"]
    qual_ok = qual["mean"] >= qual["threshold_min"]

    error_rows = "".join(
        f'<tr><td>{k}</td><td class="num">{v}</td></tr>' for k, v in err["breakdown"].items()
    ) or '<tr><td colspan="2" class="muted">Không có lỗi trong cửa sổ này</td></tr>'

    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Day 13 Monitoring</title>
<style>
  :root {{
    color-scheme: light;
    --surface-1: #fcfcfb;
    --page: #f9f9f7;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --muted: #898781;
    --grid: #e1e0d9;
    --border: rgba(11,11,11,0.10);
    --good: #0ca30c;
    --critical: #d03b3b;
    --blue: #2a78d6;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      color-scheme: dark;
      --surface-1: #1a1a19;
      --page: #0d0d0d;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --muted: #898781;
      --grid: #2c2c2a;
      --border: rgba(255,255,255,0.10);
      --good: #0ca30c;
      --critical: #e66767;
      --blue: #3987e5;
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --surface-1: #1a1a19;
    --page: #0d0d0d;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --muted: #898781;
    --grid: #2c2c2a;
    --border: rgba(255,255,255,0.10);
    --good: #0ca30c;
    --critical: #e66767;
    --blue: #3987e5;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--page);
    color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 24px 16px 48px;
  }}
  .wrap {{ max-width: 1080px; margin: 0 auto; }}
  header {{ margin-bottom: 20px; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .subtitle {{ color: var(--text-secondary); font-size: 13px; }}
  .meta-row {{ display: flex; gap: 16px; flex-wrap: wrap; margin-top: 8px; font-size: 12px; color: var(--muted); }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 14px;
  }}
  .panel {{
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px 18px;
  }}
  .panel h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: .04em; color: var(--text-secondary); margin: 0 0 12px; font-weight: 600; }}
  .stat-row {{ display: flex; gap: 22px; flex-wrap: wrap; margin-bottom: 8px; }}
  .stat {{ min-width: 70px; }}
  .stat .value {{ font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; }}
  .stat .label {{ font-size: 11px; color: var(--muted); margin-top: 2px; }}
  .badge {{ display: inline-block; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 99px; margin-left: 6px; vertical-align: middle; }}
  .badge.ok {{ background: rgba(12,163,12,0.12); color: var(--good); }}
  .badge.breach {{ background: rgba(208,59,59,0.12); color: var(--critical); }}
  .threshold {{ font-size: 11px; color: var(--muted); margin-top: 10px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 6px; }}
  td {{ padding: 4px 0; border-top: 1px solid var(--grid); }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .muted {{ color: var(--muted); }}
  .bar-track {{ background: var(--grid); border-radius: 4px; height: 8px; margin-top: 10px; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 4px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>{d['title']}</h1>
    <div class="subtitle">Nguồn: data/logs.jsonl &middot; Time range: {d['time_range_minutes']} phút &middot; Refresh: {d['refresh_seconds']}s</div>
    <div class="meta-row">
      <span>Cửa sổ dữ liệu: {traf['window_start'] or 'n/a'} &rarr; {traf['window_end'] or 'n/a'}</span>
      <span>Tổng bản ghi log: {meta['total_records']}</span>
    </div>
  </header>

  <div class="grid">
    <div class="panel">
      <h2>Latency percentiles &amp; TTFT <span class="badge {status(lat_ok)}">{'OK' if lat_ok else 'BREACH'}</span></h2>
      <div class="stat-row">
        <div class="stat"><div class="value">{lat['p50']:.0f}</div><div class="label">P50 ms</div></div>
        <div class="stat"><div class="value">{lat['p95']:.0f}</div><div class="label">P95 ms</div></div>
        <div class="stat"><div class="value">{lat['p99']:.0f}</div><div class="label">P99 ms</div></div>
        <div class="stat"><div class="value">{lat['ttft_p95']:.0f}</div><div class="label">TTFT P95 ms</div></div>
      </div>
      <div class="threshold">Threshold: P95 &le; {lat['threshold_p95_ms']} ms (SLO trong config/slo.yaml)</div>
    </div>

    <div class="panel">
      <h2>Request traffic</h2>
      <div class="stat-row">
        <div class="stat"><div class="value">{traf['count']}</div><div class="label">requests trong cửa sổ</div></div>
      </div>
      <div class="threshold">Nguồn: request_received events</div>
    </div>

    <div class="panel">
      <h2>Error rate &amp; retrieval success <span class="badge {status(err_ok)}">{'OK' if err_ok else 'BREACH'}</span></h2>
      <div class="stat-row">
        <div class="stat"><div class="value">{err['error_rate_pct']}%</div><div class="label">error rate</div></div>
        <div class="stat"><div class="value">{err['tool_success_rate_pct']}%</div><div class="label">retrieval success</div></div>
      </div>
      <table><tbody>{error_rows}</tbody></table>
      <div class="threshold">Threshold: error rate &le; {err['threshold_error_rate_pct']}%</div>
    </div>

    <div class="panel">
      <h2>Cost over time <span class="badge {status(cost_ok)}">{'OK' if cost_ok else 'BREACH'}</span></h2>
      <div class="stat-row">
        <div class="stat"><div class="value">${cost['total_usd']:.4f}</div><div class="label">total USD</div></div>
        <div class="stat"><div class="value">${cost['avg_usd']:.6f}</div><div class="label">avg / request</div></div>
      </div>
      <div class="threshold">Threshold: total &le; ${cost['threshold_total_usd']}</div>
    </div>

    <div class="panel">
      <h2>Input &amp; output tokens <span class="badge {status(tok_ok)}">{'OK' if tok_ok else 'BREACH'}</span></h2>
      <div class="stat-row">
        <div class="stat"><div class="value">{tok['tokens_in_total']}</div><div class="label">tokens in</div></div>
        <div class="stat"><div class="value">{tok['tokens_out_total']}</div><div class="label">tokens out</div></div>
      </div>
      <div class="threshold">Threshold: tổng &le; {tok['threshold_max']} tokens</div>
    </div>

    <div class="panel">
      <h2>Quality proxy <span class="badge {status(qual_ok)}">{'OK' if qual_ok else 'BREACH'}</span></h2>
      <div class="stat-row">
        <div class="stat"><div class="value">{qual['mean']}</div><div class="label">mean quality_score</div></div>
      </div>
      <div class="bar-track"><div class="bar-fill" style="width:{qual['mean']*100:.0f}%; background: var(--blue);"></div></div>
      <div class="threshold">Threshold: mean &ge; {qual['threshold_min']}</div>
    </div>
  </div>
</div>
</body>
</html>
"""


def main() -> None:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Build a dashboard HTML snapshot from data/logs.jsonl")
    parser.add_argument("--log-path", type=Path, default=LOG_PATH)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "submission" / "evidence" / "11-dashboard-overview.html")
    args = parser.parse_args()

    if not args.log_path.exists():
        print(f"Error: {args.log_path} not found. Run the app and send requests first.")
        raise SystemExit(1)

    records = load_records(args.log_path)
    panels = compute_panels(records)
    dashboard_cfg = yaml.safe_load(DASHBOARD_CONFIG_PATH.read_text(encoding="utf-8"))

    html = render_html(panels, dashboard_cfg)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")

    print(f"Dashboard written to {args.out}")
    print(json.dumps(panels, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
