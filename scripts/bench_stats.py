"""Print aggregate render statistics from your own database. Read-only.

Prints counts and timings only. It never selects names, voter IDs, file keys or
credentials, and never prints the database URL.

Usage (from the repo root, with your .env loaded or VIDGEN_DATABASE_URL set):
    set -a; . ./.env; set +a
    .venv/bin/python scripts/bench_stats.py            # table
    .venv/bin/python scripts/bench_stats.py --json     # JSON
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from sqlalchemy import create_engine, text

_ROW_STATS = text(
    """
    select
      count(*)                                                  as rows_total,
      count(*) filter (where status = 'COMPLETED')              as rows_completed,
      count(*) filter (where status = 'FAILED')                 as rows_failed,
      count(*) filter (where status = 'SKIPPED')                as rows_skipped,
      count(*) filter (where status = 'CANCELLED')              as rows_cancelled,
      avg(render_seconds)  filter (where status = 'COMPLETED')  as avg_s,
      percentile_cont(0.5)  within group (order by render_seconds)
        filter (where status = 'COMPLETED')                     as median_s,
      percentile_cont(0.95) within group (order by render_seconds)
        filter (where status = 'COMPLETED')                     as p95_s,
      min(render_seconds)  filter (where status = 'COMPLETED')  as min_s,
      max(render_seconds)  filter (where status = 'COMPLETED')  as max_s
    from batch_rows
    """
)

_BATCH_STATS = text(
    """
    select
      count(*)                                         as batches_total,
      count(*) filter (where status = 'COMPLETED')     as batches_completed,
      count(*) filter (where finished_at is not null and started_at is not null)
                                                       as batches_timed,
      avg(extract(epoch from (finished_at - started_at)))
        filter (where status = 'COMPLETED')            as avg_batch_wall_s
    from batches
    """
)

# Wall-clock throughput = completed rows / elapsed time of the batches that finished.
_THROUGHPUT = text(
    """
    select
      sum(c.completed)                                                  as videos,
      sum(extract(epoch from (b.finished_at - b.started_at)))           as wall_s
    from batches b
    join lateral (
      select count(*) as completed from batch_rows r
      where r.batch_id = b.id and r.status = 'COMPLETED'
    ) c on true
    where b.status = 'COMPLETED' and b.started_at is not null and b.finished_at is not null
    """
)


def _clean(row: Any) -> dict[str, float | int | None]:
    return {k: (round(float(v), 2) if isinstance(v, float) else v) for k, v in row._mapping.items()}


def collect(url: str) -> dict[str, Any]:
    """Run the read-only aggregate queries and return one dict."""
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("set transaction read only"))
        rows = _clean(conn.execute(_ROW_STATS).one())
        batches = _clean(conn.execute(_BATCH_STATS).one())
        thr = conn.execute(_THROUGHPUT).one()
    done = rows["rows_completed"] or 0
    attempted = done + (rows["rows_failed"] or 0)
    result: dict[str, Any] = {**rows, **batches}
    result["success_rate_pct"] = round(100 * done / attempted, 1) if attempted else None
    if thr.wall_s and thr.videos:
        result["throughput_videos_per_hour"] = round(float(thr.videos) / float(thr.wall_s) * 3600, 1)
    else:
        result["throughput_videos_per_hour"] = None
    return result


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args()
    url = os.environ.get("VIDGEN_DATABASE_URL")
    if not url:
        print("Set VIDGEN_DATABASE_URL (e.g. `set -a; . ./.env; set +a`).", file=sys.stderr)
        return 2
    stats = collect(url)
    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        width = max(len(k) for k in stats)
        for key, value in stats.items():
            print(f"{key:<{width}}  {'n/a' if value is None else value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
