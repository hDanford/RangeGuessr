#!/usr/bin/env python3
"""
extend_schedule.py - Extend the RangeGuessr daily schedule

Reads the current data/schedule.js, finds the last scheduled date,
and appends more days without repeating recently used animals.

USAGE:
    cd pipeline
    python3 extend_schedule.py           # adds 90 more days (default)
    python3 extend_schedule.py 180       # adds 180 more days

Then commit and push data/schedule.js.
"""

import os
import re
import sys
import random
from datetime import date, timedelta

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT    = os.path.dirname(SCRIPT_DIR)
SCHEDULE_JS  = os.path.join(REPO_ROOT, "data", "schedule.js")
ANIMALS_JS   = os.path.join(REPO_ROOT, "data", "animals.js")

def load_animal_ids():
    with open(ANIMALS_JS, encoding="utf-8") as f:
        content = f.read()
    return re.findall(r'id:"([^"]+)"', content)

def load_schedule(path):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    pairs = re.findall(r'"(\d{4}-\d{2}-\d{2})"\s*:\s*"([^"]+)"', content)
    return {d: a for d, a in pairs}, content

def extend_schedule(schedule, animal_ids, extra_days):
    if not schedule:
        last_date = date.today() - timedelta(days=1)
    else:
        last_date = date.fromisoformat(max(schedule.keys()))

    # Build a pool that avoids repeating the last N animals
    # where N = min(len(animals)-1, 10)
    recent_count = min(len(animal_ids) - 1, 10)
    sorted_dates = sorted(schedule.keys())
    recent = [schedule[d] for d in sorted_dates[-recent_count:]] if sorted_dates else []

    new_entries = {}
    pool = []

    for i in range(extra_days):
        if not pool:
            available = [a for a in animal_ids if a not in recent[-recent_count:]]
            if not available:
                available = animal_ids[:]
            random.shuffle(available)
            pool = available

        next_date = last_date + timedelta(days=i + 1)
        animal_id = pool.pop(0)
        recent.append(animal_id)
        new_entries[next_date.strftime("%Y-%m-%d")] = animal_id

    return new_entries

def write_schedule(path, schedule, new_entries):
    all_entries = {**schedule, **new_entries}
    sorted_entries = sorted(all_entries.items())

    lines = [
        "// data/schedule.js - Daily animal schedule",
        "// Edit by hand or run: python3 pipeline/extend_schedule.py",
        "// Add new dates at the bottom to extend the schedule",
        "// If today's date is not in the schedule, the game falls back to the hash-based daily",
        "",
        "const SCHEDULE = {",
    ]
    for date_str, animal_id in sorted_entries:
        lines.append(f'  "{date_str}": "{animal_id}",')
    lines.append("};")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return len(sorted_entries)

def main():
    extra_days = int(sys.argv[1]) if len(sys.argv) > 1 else 90

    print("=" * 50)
    print("RangeGuessr - Extend Schedule")
    print("=" * 50)

    animal_ids = load_animal_ids()
    print(f"\nLoaded {len(animal_ids)} animals from animals.js")

    if not os.path.exists(SCHEDULE_JS):
        print("ERROR: data/schedule.js not found")
        sys.exit(1)

    schedule, _ = load_schedule(SCHEDULE_JS)
    print(f"Current schedule: {len(schedule)} days")

    if schedule:
        last = max(schedule.keys())
        print(f"Last scheduled date: {last}")
    
    new_entries = extend_schedule(schedule, animal_ids, extra_days)
    
    first_new = min(new_entries.keys())
    last_new  = max(new_entries.keys())
    
    total = write_schedule(SCHEDULE_JS, schedule, new_entries)

    print(f"\nAdded {extra_days} days: {first_new} to {last_new}")
    print(f"Schedule now covers {total} days total")
    print(f"\nDone. Commit and push data/schedule.js to make it live.")

if __name__ == "__main__":
    main()
