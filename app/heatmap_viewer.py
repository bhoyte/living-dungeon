"""Render a quick terminal heatmap from a saved .npz field snapshot."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

PALETTE = " .:-=+*#%@"


def normalize(arr: np.ndarray, vmin: float | None, vmax: float | None) -> np.ndarray:
    lo = float(np.min(arr) if vmin is None else vmin)
    hi = float(np.max(arr) if vmax is None else vmax)
    if hi <= lo:
        return np.zeros_like(arr, dtype=np.float32)
    return np.clip((arr - lo) / (hi - lo), 0.0, 1.0).astype(np.float32)


def render_ascii(arr: np.ndarray, *, max_width: int = 120) -> str:
    step = max(1, int(np.ceil(arr.shape[1] / max_width)))
    sampled = arr[:, ::step]
    idx = np.clip((sampled * (len(PALETTE) - 1)).astype(int), 0, len(PALETTE) - 1)
    lines = ["".join(PALETTE[i] for i in row) for row in idx]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render an ASCII heatmap from fields_snapshot.npz")
    parser.add_argument("--npz", required=True, help="Path to fields_snapshot.npz")
    parser.add_argument("--field", required=True, help="Field name, e.g. mana_geo")
    parser.add_argument("--vmin", type=float, default=None)
    parser.add_argument("--vmax", type=float, default=None)
    parser.add_argument("--max-width", type=int, default=120)
    args = parser.parse_args(argv)

    npz_path = Path(args.npz)
    with np.load(npz_path) as npz:
        key = f"field_{args.field}"
        if key not in npz:
            available = ", ".join(sorted(npz.files))
            raise KeyError(f"{key} not found. Available keys: {available}")
        arr = np.asarray(npz[key], dtype=np.float32)

    norm = normalize(arr, args.vmin, args.vmax)
    print(render_ascii(norm, max_width=args.max_width))
    print(
        f"\nfield={args.field} shape={arr.shape} min={float(np.min(arr)):.4f} "
        f"max={float(np.max(arr)):.4f} mean={float(np.mean(arr)):.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
