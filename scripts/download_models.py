#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.request


def expand(value):
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [expand(v) for v in value]
    if isinstance(value, dict):
        return {k: expand(v) for k, v in value.items()}
    return value


def cleaned_headers(raw):
    headers = {}
    for key, value in (raw or {}).items():
        value = expand(str(value)).strip()
        if not value:
            continue
        if key.lower() == "authorization" and value.lower() in {"bearer", "bearer ${hf_token}", "bearer ${civitai_token}"}:
            continue
        if key.lower() == "authorization" and value.lower().startswith("bearer ") and len(value.split(" ", 1)[1].strip()) == 0:
            continue
        headers[key] = value
    return headers


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024 * 8), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def resolve_download_url(url, headers, timeout=90):
    request = urllib.request.Request(url, headers=headers | {"User-Agent": headers.get("User-Agent", "runpod-ltx-template")})
    response = urllib.request.urlopen(request, timeout=timeout)
    try:
        return response.geturl()
    finally:
        response.close()


def run_aria2(url, output, connections, splits):
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "aria2c",
        "-x",
        str(connections),
        "-s",
        str(splits),
        "-k",
        "1M",
        "--continue=true",
        "--allow-overwrite=true",
        "--auto-file-renaming=false",
        "--summary-interval=10",
        "--console-log-level=warn",
        "-d",
        str(output.parent),
        "-o",
        output.name,
        url,
    ]
    subprocess.run(cmd, check=True)


def run_urllib(url, output, headers):
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    request = urllib.request.Request(url, headers=headers | {"User-Agent": headers.get("User-Agent", "runpod-ltx-template")})
    with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as handle:
        shutil.copyfileobj(response, handle, length=1024 * 1024 * 8)
    tmp.replace(output)


def download(entry, root, use_aria2, connections, splits):
    entry = expand(entry)
    name = entry.get("name") or entry.get("path")
    url = entry["url"]
    output = root / entry["path"]
    expected_sha = (entry.get("sha256") or "").upper()
    required = entry.get("required", True)
    headers = cleaned_headers(entry.get("headers"))

    if output.exists() and output.stat().st_size > 0:
        if expected_sha:
            actual_sha = sha256_file(output)
            if actual_sha == expected_sha:
                print(f"OK existing: {name}")
                return
            print(f"SHA mismatch, redownloading: {name}", file=sys.stderr)
            output.unlink()
        else:
            print(f"SKIP existing: {name}")
            return

    try:
        print(f"DOWNLOAD: {name}")
        if use_aria2 and shutil.which("aria2c"):
            final_url = resolve_download_url(url, headers)
            run_aria2(final_url, output, connections, splits)
        else:
            run_urllib(url, output, headers)

        if expected_sha:
            actual_sha = sha256_file(output)
            if actual_sha != expected_sha:
                raise RuntimeError(f"sha256 mismatch for {output.name}: expected {expected_sha}, got {actual_sha}")
    except Exception as exc:
        if required:
            raise
        print(f"WARN optional model failed: {name}: {exc}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--no-aria2", action="store_true")
    parser.add_argument("--connections", type=int, default=int(os.environ.get("ARIA2_CONNECTIONS", "16")))
    parser.add_argument("--splits", type=int, default=int(os.environ.get("ARIA2_SPLITS", "16")))
    args = parser.parse_args()

    root = pathlib.Path(args.root)
    manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
    for entry in manifest.get("models", []):
        if not entry.get("enabled", True):
            print(f"SKIP disabled: {entry.get('name') or entry.get('path')}")
            continue
        download(entry, root, not args.no_aria2, args.connections, args.splits)


if __name__ == "__main__":
    main()
