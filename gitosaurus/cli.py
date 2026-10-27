"""Usage: python -m gitosaurus.cli <repo> <path/in/repo> <line> [end_line] [--model TAG]"""
import argparse

from .story import explain_range
from .llm import DEFAULT_MODEL


def main() -> None:
    p = argparse.ArgumentParser(prog="gitosaurus")
    p.add_argument("repo")
    p.add_argument("path")
    p.add_argument("line", type=int)
    p.add_argument("end_line", type=int, nargs="?")
    p.add_argument("--model", default=DEFAULT_MODEL)
    a = p.parse_args()
    r = explain_range(a.repo, a.path, a.line, a.end_line or a.line, a.model)
    print(f"\n{a.path}:{r['start']}-{r['end']}\n{r['code']}\n")
    print(r["answer"])
    for c in r["commits"]:
        print(f"\nOrigin: {c.sha[:7]} {c.date} {c.author} - {c.subject}  ({c.lines} line(s))")


if __name__ == "__main__":
    main()
