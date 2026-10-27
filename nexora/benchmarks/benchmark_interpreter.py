"""Small, repeatable end-to-end benchmarks for the NEXORA interpreter.

Run from the nexora/ directory with ``python benchmarks/benchmark_interpreter.py``.
Each measurement includes analysis and execution through the same API as ``nex run``.
"""

from __future__ import annotations

import argparse
import statistics
import time
import tracemalloc

from nexora.api import run_source


PROGRAMS = {
    "fib(20)": """
fn fib(n: Int) gives Int {
    if n < 2 {
        return n
    }
    return fib(n - 1) + fib(n - 2)
}
fn main() { print(fib(20)) }
""",
    "while 100000": """
fn main() {
    var i = 0
    var total = 0
    while i < 100000
        shrinks 100000 - i
    {
        total = total + i
        i = i + 1
    }
    print(total)
}
""",
    "list append 1000": """
fn main() {
    var xs: List[Int] = []
    var i = 0
    while i < 1000
        shrinks 1000 - i
    {
        xs = List.append(xs, i)
        i = i + 1
    }
    print(List.length(xs))
}
""",
}


def run_checked(source: str) -> None:
    result = run_source(source, filename="benchmark.nex")
    if result["status"] != "success":
        raise RuntimeError(f"Benchmark program failed: {result}")


def measure_time(source: str, repeats: int) -> float:
    durations: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        run_checked(source)
        durations.append(time.perf_counter() - started)
    return statistics.median(durations)


def measure_peak_memory(source: str, repeats: int) -> int:
    peak = 0
    for _ in range(repeats):
        tracemalloc.start()
        try:
            run_checked(source)
            _, run_peak = tracemalloc.get_traced_memory()
            peak = max(peak, run_peak)
        finally:
            tracemalloc.stop()
    return peak


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    print(f"Median of {args.repeats} untraced timing runs; separate traced memory runs")
    print("Benchmark | seconds | peak MiB")
    for name, source in PROGRAMS.items():
        seconds = measure_time(source, args.repeats)
        peak = measure_peak_memory(source, args.repeats)
        print(f"{name} | {seconds:.3f} | {peak / 1024 / 1024:.2f}")


if __name__ == "__main__":
    main()
