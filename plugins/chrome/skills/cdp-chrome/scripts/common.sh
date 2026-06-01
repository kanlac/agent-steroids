#!/bin/bash
# Shared helpers for cdp-chrome scripts. Keep POSIX-ish bash; no personal paths.

set -u

cdp_config_path() {
  printf '%s\n' "${APPDATA:-$HOME/.config}/steroids.json"
}

cdp_load_config() {
  # Prints shell assignments: CDP_PORT=... CDP_PROFILE_DIR=...
  python3 - "$@" <<'PY'
import json
import os
import shlex
import sys

config_path = os.path.expanduser(os.path.expandvars(os.environ.get("CDP_CHROME_CONFIG", os.path.join(os.environ.get("APPDATA", os.path.join(os.environ.get("HOME", ""), ".config")), "steroids.json"))))
port = 9224
profile_dir = "~/.config/cdp-chrome/profile"
try:
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    section = data.get("cdp-chrome", {}) if isinstance(data, dict) else {}
    if "port" in section:
        port = int(section["port"])
    if "profile_dir" in section and section["profile_dir"]:
        profile_dir = str(section["profile_dir"])
except FileNotFoundError:
    pass
except Exception as exc:
    print(f"ERROR: invalid cdp-chrome config at {config_path}: {exc}", file=sys.stderr)
    sys.exit(2)

if port < 1 or port > 65535:
    print(f"ERROR: cdp-chrome.port must be between 1 and 65535, got {port}", file=sys.stderr)
    sys.exit(2)

profile_dir = os.path.abspath(os.path.expanduser(os.path.expandvars(profile_dir)))
print(f"CDP_PORT={port}")
print(f"CDP_PROFILE_DIR={shlex.quote(profile_dir)}")
print(f"CDP_CONFIG_PATH={shlex.quote(config_path)}")
PY
}

cdp_apply_config() {
  eval "$(cdp_load_config)"
}

cdp_canonical_dir() {
  # Canonicalize a directory path if it exists; otherwise normalize its parent.
  # Prints the best-effort absolute path.
  python3 - "$1" <<'PY'
import os
import sys
path = os.path.abspath(os.path.expanduser(os.path.expandvars(sys.argv[1])))
if os.path.isdir(path):
    print(os.path.realpath(path))
else:
    parent = os.path.dirname(path) or "."
    if os.path.isdir(parent):
        print(os.path.join(os.path.realpath(parent), os.path.basename(path)))
    else:
        print(os.path.realpath(path))
PY
}

cdp_http_ready() {
  port="$1"
  for endpoint in "http://127.0.0.1:$port" "http://[::1]:$port"; do
    if curl -fsS --connect-timeout 2 "$endpoint/json/version" >/dev/null 2>&1; then
      return 0
    fi
  done
  return 1
}

cdp_listener_pids() {
  port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN -Fp 2>/dev/null | while IFS= read -r line; do
      case "$line" in
        p*) printf '%s\n' "${line#p}" ;;
      esac
    done | sort -u
  fi
}

cdp_pid_user() {
  pid="$1"
  if command -v ps >/dev/null 2>&1; then
    set -- $(ps -p "$pid" -o user= 2>/dev/null)
    printf '%s\n' "${1:-}"
  fi
}

cdp_pid_command() {
  pid="$1"
  if command -v ps >/dev/null 2>&1; then
    ps -ww -p "$pid" -o command= 2>/dev/null
  fi
}

cdp_command_profile_matches() {
  command_line="$1"
  expected_profile="$2"
  expected_canon="$(cdp_canonical_dir "$expected_profile")"

  python3 - "$command_line" "$expected_profile" "$expected_canon" <<'PY'
import os
import shlex
import sys
cmd = sys.argv[1]
expected_raw = os.path.abspath(os.path.expanduser(os.path.expandvars(sys.argv[2])))
expected = os.path.realpath(sys.argv[3])

for value in (expected_raw, expected):
    if f"--user-data-dir={value}" in cmd or f"--user-data-dir {value}" in cmd:
        sys.exit(0)

try:
    parts = shlex.split(cmd)
except Exception:
    parts = cmd.split()
values = []
for i, part in enumerate(parts):
    if part.startswith("--user-data-dir="):
        values.append(part.split("=", 1)[1])
    elif part == "--user-data-dir" and i + 1 < len(parts):
        values.append(parts[i + 1])
for value in values:
    if os.path.realpath(os.path.abspath(os.path.expanduser(os.path.expandvars(value)))) == expected:
        sys.exit(0)
sys.exit(1)
PY
}

