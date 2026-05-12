"""
Offline ESKF validation against flight logs.

Usage:
    python tools/replay_eval.py \
        --log logs/flight_001.log \
        --ground-truth logs/flight_001_gps.csv \
        --output logs/flight_001_eval/
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np


def load_flight_log(path: str) -> list[dict]:
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k: float(v) if k != 'timestamp_ns' else int(v) for k, v in row.items()})
    return rows


def load_ground_truth(path: str) -> list[dict]:
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k: float(v) for k, v in row.items()})
    return rows


def compute_metrics(
    log_rows: list[dict],
    gt_rows: list[dict],
) -> dict:
    if not gt_rows:
        pos_log = np.array([[r['pos_n'], r['pos_e'], r['pos_d']] for r in log_rows])
        return {
            'rms': float(np.nan),
            'p90': float(np.nan),
            'p95': float(np.nan),
            'fix_accept_rate': _fix_accept_rate(log_rows),
            'n_frames': len(log_rows),
        }

    gt_times = np.array([r.get('timestamp_s', r.get('time_s', 0.0)) for r in gt_rows])
    log_times = np.array([r['timestamp_ns'] * 1e-9 for r in log_rows])

    errors = []
    for row in log_rows:
        t = row['timestamp_ns'] * 1e-9
        idx = int(np.argmin(np.abs(gt_times - t)))
        if abs(gt_times[idx] - t) > 0.5:
            continue
        gt = gt_rows[idx]
        p_log = np.array([row['pos_n'], row['pos_e'], row['pos_d']])
        p_gt = np.array([gt.get('north_m', 0.0), gt.get('east_m', 0.0), gt.get('down_m', 0.0)])
        errors.append(float(np.linalg.norm(p_log - p_gt)))

    if not errors:
        return {'rms': np.nan, 'p90': np.nan, 'p95': np.nan,
                'fix_accept_rate': _fix_accept_rate(log_rows), 'n_frames': len(log_rows)}

    errors = np.array(errors)
    return {
        'rms': float(np.sqrt(np.mean(errors ** 2))),
        'p90': float(np.percentile(errors, 90)),
        'p95': float(np.percentile(errors, 95)),
        'fix_accept_rate': _fix_accept_rate(log_rows),
        'n_frames': len(log_rows),
    }


def _fix_accept_rate(log_rows: list[dict]) -> float:
    if not log_rows:
        return 0.0
    return float(np.mean([r['fix_accepted'] for r in log_rows]))


def plot_results(log_rows: list[dict], output_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed — skipping plots", file=sys.stderr)
        return

    times = np.array([r['timestamp_ns'] * 1e-9 for r in log_rows])
    times -= times[0]

    north = np.array([r['pos_n'] for r in log_rows])
    east = np.array([r['pos_e'] for r in log_rows])
    tq = np.array([r['track_quality'] for r in log_rows])
    fixes = np.array([r['fix_accepted'] for r in log_rows])

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

    axes[0].plot(times, north, label='North (m)')
    axes[0].plot(times, east, label='East (m)')
    axes[0].set_ylabel('Position (m)')
    axes[0].legend()
    axes[0].set_title('ESKF Position Estimate')

    axes[1].plot(times, tq, label='Track Quality')
    axes[1].set_ylabel('Track Quality')
    axes[1].set_ylim(0, 1.1)

    fix_times = times[fixes > 0]
    axes[2].vlines(fix_times, 0, 1, colors='green', alpha=0.5, label='Fix Accepted')
    axes[2].set_ylabel('Fix Events')
    axes[2].set_xlabel('Time (s)')

    plt.tight_layout()
    plot_path = output_dir / "position.png"
    plt.savefig(str(plot_path), dpi=150)
    print(f"Plot saved: {plot_path}")
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline ESKF replay evaluation")
    parser.add_argument("--log", type=str, required=True)
    parser.add_argument("--ground-truth", type=str, default=None)
    parser.add_argument("--output", type=str, default="logs/eval/")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading flight log: {args.log}")
    log_rows = load_flight_log(args.log)
    print(f"  {len(log_rows)} frames loaded")

    gt_rows = []
    if args.ground_truth:
        print(f"Loading ground truth: {args.ground_truth}")
        gt_rows = load_ground_truth(args.ground_truth)
        print(f"  {len(gt_rows)} ground truth points loaded")

    metrics = compute_metrics(log_rows, gt_rows)

    print("\nResults:")
    print(f"  Frames evaluated:  {metrics['n_frames']}")
    print(f"  Fix accept rate:   {metrics['fix_accept_rate']*100:.1f}%")
    print(f"  Position RMS:      {metrics['rms']:.2f} m")
    print(f"  P90 error:         {metrics['p90']:.2f} m")
    print(f"  P95 error:         {metrics['p95']:.2f} m")

    plot_results(log_rows, output_dir)

    summary_path = output_dir / "summary.txt"
    with open(summary_path, "w") as f:
        for k, v in metrics.items():
            f.write(f"{k}: {v}\n")
    print(f"Summary saved: {summary_path}")


if __name__ == "__main__":
    main()
