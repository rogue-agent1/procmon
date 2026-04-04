#!/usr/bin/env python3
"""procmon - process monitor with top/search/tree/watch capabilities."""

import argparse, subprocess, sys, time, os, re

def get_processes(sort_by="cpu"):
    """Get process list via ps."""
    flag = "-r" if sort_by == "cpu" else "-m"
    r = subprocess.run(
        ["ps", flag, "-e", "-o", "pid,ppid,%cpu,%mem,rss,user,comm"],
        capture_output=True, text=True
    )
    procs = []
    for line in r.stdout.strip().splitlines()[1:]:
        parts = line.split(None, 6)
        if len(parts) < 7:
            continue
        try:
            procs.append({
                "pid": int(parts[0]),
                "ppid": int(parts[1]),
                "cpu": float(parts[2]),
                "mem": float(parts[3]),
                "rss": int(parts[4]),
                "user": parts[5],
                "comm": parts[6],
            })
        except (ValueError, IndexError):
            continue
    return procs

def fmt_size(kb):
    if kb >= 1048576:
        return f"{kb/1048576:.1f}G"
    if kb >= 1024:
        return f"{kb/1024:.1f}M"
    return f"{kb}K"

def bar(val, mx, width=15):
    if mx == 0:
        return " " * width
    filled = int((val / mx) * width)
    return "█" * filled + "░" * (width - filled)

def cmd_top(args):
    procs = get_processes(args.sort)
    n = args.num
    print(f"\n{'PID':>7}  {'USER':<10} {'CPU%':>5} {'MEM%':>5} {'RSS':>7}  {'BAR':<15}  COMMAND")
    print("─" * 75)
    mx = max((p["cpu"] if args.sort == "cpu" else p["mem"]) for p in procs[:n]) if procs else 1
    for p in procs[:n]:
        val = p["cpu"] if args.sort == "cpu" else p["mem"]
        b = bar(val, max(mx, 0.1))
        comm = os.path.basename(p["comm"])[:20]
        print(f"{p['pid']:>7}  {p['user']:<10} {p['cpu']:>5.1f} {p['mem']:>5.1f} {fmt_size(p['rss']):>7}  {b}  {comm}")
    print()

def cmd_search(args):
    pattern = args.pattern.lower()
    procs = get_processes("cpu")
    matches = [p for p in procs if pattern in p["comm"].lower() or pattern in str(p["pid"])]
    if not matches:
        print(f"No processes matching '{args.pattern}'")
        return
    print(f"\n{'PID':>7}  {'USER':<10} {'CPU%':>5} {'MEM%':>5} {'RSS':>7}  COMMAND")
    print("─" * 60)
    for p in matches:
        comm = os.path.basename(p["comm"])[:30]
        print(f"{p['pid']:>7}  {p['user']:<10} {p['cpu']:>5.1f} {p['mem']:>5.1f} {fmt_size(p['rss']):>7}  {comm}")
    print(f"\n  {len(matches)} process(es) found\n")

def cmd_tree(args):
    procs = get_processes("cpu")
    by_ppid = {}
    by_pid = {}
    for p in procs:
        by_pid[p["pid"]] = p
        by_ppid.setdefault(p["ppid"], []).append(p)

    root = args.pid or 1

    def print_tree(pid, prefix="", is_last=True):
        p = by_pid.get(pid)
        if not p:
            return
        connector = "└─ " if is_last else "├─ "
        comm = os.path.basename(p["comm"])[:25]
        print(f"{prefix}{connector}{pid} {comm} ({p['cpu']:.1f}% cpu, {fmt_size(p['rss'])})")
        children = by_ppid.get(pid, [])
        children.sort(key=lambda c: c["cpu"], reverse=True)
        ext = "   " if is_last else "│  "
        for i, child in enumerate(children[:args.max]):
            print_tree(child["pid"], prefix + ext, i == len(children[:args.max]) - 1)

    print(f"\nProcess tree from PID {root}:\n")
    print_tree(root, "", True)
    print()

