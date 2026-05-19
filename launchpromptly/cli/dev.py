"""
launchpromptly dev — Python equivalent of `npx launchpromptly dev`.

Usage:
    python -m launchpromptly dev
    launchpromptly dev --port 7080 --tag latest

Starts a local scanner Docker container and prints the LP_SCANNER_URL.
Falls back gracefully to regex-only mode if Docker is unavailable.

License: BSL-1.1 (converts to Apache-2.0 after 4 years)
"""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error

SCANNER_IMAGE = "ghcr.io/launchpromptly/scanner"
CONTAINER_NAME = "lp-scanner-dev"
DEFAULT_PORT = 7080
HEALTH_POLL_SECS = 0.5
HEALTH_TIMEOUT_SECS = 60


def is_docker_available() -> bool:
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def is_container_running(name: str) -> bool:
    try:
        out = subprocess.check_output(
            ["docker", "inspect", "--format", "{{.State.Running}}", name],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        return out == "true"
    except subprocess.CalledProcessError:
        return False


def wait_for_health(url: str) -> bool:
    deadline = time.monotonic() + HEALTH_TIMEOUT_SECS
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(HEALTH_POLL_SECS)
    return False


def stop_container() -> None:
    try:
        subprocess.run(["docker", "stop", CONTAINER_NAME], capture_output=True)
        subprocess.run(["docker", "rm", CONTAINER_NAME], capture_output=True)
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start a local LaunchPromptly scanner")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--tag", default="latest")
    args = parser.parse_args(argv)

    port = args.port
    tag = args.tag
    image_ref = f"{SCANNER_IMAGE}:{tag}"
    scanner_url = f"http://localhost:{port}"

    print("LaunchPromptly Dev Scanner\n")

    if not is_docker_available():
        print("WARNING: Docker not found or not running.")
        print("  Falling back to regex-only mode (no ML detection).")
        print("  Start Docker and re-run `launchpromptly dev` for full ML capabilities.\n")
        _print_fallback()
        return 0

    if is_container_running(CONTAINER_NAME):
        print(f"Stopping existing {CONTAINER_NAME} container...")
        stop_container()

    print(f"Pulling {image_ref}...")
    try:
        subprocess.run(["docker", "pull", image_ref], check=True)
    except subprocess.CalledProcessError:
        print(f"WARNING: Could not pull {image_ref}. Using cached image if available.")

    print(f"\nStarting scanner on port {port}...")
    docker_args = [
        "docker", "run", "--rm", "-d",
        "--name", CONTAINER_NAME,
        "-p", f"{port}:7080",
        "-e", "LP_AUTH_REQUIRED=false",
        "-e", "LOG_LEVEL=info",
        "--memory", "4g",
        image_ref,
    ]

    result = subprocess.run(docker_args, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: docker run failed:\n{result.stderr}", file=sys.stderr)
        _print_fallback()
        return 1

    container_id = result.stdout.strip()[:12]
    print(f"  Container: {container_id}")
    print("  Waiting for scanner to be healthy...")

    healthy = wait_for_health(scanner_url)
    if not healthy:
        print("\nERROR: Scanner did not become healthy within 60 s.")
        print("  Check logs: docker logs lp-scanner-dev")
        _print_fallback()
        return 1

    print(f"\nScanner is ready at {scanner_url}\n")
    print("Set this in your shell to use the scanner:")
    print(f"\n  export LP_SCANNER_URL={scanner_url}\n")
    print("Or in your .env:")
    print(f"\n  LP_SCANNER_URL={scanner_url}\n")
    print("Press Ctrl+C to stop.\n")

    # Stream logs
    log_proc = subprocess.Popen(
        ["docker", "logs", "-f", CONTAINER_NAME],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    def _shutdown(sig, frame):
        print("\n\nStopping scanner...")
        log_proc.terminate()
        stop_container()
        print("Scanner stopped. Goodbye!")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log_proc.wait()
    return 0


def _print_fallback() -> None:
    print("The SDK will use regex-only detection (no ML scores).")
    print("No LP_SCANNER_URL needs to be set in fallback mode.")


if __name__ == "__main__":
    sys.exit(main())