cdp_validate_listener() {
  # Usage: cdp_validate_listener PORT PROFILE_DIR CONTEXT
  # Returns 0 if no listener or a matching current-user Chrome listener is found.
  # Returns non-zero with a clear message for occupied/wrong listeners.
  port="$1"
  profile_dir="$2"
  context="${3:-runtime}"
  os_name="$(uname -s 2>/dev/null || echo unknown)"
  current_user="$(id -un 2>/dev/null || whoami 2>/dev/null || echo unknown)"

  if ! cdp_http_ready "$port"; then
    # If there is a non-CDP listener, fail before Chrome/MCP silently misbehaves.
    pids="$(cdp_listener_pids "$port" | tr '\n' ' ')"
    if [ -n "$pids" ]; then
      echo "ERROR: cdp-chrome port $port is occupied, but /json/version is not a Chrome DevTools endpoint." >&2
      echo "Choose a different cdp-chrome.port in $(cdp_config_path) and rerun setup/doctor." >&2
      return 1
    fi
    return 0
  fi

  if ! command -v lsof >/dev/null 2>&1 || ! command -v ps >/dev/null 2>&1; then
    if [ "$os_name" = "Darwin" ]; then
      echo "ERROR: cannot inspect cdp-chrome listener ownership/profile on macOS; lsof and ps are required." >&2
      return 1
    fi
    echo "WARNING: cdp-chrome on port $port responds, but ownership/profile could not be inspected on this platform." >&2
    return 0
  fi

  pids="$(cdp_listener_pids "$port")"
  if [ -z "$pids" ]; then
    if [ "$os_name" = "Darwin" ]; then
      echo "ERROR: cdp-chrome port $port responds, but lsof could not identify the listener on macOS." >&2
      echo "Refusing to use it to avoid connecting to another user's Chrome. Choose another cdp-chrome.port in $(cdp_config_path)." >&2
      return 1
    fi
    echo "WARNING: cdp-chrome port $port responds, but listener PID could not be inspected." >&2
    return 0
  fi

  for pid in $pids; do
    owner="$(cdp_pid_user "$pid")"
    cmd="$(cdp_pid_command "$pid")"
    if [ -z "$owner" ] || [ -z "$cmd" ]; then
      if [ "$os_name" = "Darwin" ]; then
        echo "ERROR: cannot inspect process $pid for cdp-chrome port $port on macOS." >&2
        return 1
      fi
      echo "WARNING: cannot inspect process $pid for cdp-chrome port $port; accepting best-effort." >&2
      continue
    fi
    if [ "$owner" != "$current_user" ]; then
      echo "ERROR: cdp-chrome port $port is owned by OS user '$owner', not current user '$current_user'." >&2
      echo "Choose a different cdp-chrome.port in $(cdp_config_path) for this OS user." >&2
      return 1
    fi
    case "$cmd" in
      *Google\ Chrome*|*Chromium*|*Chrome*|*chrome*) ;;
      *)
        echo "ERROR: cdp-chrome port $port is owned by current user but process $pid does not look like Chrome." >&2
        echo "Choose a different cdp-chrome.port in $(cdp_config_path) or stop the conflicting process." >&2
        return 1
        ;;
    esac
    if ! cdp_command_profile_matches "$cmd" "$profile_dir"; then
      echo "ERROR: Chrome on cdp-chrome port $port is not using configured profile_dir:" >&2
      echo "  expected: $(cdp_canonical_dir "$profile_dir")" >&2
      echo "  process:  $pid" >&2
      echo "Choose a different cdp-chrome.port in $(cdp_config_path) or stop/restart Chrome with the configured profile." >&2
      return 1
    fi
  done

  echo "cdp-chrome $context check OK: port $port is current user '$current_user' with profile $(cdp_canonical_dir "$profile_dir")"
  return 0
}
