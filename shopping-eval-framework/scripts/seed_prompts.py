"""
Seed (or update) all agent prompts in Langfuse.

Run once to bootstrap prompt management, or whenever you want to push
a new prompt version. Each call to create_prompt() with an existing name
creates a new version — this is intentional so the edit history is preserved.

Usage:
    python scripts/seed_prompts.py                   # create initial versions
    python scripts/seed_prompts.py --force           # always create new version
    python scripts/seed_prompts.py --check           # print current versions, no writes

Requires LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY in environment or .env.
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from langfuse import get_client  # noqa: E402
from agent.prompts import PROMPT_DEFINITIONS  # noqa: E402


def check_versions(lf) -> dict:
    """Return {name: version} for each prompt that exists in Langfuse."""
    versions = {}
    for name in PROMPT_DEFINITIONS:
        try:
            p = lf.get_prompt(name, label="production")
            versions[name] = p.version
        except Exception:
            versions[name] = None
    return versions


def seed(force: bool = False) -> None:
    if not os.getenv("LANGFUSE_PUBLIC_KEY"):
        print("ERROR: LANGFUSE_PUBLIC_KEY not set. Add it to .env first.")
        sys.exit(1)

    lf = get_client()
    versions = check_versions(lf)

    for name, defn in PROMPT_DEFINITIONS.items():
        existing = versions.get(name)
        if existing is not None and not force:
            print(f"  {name:<28} already exists (version {existing}) — skipping")
            print(f"    → run with --force to create a new version")
            continue

        action = "Updating" if existing is not None else "Creating"
        print(f"  {action} '{name}' ...", end=" ")
        lf.create_prompt(
            name=name,
            type=defn["type"],
            prompt=defn["prompt"],
            labels=["production"],
        )
        new_p = lf.get_prompt(name, label="production")
        print(f"version {new_p.version}")

    lf.flush()
    print("\nDone. View prompts at: https://cloud.langfuse.com → Prompts")


def main():
    parser = argparse.ArgumentParser(description="Seed Langfuse prompts")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Always create a new version even if prompt already exists",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Print current versions without writing anything",
    )
    args = parser.parse_args()

    if not os.getenv("LANGFUSE_PUBLIC_KEY"):
        print("ERROR: LANGFUSE_PUBLIC_KEY not set. Add it to .env first.")
        sys.exit(1)

    lf = get_client()

    if args.check:
        print("\nCurrent prompt versions in Langfuse:")
        for name, version in check_versions(lf).items():
            status = f"version {version}" if version is not None else "NOT FOUND"
            print(f"  {name:<28} {status}")
        return

    print("\nSeeding prompts into Langfuse...")
    seed(force=args.force)


if __name__ == "__main__":
    main()
