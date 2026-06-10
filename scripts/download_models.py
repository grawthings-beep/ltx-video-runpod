#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed


def log(message, *, error=False):
    print(message, file=sys.stderr if error else sys.stdout, flush=True)


def extract_archive(archive, dest_dir, what):
    """Extract members of a zip into dest_dir (flattened to basenames).

    `what` selects which members to keep: a comma-separated extension list
    (e.g. "pt" or "pt,safetensors") or a truthy value ("all"/"*"/True) for
    everything. Subdirectories in the archive are flattened. The archive is
    removed afterwards. Returns the list of extracted filenames.
    """
    exts = None
    if isinstance(what, str) and what.strip().lower() not in ("", "1", "true", "all", "*"):
        exts = {"." + e.strip().lstrip(".").lower() for e in what.split(",") if e.strip()}
    dest_dir.mkdir(parents=True, exist_ok=True)
    extracted = []
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():
            base = os.path.basename(member)
            if not base or member.endswith("/"):
                continue
            if exts and os.path.splitext(base)[1].lower() not in exts:
                continue
            target = dest_dir / base
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024 * 8)
            extracted.append(base)
    archive.unlink()
    return extracted


def expand(value):
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [expand(v) for v in value]
    if isinstance(value, dict):
        return {k: expand(v) for k, v in value.items()}
    return value


def has_unresolved_template(value):
    if not isinstance(value, str):
        return False
    return bool(re.search(r"\{\{.+?\}\}|\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$[A-Za-z_][A-Za-z0-9_]*", value))


def missing_required_env(names):
    missing = []
    for name in names or []:
        value = os.environ.get(str(name), "").strip()
        if not value or has_unresolved_template(value):
            missing.append(str(name))
    return missing


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


def sha256_file(path, name):
    digest = hashlib.sha256()
    total = path.stat().st_size
    processed = 0
    started = time.monotonic()
    last_report = started
    log(f"VERIFY: {name} ({total / (1024 ** 3):.2f} GiB)")
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024 * 8), b""):
            digest.update(chunk)
            processed += len(chunk)
            now = time.monotonic()
            if now - last_report >= 10:
                elapsed = max(now - started, 0.001)
                percent = processed * 100 / total if total else 100
                speed = processed / elapsed / (1024 ** 2)
                log(f"VERIFY: {name} {percent:.1f}% ({speed:.1f} MiB/s)")
                last_report = now
    elapsed = max(time.monotonic() - started, 0.001)
    speed = processed / elapsed / (1024 ** 2)
    log(f"VERIFIED: {name} ({speed:.1f} MiB/s)")
    return digest.hexdigest().upper()


def verification_marker(path):
    return path.with_name(path.name + ".sha256.json")


def has_cached_verification(path, expected_sha):
    marker = verification_marker(path)
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        stat = path.stat()
        return (
            data.get("sha256") == expected_sha
            and data.get("size") == stat.st_size
            and data.get("mtime_ns") == stat.st_mtime_ns
        )
    except (OSError, ValueError, TypeError):
        return False