def cmd_summary(args):
    procs = get_processes("cpu")
    total_cpu = sum(p["cpu"] for p in procs)
    total_mem = sum(p["mem"] for p in procs)
    total_rss = sum(p["rss"] for p in procs)
    users = {}
    for p in procs:
        u = p["user"]
        if u not in users:
            users[u] = {"count": 0, "cpu": 0, "mem": 0}
        users[u]["count"] += 1
        users[u]["cpu"] += p["cpu"]
        users[u]["mem"] += p["mem"]

    print(f"\n  System Summary")
    print(f"  ─────────────────────────────")
    print(f"  Processes: {len(procs)}")
    print(f"  Total CPU: {total_cpu:.1f}%")
    print(f"  Total MEM: {total_mem:.1f}% ({fmt_size(total_rss)})")
    print(f"\n  Top 5 CPU hogs:")
    for p in sorted(procs, key=lambda x: x["cpu"], reverse=True)[:5]:
        comm = os.path.basename(p["comm"])[:20]
        print(f"    {p['cpu']:>5.1f}%  {comm} (PID {p['pid']})")
    print(f"\n  Top 5 MEM hogs:")
    for p in sorted(procs, key=lambda x: x["rss"], reverse=True)[:5]:
        comm = os.path.basename(p["comm"])[:20]
        print(f"    {fmt_size(p['rss']):>7}  {comm} (PID {p['pid']})")
    print(f"\n  By user:")
    for u, s in sorted(users.items(), key=lambda x: x[1]["cpu"], reverse=True)[:8]:
        print(f"    {u:<12} {s['count']:>4} procs  {s['cpu']:>5.1f}% cpu  {s['mem']:>5.1f}% mem")
    print()

def cmd_watch(args):
    """Watch a specific PID over time."""
    pid = args.pid
    interval = args.interval
    history_cpu = []
    history_mem = []
    sparks = "▁▂▃▄▅▆▇█"

    def sparkline(data, width=20):
        if not data:
            return ""
        recent = data[-width:]
        mn, mx = min(recent), max(recent)
        rng = mx - mn if mx > mn else 1
        return "".join(sparks[min(int((v - mn) / rng * 7), 7)] for v in recent)

    print(f"Watching PID {pid} (Ctrl+C to stop)\n")
    try:
        while True:
            procs = get_processes("cpu")
            p = next((x for x in procs if x["pid"] == pid), None)
            if not p:
                print(f"PID {pid} not found")
                break
            history_cpu.append(p["cpu"])
            history_mem.append(p["mem"])
            comm = os.path.basename(p["comm"])
            cpu_spark = sparkline(history_cpu)
            mem_spark = sparkline(history_mem)
            print(f"\r  {comm} | CPU: {p['cpu']:>5.1f}% {cpu_spark} | MEM: {p['mem']:>4.1f}% ({fmt_size(p['rss'])}) {mem_spark}  ", end="", flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n")

def main():
    p = argparse.ArgumentParser(description="Process monitor")
    sp = p.add_subparsers(dest="cmd")

    t = sp.add_parser("top", help="Top processes")
    t.add_argument("-n", "--num", type=int, default=15)
    t.add_argument("-s", "--sort", choices=["cpu", "mem"], default="cpu")
    t.set_defaults(func=cmd_top)

    s = sp.add_parser("search", help="Search processes")
    s.add_argument("pattern")
    s.set_defaults(func=cmd_search)

    tr = sp.add_parser("tree", help="Process tree")
    tr.add_argument("--pid", type=int, default=1)
    tr.add_argument("--max", type=int, default=10, help="Max children per node")
    tr.set_defaults(func=cmd_tree)

    su = sp.add_parser("summary", help="System summary")
    su.set_defaults(func=cmd_summary)

    w = sp.add_parser("watch", help="Watch a PID over time")
    w.add_argument("pid", type=int)
    w.add_argument("-i", "--interval", type=float, default=1.0)
    w.set_defaults(func=cmd_watch)

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        sys.exit(1)
    args.func(args)

if __name__ == "__main__":
    main()
