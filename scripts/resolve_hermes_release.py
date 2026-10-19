#!/usr/bin/env python3
"""Resolve the Hermes Agent release that the Dockerfile should pin.

Source of truth is the `stable` tag published by Nous Research on Docker Hub.
We follow its digest back to the matching `vX.Y.Z` tag so the pin stays both
human-readable and immutable:

    FROM nousresearch/hermes-agent:v0.22.2@sha256:3609...

`stable` is used rather than "newest tag wins" so release candidates and the
`-desktop` image variants can never be picked up by accident.

Usage:
    resolve_hermes_release.py                    # print resolved release as JSON
    resolve_hermes_release.py --current          # add the currently pinned release
    resolve_hermes_release.py --write            # update Dockerfile + README
    resolve_hermes_release.py --pin v0.22.1      # resolve one specific version

Exits non-zero when a release cannot be resolved with confidence. Never
falls back to a guess: a wrong pin would be deployed straight to production.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

IMAGE = "nousresearch/hermes-agent"
CHANNEL = "stable"

HUB_TAGS = f"https://hub.docker.com/v2/repositories/{IMAGE}/tags"
REGISTRY = "https://registry-1.docker.io/v2"
AUTH = "https://auth.docker.io/token"

MANIFEST_TYPES = ",".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)

# v0.22.2 — not v0.22.2-desktop, not rc.2-v0.22.2, not the old CalVer v2026.8.3
SEMVER_TAG = re.compile(r"^v\d+\.\d+\.\d+$")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCKERFILE = os.path.join(ROOT, "Dockerfile")
README = os.path.join(ROOT, "README.md")

# FROM nousresearch/hermes-agent:<tag>@sha256:<digest>
PIN = re.compile(
    r"(?P<image>" + re.escape(IMAGE) + r"):(?P<tag>[\w.\-]+)@(?P<digest>sha256:[0-9a-f]{64})"
)


class ResolveError(RuntimeError):
    """Raised when the release cannot be determined with confidence."""


def _get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_tags(max_pages: int = 5) -> list[dict]:
    """Return Docker Hub tags, newest first, across a few pages."""
    tags: list[dict] = []
    url = f"{HUB_TAGS}?page_size=100&ordering=last_updated"
    for _ in range(max_pages):
        page = _get_json(url)
        tags.extend(page.get("results", []))
        url = page.get("next")
        if not url:
            break
    if not tags:
        raise ResolveError("Docker Hub returned no tags for " + IMAGE)
    return tags


def resolve(pin: str | None = None) -> dict:
    """Resolve the release to pin: {'tag': 'v0.22.2', 'digest': 'sha256:...'}."""
    tags = fetch_tags()
    by_name = {t["name"]: t for t in tags if t.get("digest")}

    if pin:
        if pin not in by_name:
            raise ResolveError(f"tag {pin!r} not found on Docker Hub for {IMAGE}")
        if not SEMVER_TAG.match(pin):
            raise ResolveError(f"tag {pin!r} is not a plain vX.Y.Z release tag")
        return {"tag": pin, "digest": by_name[pin]["digest"]}

    channel = by_name.get(CHANNEL)
    if not channel:
        raise ResolveError(f"no {CHANNEL!r} tag published for {IMAGE}")
    digest = channel["digest"]

    # Walk back from the digest to the release tag that shares it.
    named = sorted(
        (t["name"] for t in tags if t.get("digest") == digest and SEMVER_TAG.match(t["name"])),
        key=version_key,
        reverse=True,
    )
    if not named:
        raise ResolveError(
            f"{CHANNEL} points at {digest} but no vX.Y.Z tag shares that digest; "
            "refusing to guess a version number"
        )
    return {"tag": named[0], "digest": digest}


def version_key(tag: str) -> tuple[int, ...]:
    return tuple(int(part) for part in tag.lstrip("v").split("."))


def verify(tag: str, digest: str) -> None:
    """Confirm the digest really resolves in the registry before we pin it."""
    token = _get_json(f"{AUTH}?service=registry.docker.io&scope=repository:{IMAGE}:pull")["token"]
    headers = {"Authorization": f"Bearer {token}", "Accept": MANIFEST_TYPES}
    for ref in (tag, digest):
        req = urllib.request.Request(
            f"{REGISTRY}/{IMAGE}/manifests/{ref}", headers=headers, method="HEAD"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                got = resp.headers.get("Docker-Content-Digest")
        except urllib.error.HTTPError as exc:
            raise ResolveError(f"{IMAGE}:{ref} does not resolve in the registry ({exc.code})")
        if got != digest:
            raise ResolveError(f"{IMAGE}:{ref} resolves to {got}, expected {digest}")


def current() -> dict:
    with open(DOCKERFILE, encoding="utf-8") as fh:
        match = PIN.search(fh.read())
    if not match:
        raise ResolveError(f"no pinned {IMAGE} reference found in Dockerfile")
    return {"tag": match.group("tag"), "digest": match.group("digest")}


def write(tag: str, digest: str) -> list[str]:
    """Rewrite every pinned reference. Returns the files actually changed."""
    replacement = f"{IMAGE}:{tag}@{digest}"
    changed = []
    for path in (DOCKERFILE, README):
        with open(path, encoding="utf-8") as fh:
            before = fh.read()
        after = PIN.sub(replacement, before)
        if after != before:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(after)
            changed.append(os.path.relpath(path, ROOT))
    return changed


def emit(payload: dict, github_output: str | None) -> None:
    print(json.dumps(payload, indent=2))
    if not github_output:
        return
    with open(github_output, "a", encoding="utf-8") as fh:
        for key, value in payload.items():
            if isinstance(value, bool):
                value = str(value).lower()
            elif isinstance(value, list):
                # Space-joined so the workflow can pass it straight to `git add`.
                value = " ".join(value)
            fh.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pin", metavar="vX.Y.Z", help="resolve this release instead of stable")
    parser.add_argument("--current", action="store_true", help="also report the current pin")
    parser.add_argument("--write", action="store_true", help="update Dockerfile and README")
    parser.add_argument("--no-verify", action="store_true", help="skip the registry check")
    args = parser.parse_args()

    try:
        target = resolve(args.pin)
        if not args.no_verify:
            verify(target["tag"], target["digest"])
        payload = {"tag": target["tag"], "digest": target["digest"]}

        if args.current or args.write:
            now = current()
            payload["current_tag"] = now["tag"]
            payload["current_digest"] = now["digest"]
            payload["changed"] = now != target

        if args.write and payload["changed"]:
            payload["files"] = write(target["tag"], target["digest"])
    except (ResolveError, urllib.error.URLError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    emit(payload, os.environ.get("GITHUB_OUTPUT"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
