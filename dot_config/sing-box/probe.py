"""Unprivileged sb diagnostics. Each deep probe owns a temporary SOCKS listener."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import copy
import json
import os
from pathlib import Path
import signal
import socket
from statistics import median
import struct
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import quote

HTTPS_TARGETS = ("https://www.gstatic.com/generate_204", "https://cp.cloudflare.com/generate_204")
STUN_TARGETS = (("stun.l.google.com", 19302), ("stun.cloudflare.com", 3478))
STOP = threading.Event()


def curl(*args, timeout=35):
    result = subprocess.run(
        ["curl", "--silent", "--show-error", "--fail-with-body", "--noproxy", "*",
         "--max-time", str(timeout), *args], capture_output=True, text=True, timeout=timeout + 2,
    )
    if result.returncode:
        raise RuntimeError(f"curl exit {result.returncode}: {result.stderr.strip()[:200]}")
    return result.stdout


def quick(tag):
    secret = os.environ.get("SB_API_SECRET", "admin")
    headers = ["--header", f"Authorization: Bearer {secret}"] if secret else []
    data = json.loads(curl(*headers, "--get", "--data-urlencode", f"url={HTTPS_TARGETS[0]}",
                           "--data-urlencode", "timeout=30000",
                           f"http://127.0.0.1:9091/proxies/{quote(tag, safe='')}/delay"))
    return {"status": "HTTPS probe passed", "latency_ms": data["delay"]}


def isolated_config(config, tag, port):
    result = copy.deepcopy(config)
    # Keep DNS, endpoints and detours, but never start production listeners, cache,
    # controllers, route downloads or background URL tests in a diagnostic instance.
    result.pop("experimental", None)
    result.pop("services", None)
    result["log"] = {"level": "error"}
    result["inbounds"] = [{"type": "socks", "listen": "127.0.0.1", "listen_port": port}]
    # DNS policies referencing route rule sets are unsupported; retain their referenced
    # sets here if needed, at the cost of downloads during diagnostic startup.
    result["route"] = {key: value for key, value in result.get("route", {}).items()
                       if key not in ("rules", "rule_set", "final")}
    result["route"]["final"] = tag
    for outbound in result.get("outbounds", []):
        if outbound.get("type") == "urltest":
            outbound["type"] = "selector"
            for key in ("url", "interval", "tolerance", "idle_timeout"):
                outbound.pop(key, None)
    return result


@contextmanager
def instance(config, tag):
    # Ephemeral-port reservation has a bind race; retry allocation if contention matters.
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="sb-probe-") as directory:
        path = Path(directory) / "config.json"
        path.write_text(json.dumps(isolated_config(config, tag, port)))
        path.chmod(0o600)
        with (Path(directory) / "error.log").open("w+") as log:
            process = subprocess.Popen(["sing-box", "run", "-c", str(path)], cwd=directory,
                                       stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 8
                while True:
                    if STOP.is_set():
                        raise RuntimeError("probe cancelled")
                    if process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError("isolated sing-box failed: " + log.read()[-500:])
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                            break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError("isolated sing-box startup timed out")
                        time.sleep(0.05)
                yield port
            finally:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def transfer(port, url, *, upload=None):
    args = ["--proxy", f"socks5h://127.0.0.1:{port}", "--noproxy", "", "--output", os.devnull,
            "--write-out", "%{json}"]
    if upload is not None:
        args.extend(["--data-binary", "@" + str(upload)])
    return json.loads(curl(*args, url, timeout=15))


def stability(port, count):
    attempts = []
    # One curl process per sample deliberately forces a fresh connection, no retries.
    for index in range(count):
        if STOP.is_set():
            raise RuntimeError("probe cancelled")
        target = HTTPS_TARGETS[index % len(HTTPS_TARGETS)]
        try:
            result = transfer(port, target)
            attempts.append({"target": target, "latency_ms": round(result["time_total"] * 1000, 1)})
        except (RuntimeError, subprocess.TimeoutExpired, ValueError) as error:
            attempts.append({"target": target, "error": str(error)})
        if index + 1 < count and STOP.wait(1):
            raise RuntimeError("probe cancelled")
    passed = [item["latency_ms"] for item in attempts if "latency_ms" in item]
    return {"status": "passed" if passed and len(passed) == len(attempts) else "unstable" if passed else "failed",
            "successes": len(passed), "attempts": len(attempts),
            "min_latency_ms": min(passed, default=None),
            "median_latency_ms": round(median(passed), 1) if passed else None,
            "max_latency_ms": max(passed, default=None), "samples": attempts}


def bandwidth(port, size):
    results = {}
    with tempfile.TemporaryDirectory(prefix="sb-bandwidth-") as directory:
        payload = Path(directory) / "upload"
        with payload.open("wb") as output:
            output.truncate(size)
        for direction, url, upload in (
            ("download", f"https://speed.cloudflare.com/__down?bytes={size}", None),
            ("upload", "https://speed.cloudflare.com/__up", payload),
        ):
            if STOP.is_set():
                raise RuntimeError("probe cancelled")
            try:
                data = transfer(port, url, upload=upload)
                transferred = data["size_download" if direction == "download" else "size_upload"]
                if transferred != size:
                    raise RuntimeError(f"incomplete transfer: {transferred}/{size} bytes")
                results[direction] = {"status": "passed", "bytes": transferred,
                                      "mbps": round(transferred * 8 / max(data["time_total"], 0.000001) / 1e6, 2)}
            except (RuntimeError, subprocess.TimeoutExpired, ValueError) as error:
                results[direction] = {"status": "failed", "error": str(error)}
    results["status"] = "passed" if all(item["status"] == "passed" for item in results.values()) else "failed"
    return results


def receive(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise RuntimeError("SOCKS connection closed")
        data += chunk
    return data


def socks_address(sock):
    kind = receive(sock, 1)[0]
    if kind == 1:
        host = socket.inet_ntop(socket.AF_INET, receive(sock, 4))
    elif kind == 4:
        host = socket.inet_ntop(socket.AF_INET6, receive(sock, 16))
    elif kind == 3:
        host = receive(sock, receive(sock, 1)[0]).decode()
    else:
        raise RuntimeError("invalid SOCKS address")
    return host, struct.unpack("!H", receive(sock, 2))[0]


def stun(port, host, destination_port):
    with socket.create_connection(("127.0.0.1", port), timeout=4) as control:
        control.settimeout(4)
        control.sendall(b"\x05\x01\x00")
        if receive(control, 2) != b"\x05\x00":
            raise RuntimeError("SOCKS authentication rejected")
        control.sendall(b"\x05\x03\x00\x01\x00\x00\x00\x00\x00\x00")
        if receive(control, 3) != b"\x05\x00\x00":
            raise RuntimeError("SOCKS UDP ASSOCIATE rejected")
        relay_host, relay_port = socks_address(control)
        if relay_host == "0.0.0.0":
            relay_host = "127.0.0.1"
        transaction = os.urandom(12)
        request = struct.pack("!HHI", 1, 0, 0x2112A442) + transaction
        name = host.encode("ascii")
        packet = b"\x00\x00\x00\x03" + bytes([len(name)]) + name + struct.pack("!H", destination_port) + request
        started = time.monotonic()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.settimeout(4)
            udp.connect((relay_host, relay_port))
            udp.send(packet)
            response = udp.recv(4096)
        if len(response) < 4 or response[:3] != b"\x00\x00\x00":
            raise RuntimeError("invalid or fragmented SOCKS UDP reply")
        kind = response[3]
        offset = {1: 10, 4: 22}.get(kind)
        if kind == 3:
            if len(response) < 5:
                raise RuntimeError("truncated UDP reply address")
            offset = 7 + response[4]
        if offset is None:
            raise RuntimeError("invalid UDP reply address")
        message = response[offset:]
        if len(message) < 20 or message[:2] != b"\x01\x01" or message[4:8] != b"\x21\x12\xa4\x42" or message[8:20] != transaction:
            raise RuntimeError("invalid STUN binding response")
        length = struct.unpack("!H", message[2:4])[0]
        if length % 4 or len(message) != 20 + length:
            raise RuntimeError("truncated STUN response")
        offset = 20
        mapped = False
        while offset < len(message):
            if offset + 4 > len(message):
                raise RuntimeError("truncated STUN attribute")
            kind, size = struct.unpack("!HH", message[offset:offset + 4])
            offset += 4
            if offset + size > len(message):
                raise RuntimeError("truncated STUN attribute")
            if kind in (1, 0x0020) and size in (8, 20):
                mapped = True
            offset += (size + 3) & ~3
        if not mapped:
            raise RuntimeError("STUN response lacks a mapped address")
        return round((time.monotonic() - started) * 1000, 1)


def udp_probe(port):
    samples = []
    for host, destination_port in STUN_TARGETS:
        for _ in range(3):
            if STOP.is_set():
                raise RuntimeError("probe cancelled")
            try:
                samples.append({"target": f"{host}:{destination_port}", "latency_ms": stun(port, host, destination_port)})
            except (OSError, RuntimeError) as error:
                samples.append({"target": f"{host}:{destination_port}", "error": str(error)})
    passed = [item["latency_ms"] for item in samples if "latency_ms" in item]
    return {"status": "passed" if len(passed) == len(samples) else "degraded" if passed else "failed",
            "received": len(passed), "sent": len(samples),
            "loss_percent": round(100 * (1 - len(passed) / len(samples)), 1),
            "rtt_spread_ms": round(max(passed) - min(passed), 1) if passed else None,
            "samples": samples}


def probe(tag, config, args):
    row = {"outbound": tag, "mode": args.mode}
    try:
        if STOP.is_set():
            raise RuntimeError("probe cancelled")
        if args.mode == "quick":
            row.update(quick(tag))
        else:
            with instance(config, tag) as port:
                for mode, action in (("udp", lambda: udp_probe(port)),
                                     ("stability", lambda: stability(port, args.attempts)),
                                     ("bandwidth", lambda: bandwidth(port, args.bytes))):
                    if STOP.is_set():
                        raise RuntimeError("probe cancelled")
                    if args.mode in (mode, "full"):
                        row[mode] = action()
            row["status"] = "passed" if all(value["status"] == "passed" for value in row.values() if isinstance(value, dict)) else "failed"
    except Exception as error:
        row.update(status="failed or timed out", latency_ms=None, error=str(error))
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("quick", "udp", "bandwidth", "stability", "full"), default="quick")
    parser.add_argument("--attempts", type=int, default=20)
    parser.add_argument("--bytes", type=int, default=5_000_000)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    if min(args.attempts, args.bytes, args.threads) < 1:
        parser.error("attempts, bytes and threads must be positive")
    payload = json.load(sys.stdin)
    tags, config = payload["tags"], payload.get("config")
    # Workers unwind their instances after the in-flight bounded request on Ctrl-C.
    def interrupt(*_):
        STOP.set()
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    pool = ThreadPoolExecutor(max_workers=args.threads)
    try:
        futures = [pool.submit(probe, tag, config, args) for tag in tags]
        for future in as_completed(futures):
            print(json.dumps(future.result()), flush=True)
    except (KeyboardInterrupt, BrokenPipeError):
        STOP.set()
        return 130
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
