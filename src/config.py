"""Project configuration: data source, paths, and processing constants."""
from pathlib import Path

# Data source: Vadimkin/ukrainian-air-raid-sirens-dataset, official English CSV.
# Region names are transliterated to Latin script in this file, which keeps the
# whole pipeline and dashboard English-only.
RAW_URL = (
    "https://raw.githubusercontent.com/Vadimkin/"
    "ukrainian-air-raid-sirens-dataset/main/datasets/official_data_en.csv"
)

# Local cache. The data/ directory is gitignored: the full dataset is never
# committed (it is large, updates daily, and is someone else's data to host).
DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
RAW_PATH = RAW_DIR / "official_data_en.csv"

# Timezone. Always convert through the IANA zone name so daylight-saving time is
# applied automatically. A hardcoded offset (+02:00 / +03:00) would silently
# break around the DST switch, so it is deliberately never used.
KYIV_TZ = "Europe/Kyiv"

# An "alert" longer than this is treated as a permanent / stuck siren, not a
# real alert. Some records get "stuck" open (no end signal recorded), producing
# multi-hundred-day durations — observed in Dnipropetrovska and Kharkivska
# oblasts. Such rows are flagged and excluded from analysis. Detection is by
# duration threshold, NOT by region, so it generalizes to any stuck record.
# The longest genuine mass attacks run ~30 hours, so 7 days is a safe cut-off.
PERMANENT_THRESHOLD_DAYS = 7

# Night window (Kyiv local hours) used for the "night share" metric: 22:00-05:59.
NIGHT_HOURS = set(range(22, 24)) | set(range(0, 6))
