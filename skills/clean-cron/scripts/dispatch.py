#!/usr/bin/env python3
"""
Clean-cron dispatcher: read tasks.yaml, match cron expressions, run matching tasks.
Called by launchd every minute via: cat dispatch.py | python3
"""

import os
import sys
import subprocess
import random
from datetime import datetime

# --- YAML parsing (minimal, no pyyaml fallback) ---
try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run: pip3 install pyyaml", file=sys.stderr)
    sys.exit(1)

# --- Cron expression matching ---

def _field_match(pattern, value, max_val):
    """Match a single cron field against a value."""
    if pattern == "*":
        return True
    for part in pattern.split(","):
        if "/" in part:
            base, step = part.split("/", 1)
            step = int(step)
            if base == "*":
                if value % step == 0:
                    return True
            elif "-" in base:
                lo, hi = map(int, base.split("-", 1))
                if lo <= value <= hi and (value - lo) % step == 0:
                    return True
        elif "-" in part:
            lo, hi = map(int, part.split("-", 1))
            if lo <= value <= hi:
                return True
        else:
            if int(part) == value:
                return True
    return False


def cron_match(expr, now):
    """Match a 5-field cron expression against a datetime."""
    fields = expr.strip().split()
    if len(fields) != 5:
        return False
    minute, hour, dom, month, dow = fields
    # cron: 0=Sunday, python: 0=Monday → convert
    py_dow = now.isoweekday() % 7  # Mon=1..Sun=0 in cron convention
    return (
        _field_match(minute, now.minute, 59)
        and _field_match(hour, now.hour, 23)
        and _field_match(dom, now.day, 31)
        and _field_match(month, now.month, 12)
        and _field_match(dow, py_dow, 7)
    )


# --- Main ---

def main():
    tasks_file = os.path.expanduser("~/.config/clean-cron/tasks.yaml")
    if not os.path.exists(tasks_file):
        return

    with open(tasks_file) as f:
        config = yaml.safe_load(f)

    if not config or "tasks" not in config:
        return

    now = datetime.now()

    for task in config["tasks"]:
        name = task.get("name", "unnamed")
        schedule = task.get("schedule", "")
        shell = task.get("shell", "")
        delay = task.get("delay", 0)  # random delay 0-N minutes

        if not schedule or not shell:
            continue

        if cron_match(schedule, now):
            # If delay is set, generate random delay and prepend sleep to shell
            if delay and delay > 0:
                delay_minutes = random.randint(0, int(delay))
                print(f"{now:%Y-%m-%d %H:%M:%S}: running {name} (delay: {delay_minutes}m)")
                shell = f"sleep {delay_minutes}m\n{shell}"
            else:
                print(f"{now:%Y-%m-%d %H:%M:%S}: running {name}")
            # Execute shell via bash in background, using echo|bash to avoid provenance issues
            subprocess.Popen(
                ["/bin/bash", "-c", shell],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,  # detach from parent process group
                env={
                    **os.environ,
                    "PATH": f"/opt/homebrew/bin:{os.path.expanduser('~/.local/bin')}:/usr/bin:/bin",
                    "HOME": os.path.expanduser("~"),
                },
            )


if __name__ == "__main__":
    main()
