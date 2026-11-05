#!/usr/bin/env python3
"""Maintain a tracking issue when a pinned Pandoc release falls behind upstream."""

import argparse
import json
import re
import subprocess
from pathlib import Path

MARKER = "<!-- pandoc-release-pin -->"


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True).strip()


def version(text):
    value = text.removeprefix("v")
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", value):
        raise ValueError(f"unexpected Pandoc release version: {text!r}")
    return tuple(map(int, value.split("."))) + (0,) * 8


def pinned_version(path, source):
    content = Path(path).read_text()
    if source == "shell":
        matches = re.findall(r'^PANDOC_VERSION="\$\{PANDOC_VERSION:-([0-9.]+)\}"$', content, re.M)
    else:
        matches = re.findall(r"^\s+pandoc: ['\"]([0-9.]+)['\"]$", content, re.M)
    if not matches:
        raise ValueError(f"no Pandoc pin found in {path}")
    return max(matches, key=version)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pin-file", required=True)
    parser.add_argument("--source", choices=("shell", "matrix"), required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-url", default="local dry run")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    pin = pinned_version(args.pin_file, args.source)
    latest = json.loads(gh("release", "view", "--repo", "jgm/pandoc", "--json", "tagName"))["tagName"]
    behind = version(pin) < version(latest)
    print(f"Pinned Pandoc {pin}; latest release {latest}; behind={str(behind).lower()}")
    if args.dry_run:
        return

    issues = json.loads(gh("issue", "list", "--repo", args.repo, "--state", "open",
                           "--limit", "1000", "--json", "number,body"))
    existing = next((issue["number"] for issue in issues if MARKER in (issue["body"] or "")), None)
    if behind:
        title = f"pinned Pandoc {pin} is behind the latest release {latest}"
        body = (f"{MARKER}\n\nThe newest Pandoc version in this repository's pin is "
                f"{pin}; [Pandoc {latest}](https://github.com/jgm/pandoc/releases/tag/{latest}) "
                f"is the latest stable release.\n\nLast checked by: {args.run_url}\n\n"
                "This tracking issue is refreshed by the scheduled workflow and closes "
                "when the pin catches up.\n")
        if existing:
            gh("issue", "edit", str(existing), "--repo", args.repo, "--title", title, "--body", body)
            print(f"Updated issue #{existing}")
        else:
            print(gh("issue", "create", "--repo", args.repo, "--title", title,
                     "--body", body, "--label", "chore", "--label", "area:tooling",
                     "--label", "tracking"))
    elif existing:
        gh("issue", "comment", str(existing), "--repo", args.repo,
           "--body", f"The pin has caught up with Pandoc {latest}. Checked by {args.run_url}.")
        gh("issue", "close", str(existing), "--repo", args.repo)
        print(f"Closed issue #{existing}")


if __name__ == "__main__":
    main()
