#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
INSTALL_DIR=/usr/local/lib/internal-dns-monitor
CONFIG_DIR=/etc/internal-dns-monitor
STATE_DIR=/var/lib/internal-dns-monitor
DOC_DIR=/usr/local/share/doc/internal-dns-monitor

if [ "${EUID}" -ne 0 ]; then
  printf '%s\n' 'Run as root to install files; this script never enables or starts the timer.' >&2
  exit 1
fi

install -d -m 0755 "$INSTALL_DIR" "$CONFIG_DIR" "$DOC_DIR"
install -d -m 0750 -o lightweight -g lightweight "$STATE_DIR"
install -m 0755 "$SOURCE_DIR/monitor.py" "$INSTALL_DIR/monitor.py"
install -m 0644 "$SOURCE_DIR/README.md" "$DOC_DIR/README.md"
install -m 0644 "$SOURCE_DIR/systemd/internal-dns-monitor.service" /etc/systemd/system/internal-dns-monitor.service
install -m 0644 "$SOURCE_DIR/systemd/internal-dns-monitor.timer" /etc/systemd/system/internal-dns-monitor.timer
if [ ! -e "$CONFIG_DIR/config.env" ]; then
  install -m 0640 -o root -g lightweight "$SOURCE_DIR/config.env.example" "$CONFIG_DIR/config.env"
fi
systemctl daemon-reload
printf '%s\n' 'Installed only. Review /etc/internal-dns-monitor/config.env, then enable the timer explicitly if approved.'
