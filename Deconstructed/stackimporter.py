"""
stackimporter.py — importable OpenStack Swift uploader.

Main entry point:
    upload_directory(source_dir, container, env, log=print)
        -> (success_count, total_count)
"""

import subprocess
from pathlib import Path

MAX_RETRIES = 5
TIMEOUT = 14400  # 4 hours — large file safety net
SEGMENT_THRESHOLD = 5 * 1024 * 1024 * 1024      # 5 GB
SEGMENT_SIZE      = 4 * 1024 * 1024 * 1024 + 500 * 1024 * 1024  # 4.5 GB


def _swift(*args, env, timeout=30, check=True):
    return subprocess.run(
        ["python3", "-m", "swiftclient.shell"] + list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
        env=env,
    )


def check_auth(env: dict, log=print) -> tuple[bool, str]:
    """Verify credentials by requesting an auth token. Returns (ok, message)."""
    log(f"Auth URL : {env.get('OS_AUTH_URL', '(not set)')}")
    log(f"Project  : {env.get('OS_PROJECT_NAME', '(not set)')} / {env.get('OS_USER_DOMAIN_NAME', '(not set)')}")
    log(f"Username : {env.get('OS_USERNAME', '(not set)')}")
    log("Requesting token…")
    try:
        result = _swift("auth", env=env, timeout=30)
        if "OS_AUTH_TOKEN=" in result.stdout:
            log("Token received.")
            return True, "Authenticated successfully."
        log("No token in response.")
        return False, "Authentication failed — no token received."
    except subprocess.TimeoutExpired:
        return False, "Auth request timed out — check network/URL."
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or "").strip().splitlines()
        msg = detail[-1] if detail else "Unknown error"
        log(f"Error: {msg}")
        return False, f"Auth error: {msg}"


def _ensure_container(container: str, env: dict, log):
    try:
        _swift("stat", container, env=env)
        log(f"Container '{container}' exists.")
    except subprocess.CalledProcessError:
        log(f"Container '{container}' not found — creating…")
        try:
            _swift("post", container, env=env)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Could not create container '{container}': {e.stderr.strip()}")


def _upload_file(
    file_path: Path,
    source_root: Path,
    container: str,
    env: dict,
    log,
    attempt: int = 1,
) -> bool:
    # Preserve the source folder name in the object path:
    #   source_root = /foo/bar/MyData  →  object_name = MyData/subdir/file.txt
    object_name = str(file_path.relative_to(source_root.parent))
    size_mb = file_path.stat().st_size / (1024 * 1024)

    cmd = ["upload"]
    if file_path.stat().st_size > SEGMENT_THRESHOLD:
        segment_container = f"{container}_segments"
        cmd += [
            "--segment-size", str(SEGMENT_SIZE),
            "--segment-container", segment_container,
        ]
    cmd += [container, str(file_path), "--object-name", object_name]

    try:
        _swift(*cmd, env=env, timeout=TIMEOUT)
        log(f"✓  {object_name}  ({size_mb:.1f} MB)")
        return True
    except subprocess.TimeoutExpired:
        log(f"⏰ Timeout: {object_name} (attempt {attempt})")
    except subprocess.CalledProcessError as e:
        err = (e.stderr or "").strip().splitlines()
        log(f"✗  {object_name} — {err[-1] if err else 'unknown error'} (attempt {attempt})")

    if attempt < MAX_RETRIES:
        log(f"↻  Retrying {object_name} ({attempt + 1}/{MAX_RETRIES})…")
        return _upload_file(file_path, source_root, container, env, log, attempt + 1)

    log(f"✗  Giving up on {object_name} after {MAX_RETRIES} attempts.")
    return False


def upload_directory(
    source_dir,
    container: str,
    env: dict,
    log=print,
) -> tuple[int, int]:
    """
    Upload all files under source_dir to container, preserving folder structure.

    Args:
        source_dir: Path (or str) to the local directory to upload.
        container:  Swift container name.
        env:        dict of OS_* environment variables (including OS_PASSWORD).
        log:        callable(str) for progress output.

    Returns:
        (success_count, total_count)
    """
    source_dir = Path(source_dir)

    _ensure_container(container, env, log)

    files = sorted(f for f in source_dir.rglob("*") if f.is_file())
    if not files:
        log("No files found in the selected directory.")
        return 0, 0

    log(f"Uploading {len(files)} file(s) from '{source_dir.name}' → container '{container}'")

    success = 0
    for f in files:
        if _upload_file(f, source_dir, container, env, log):
            success += 1

    return success, len(files)