def write_verification_marker(path, expected_sha):
    stat = path.stat()
    marker = verification_marker(path)
    marker.write_text(
        json.dumps(
            {
                "sha256": expected_sha,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def remove_verification_marker(path):
    marker = verification_marker(path)
    if marker.exists():
        marker.unlink()


def verify_sha256(path, expected_sha, name, mode):
    if mode == "never":
        log(f"SKIP hash verification: {name}")
        return True
    if mode == "once" and has_cached_verification(path, expected_sha):
        log(f"OK verified cache: {name}")
        return True

    actual_sha = sha256_file(path, name)
    if actual_sha != expected_sha:
        remove_verification_marker(path)
        log(
            f"SHA mismatch for {name}: expected {expected_sha}, got {actual_sha}",
            error=True,
        )
        return False

    write_verification_marker(path, expected_sha)
    return True


def resolve_download_url(url, headers, timeout=90):
    request_headers = headers | {
        "User-Agent": headers.get("User-Agent", "runpod-ltx-template")
    }
    request = urllib.request.Request(url, headers=request_headers, method="HEAD")
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError:
        request = urllib.request.Request(
            url,
            headers=request_headers | {"Range": "bytes=0-0"},
        )
        response = urllib.request.urlopen(request, timeout=timeout)
    try:
        return response.geturl()
    finally:
        response.close()


def parse_huggingface_url(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname not in {"huggingface.co", "www.huggingface.co"}:
        return None

    parts = parsed.path.strip("/").split("/")
    if len(parts) < 5 or parts[2] != "resolve":
        return None

    repo_id = "/".join(parts[:2])
    revision = urllib.parse.unquote(parts[3])
    filename = urllib.parse.unquote("/".join(parts[4:]))
    if not repo_id or not revision or not filename:
        return None
    return repo_id, revision, filename


def bearer_token(headers):
    authorization = headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip() or None
    return None


def run_hf_hub(url, output, headers):
    from huggingface_hub import hf_hub_download

    parsed = parse_huggingface_url(url)
    if not parsed:
        raise ValueError(f"not a supported Hugging Face resolve URL: {url}")

    repo_id, revision, filename = parsed
    output.parent.mkdir(parents=True, exist_ok=True)
    log(f"HF_XET: {repo_id}/{filename} (revision {revision})")
    downloaded = pathlib.Path(
        hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            revision=revision,
            local_dir=str(output.parent),
            token=bearer_token(headers),
        )
    )

    if downloaded.resolve() != output.resolve():
        output.parent.mkdir(parents=True, exist_ok=True)
        downloaded.replace(output)


def partial_path(output):
    return output.with_name(output.name + ".part")


def migrate_legacy_aria_download(output):
    legacy_control = output.with_name(output.name + ".aria2")
    if not output.exists() or not legacy_control.exists():
        return

    partial = partial_path(output)
    partial_control = partial.with_name(partial.name + ".aria2")
    if partial.exists():
        if output.stat().st_size > partial.stat().st_size:
            partial.unlink()
            output.replace(partial)
        else:
            output.unlink()
    else:
        output.replace(partial)

    if not partial_control.exists():
        legacy_control.replace(partial_control)
    else:
        legacy_control.unlink()
    log(f"RESUME legacy partial download: {output.name}")


def run_aria2(url, output, connections, splits):
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = partial_path(output)
    cmd = [
        "aria2c",
        "-x",
        str(connections),
        "-s",
        str(splits),
        "-k",
        "1M",
        "--min-split-size=1M",
        "--continue=true",
        "--allow-overwrite=true",
        "--auto-file-renaming=false",
        "--file-allocation=none",
        "--max-tries=5",
        "--retry-wait=3",
        "--connect-timeout=30",
        "--timeout=60",
        "--summary-interval=10",
        "--console-log-level=warn",
        "-d",
        str(partial.parent),
        "-o",
        partial.name,
        url,
    ]
    subprocess.run(cmd, check=True)
    partial.replace(output)


def run_curl(url, output, headers):
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = partial_path(output)

    cmd = [
        "curl",
        "-fL",
        "--retry",
        "5",
        "--retry-delay",
        "3",
        "--retry-all-errors",
        "-A",
        headers.get("User-Agent", "Mozilla/5.0"),
    ]
    resume = partial.exists()
    if resume:
        cmd.extend(["--continue-at", "-"])
    for key, value in headers.items():
        if key.lower() == "user-agent":
            continue
        cmd.extend(["-H", f"{key}: {value}"])
    cmd.extend(["-o", str(partial), url])
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        if exc.returncode != 33 or not partial.exists():
            raise
        log(f"Server refused resume, restarting: {output.name}", error=True)
        partial.unlink()
        continue_index = cmd.index("--continue-at")
        del cmd[continue_index : continue_index + 2]
        subprocess.run(cmd, check=True)
    partial.replace(output)


def run_urllib(url, output, headers):
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = partial_path(output)
    request = urllib.request.Request(url, headers=headers | {"User-Agent": headers.get("User-Agent", "runpod-ltx-template")})
    with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as handle:
        shutil.copyfileobj(response, handle, length=1024 * 1024 * 8)
    tmp.replace(output)


def download(entry, root, use_aria2, connections, splits, verify_hashes):
    entry = expand(entry)
    name = entry.get("name") or entry.get("path")
    url = entry["url"]
    output = root / entry["path"]
    expected_sha = (entry.get("sha256") or "").upper()
    min_bytes = int(entry.get("min_bytes") or 0)
    required = entry.get("required", True)
    headers = cleaned_headers(entry.get("headers"))
    method = str(entry.get("method") or "").lower()
    extract = entry.get("extract")
    sentinel = output.parent / ("." + output.name + ".extracted")
    missing_env = missing_required_env(entry.get("requires_env"))
    if missing_env:
        message = f"missing required env for {name}: {', '.join(missing_env)}"
        if required:
            raise RuntimeError(message)
        log(f"WARN optional model skipped: {message}", error=True)
        if output.exists() and min_bytes and output.stat().st_size < min_bytes:
            output.unlink()
        return

    if has_unresolved_template(url):
        message = f"unresolved template in url for {name}"
        if required:
            raise RuntimeError(message)
        log(f"WARN optional model skipped: {message}", error=True)
        if output.exists() and min_bytes and output.stat().st_size < min_bytes:
            output.unlink()
        return

    if extract and sentinel.exists():
        log(f"OK extracted: {name}")
        return

    migrate_legacy_aria_download(output)

    if output.exists() and output.stat().st_size > 0:
        if min_bytes and output.stat().st_size < min_bytes:
            log(f"Too small, redownloading: {name}", error=True)
            remove_verification_marker(output)
            output.unlink()
        elif expected_sha:
            if verify_sha256(output, expected_sha, name, verify_hashes):
                log(f"OK existing: {name}")
                return
            output.unlink()
        elif not extract:
            log(f"SKIP existing: {name}")
            return

    try:
        log(f"DOWNLOAD: {name}")
        download_started = time.monotonic()
        if method == "curl" and shutil.which("curl"):
            run_curl(url, output, headers)
        elif method in {"", "auto", "hf", "huggingface"} and parse_huggingface_url(url):
            try:
                run_hf_hub(url, output, headers)
            except Exception as exc:
                log(
                    f"WARN hf_xet failed for {name}; falling back to aria2c: {exc}",
                    error=True,
                )
                if use_aria2 and shutil.which("aria2c"):
                    final_url = resolve_download_url(url, headers)
                    run_aria2(final_url, output, connections, splits)
                else:
                    run_urllib(url, output, headers)
        elif use_aria2 and entry.get("use_aria2", True) and shutil.which("aria2c"):
            final_url = resolve_download_url(url, headers)
            run_aria2(final_url, output, connections, splits)
        else:
            run_urllib(url, output, headers)

        elapsed = max(time.monotonic() - download_started, 0.001)
        size = output.stat().st_size
        speed = size / elapsed / (1024 ** 2)
        log(
            f"DOWNLOADED: {name} ({size / (1024 ** 3):.2f} GiB in "
            f"{elapsed:.1f}s, average {speed:.1f} MiB/s)"
        )
        if min_bytes and output.stat().st_size < min_bytes:
            raise RuntimeError(f"downloaded file is too small for {output.name}: {output.stat().st_size} bytes")
        if expected_sha:
            if not verify_sha256(output, expected_sha, name, verify_hashes):
                raise RuntimeError(f"sha256 mismatch for {output.name}")
        if extract:
            names = extract_archive(output, output.parent, extract)
            if not names:
                raise RuntimeError(f"no matching files extracted from {output.name}")
            sentinel.write_text("\n".join(names))
            log(f"EXTRACTED ({name}): {', '.join(names)}")
    except Exception as exc:
        if output.exists():
            remove_verification_marker(output)
            output.unlink()
        if required:
            raise
        log(f"WARN optional model failed: {name}: {exc}", error=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--no-aria2", action="store_true")
    parser.add_argument("--connections", type=int, default=int(os.environ.get("ARIA2_CONNECTIONS", "8")))
    parser.add_argument("--splits", type=int, default=int(os.environ.get("ARIA2_SPLITS", "8")))
    parser.add_argument("--jobs", type=int, default=int(os.environ.get("DOWNLOAD_JOBS", "1")))
    parser.add_argument(
        "--verify-hashes",
        choices=("once", "always", "never"),
        default=os.environ.get("VERIFY_MODEL_HASHES", "once"),
    )
    args = parser.parse_args()

    root = pathlib.Path(args.root)
    manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))

    entries = []
    for entry in manifest.get("models", []):
        if not entry.get("enabled", True):
            log(f"SKIP disabled: {entry.get('name') or entry.get('path')}")
            continue
        entries.append(entry)

    jobs = max(1, args.jobs)
    if jobs == 1 or len(entries) <= 1:
        for entry in entries:
            download(
                entry,
                root,
                not args.no_aria2,
                args.connections,
                args.splits,
                args.verify_hashes,
            )
        return

    log(
        f"Downloading {len(entries)} models with up to {jobs} parallel jobs "
        f"(aria2c -x{args.connections} -s{args.splits} each)"
    )
    errors = []
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {
            executor.submit(
                download,
                entry,
                root,
                not args.no_aria2,
                args.connections,
                args.splits,
                args.verify_hashes,
            ): (entry.get("name") or entry.get("path"))
            for entry in entries
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
            except Exception as exc:
                errors.append(name)
                log(f"ERROR required model failed: {name}: {exc}", error=True)

    if errors:
        raise SystemExit(f"failed to download required models: {', '.join(errors)}")


if __name__ == "__main__":
    main()
