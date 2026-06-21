"""Orchestrate the full pipeline: raw -> L1 (clean) -> L2 (marts), and persist
the marts the dashboard reads.

Run:  python pipeline.py

The full raw dataset is downloaded on first run and cached under data/raw/ (both
are gitignored). The persisted marts are tiny CSVs the Streamlit app loads
directly, so the dashboard never recomputes the 9-second pipeline on every view.
"""
from __future__ import annotations

from src import config
from src.aggregate import build_l2
from src.analysis import night_share_trend, sanity_plot
from src.data import build_l1, load_raw


def main() -> None:
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    print("1/3  loading raw data (downloads on first run) ...")
    raw = load_raw()

    print("2/3  building L1 (clean canonical events) ...")
    l1 = build_l1(raw)

    print("3/3  building L2 marts (oblast union + coverage) ...")
    l2 = build_l2(l1)

    # Persist only what the dashboard needs: both marts are tiny.
    # heat        -> year x hour-of-day coverage minutes (heatmap source)
    # night_share -> night-coverage share per year, with the uniform baseline
    heat_path = config.PROCESSED_DIR / "heat.csv"
    night_path = config.PROCESSED_DIR / "night_share.csv"
    plot_path = config.PROCESSED_DIR / "night_analysis.png"

    l2["heat"].to_csv(heat_path, index=False)
    night_share_trend(l2).to_csv(night_path, index=False)
    sanity_plot(l2, str(plot_path))

    print("\nwrote:")
    print(f"  {heat_path}")
    print(f"  {night_path}")
    print(f"  {plot_path}")
    print(f"\nL1 rows: {len(l1)}  |  years covered: "
          f"{sorted(int(y) for y in l2['night_share']['year'])}")


if __name__ == "__main__":
    main()
