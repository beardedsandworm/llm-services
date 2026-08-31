#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$SOURCE_DIR"
python3 -m unittest discover -s tests -v
python3 monitor.py --config config.env.example --check-config
UNIT_DIR=$(mktemp -d)
trap 'rm -rf "$UNIT_DIR"' EXIT
python3 -c 'from pathlib import Path; import sys; Path(sys.argv[2]).write_text(Path(sys.argv[1]).read_text().replace("/usr/local/lib/internal-dns-monitor/monitor.py", sys.argv[3]), encoding="utf-8")' \
  "$SOURCE_DIR/systemd/internal-dns-monitor.service" "$UNIT_DIR/internal-dns-monitor.service" "$SOURCE_DIR/monitor.py"
systemd-analyze verify "$UNIT_DIR/internal-dns-monitor.service" systemd/internal-dns-monitor.timer
printf '%s\n' 'Source verification passed; no DNS probes, ingress posts, installs, enables, or starts were performed.'
