#!/usr/bin/env python3
"""procmon - Process monitor with resource tracking.

Single-file, zero-dependency CLI.
"""

import sys
import argparse
import subprocess
import re
import time


def get_processes(sort_by="cpu", limit=15):
    """Get top processes."""
    if sort_by == "mem":
        flag = "-m"
    else:
        flag = "-r"  # CPU
    try:
        out = subprocess.check_output(
            ["ps", "aux", "--sort" if sys.platform == "linux" else flag],
            text=True, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        out = subprocess.check_output(["ps", "aux"], text=True)
    lines = out.strip().split("\n")
    header = lines[0]
    procs = []
    for line in lines[1:limit+1]:
        parts = line.split(None, 10)
        if len(parts) >= 11:
            procs.append({
                "user": parts[0], "pid": parts[1],
                "cpu": float(parts[2]), "mem": float(parts[3]),
                "vsz": parts[4], "rss": parts[5],
                "command": parts[10][:60],
            })
    return procs


def cmd_top(args):
    procs = get_processes(args.sort, args.count)
    print(f"  {'PID':>7s}  {'CPU%':>5s}  {'MEM%':>5s}  {'USER':8s}  COMMAND")
    print(f"  {'-'*7}  {'-'*5}  {'-'*5}  {'-'*8}  {'-'*40}")
    for p in procs:
        cpu_bar = "█" * min(int(p["cpu"] / 5), 10)
        print(f"  {p['pid']:>7s}  {p['cpu']:5.1f}  {p['mem']:5.1f}  {p['user']:8s}  {p['command']}")


def cmd_find(args):
    """Find processes by name."""
    try:
        out = subprocess.check_output(["ps", "aux"], text=True)
    except subprocess.CalledProcessError:
        return 1
    query = args.name.lower()
    found = 0
    for line in out.strip().split("\n")[1:]:
        if query in line.lower():
            parts = line.split(None, 10)
            if len(parts) >= 11:
                print(f"  PID {parts[1]:>7s}  CPU {parts[2]:>5s}%  MEM {parts[3]:>5s}%  {parts[10][:70]}")
                found += 1
    if not found:
        print(f"  No processes matching '{args.name}'")


def cmd_watch(args):
    """Watch a process over time."""
    pid = args.pid
    interval = args.interval
    count = args.count
    print(f"  Watching PID {pid} every {interval}s...\n")
    print(f"  {'Time':8s}  {'CPU%':>5s}  {'MEM%':>5s}  {'RSS':>10s}")
    for i in range(count):
        try:
            out = subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "pcpu=,pmem=,rss="],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
            if out:
                parts = out.split()
                rss_mb = int(parts[2]) / 1024 if len(parts) >= 3 else 0
                ts = time.strftime("%H:%M:%S")
                print(f"  {ts}  {parts[0]:>5s}  {parts[1]:>5s}  {rss_mb:>8.1f}MB")
        except subprocess.CalledProcessError:
            print(f"  Process {pid} not found")
            return 1
        if i < count - 1:
            time.sleep(interval)


def cmd_summary(args):
    """System process summary."""
    out = subprocess.check_output(["ps", "aux"], text=True)
    lines = out.strip().split("\n")[1:]
    total_cpu = 0
    total_mem = 0
    for line in lines:
        parts = line.split(None, 10)
        if len(parts) >= 4:
            total_cpu += float(parts[2])
            total_mem += float(parts[3])
    print(f"  Processes: {len(lines)}")
    print(f"  Total CPU: {total_cpu:.1f}%")
    print(f"  Total MEM: {total_mem:.1f}%")


def main():
    p = argparse.ArgumentParser(prog="procmon", description="Process monitor")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("top", aliases=["t"], help="Top processes")
    s.add_argument("-s", "--sort", choices=["cpu", "mem"], default="cpu")
    s.add_argument("-n", "--count", type=int, default=15)
    s = sub.add_parser("find", aliases=["f"], help="Find process")
    s.add_argument("name")
    s = sub.add_parser("watch", aliases=["w"], help="Watch process")
    s.add_argument("pid", type=int)
    s.add_argument("-i", "--interval", type=float, default=2)
    s.add_argument("-n", "--count", type=int, default=10)
    sub.add_parser("summary", aliases=["s"], help="Process summary")
    args = p.parse_args()
    if not args.cmd: p.print_help(); return 1
    cmds = {"top": cmd_top, "t": cmd_top, "find": cmd_find, "f": cmd_find,
            "watch": cmd_watch, "w": cmd_watch, "summary": cmd_summary, "s": cmd_summary}
    return cmds[args.cmd](args) or 0


if __name__ == "__main__":
    sys.exit(main())
