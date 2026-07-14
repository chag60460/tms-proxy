import socket
import os
import time
from flask import Flask, request, jsonify

app = Flask(__name__)

TMS_HOST = os.environ.get("TMS_HOST", "tramway.proxy.rlwy.net")
TMS_PORT = int(os.environ.get("TMS_PORT", 17159))
TIMEOUT = int(os.environ.get("TMS_TIMEOUT", 30))
MAX_RETRIES = int(os.environ.get("TMS_MAX_RETRIES", 3))
RETRY_DELAY = float(os.environ.get("TMS_RETRY_DELAY", 2))

print(f"[CONFIG] TMS_HOST={TMS_HOST}, TMS_PORT={TMS_PORT}, TIMEOUT={TIMEOUT}, "
      f"MAX_RETRIES={MAX_RETRIES}, RETRY_DELAY={RETRY_DELAY}", flush=True)


def query_tms(command: str) -> str:
    """Send a command to TMS and read until END\\r\\n."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(TIMEOUT)

    try:
        sock.connect((TMS_HOST, TMS_PORT))
        sock.sendall((command + "\r\n").encode("ascii"))

        buffer = b""
        while True:
            try:
                data = sock.recv(4096)
                if not data:
                    break
                buffer += data
                if buffer.endswith(b"END\r\n"):
                    break
            except socket.timeout:
                break

        return buffer.decode("ascii")

    finally:
        sock.close()


def is_valid_response(raw: str) -> bool:
    """Check that the response looks well-formed."""
    if not raw or not raw.strip():
        return False
    if not raw.strip().endswith("END"):
        return False
    # Check for obvious corruption: null bytes, non-ASCII garbage
    try:
        raw.encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


@app.route("/", methods=["POST"])
def proxy():
    body = request.get_json(force=True)
    command = body.get("command")
    print(f"[REQUEST] command={command!r}", flush=True)

    if not command:
        return jsonify({"error": "Missing 'command' field"}), 400

    last_error = None
    last_raw = None

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"[ATTEMPT {attempt}/{MAX_RETRIES}] Querying TMS...", flush=True)

        try:
            raw = query_tms(command)
            print(f"[ATTEMPT {attempt}] Got {len(raw)} bytes, "
                  f"preview={raw[:200]!r}", flush=True)

            if is_valid_response(raw):
                print(f"[SUCCESS] Valid response on attempt {attempt}", flush=True)
                return jsonify({"raw_response": raw})

            # Got a response but it's malformed — retry
            print(f"[ATTEMPT {attempt}] Malformed response, will retry", flush=True)
            last_raw = raw
            last_error = "Malformed response from TMS"

        except socket.timeout:
            print(f"[ATTEMPT {attempt}] Timed out", flush=True)
            last_error = "TMS connection timed out"

        except ConnectionRefusedError:
            print(f"[ATTEMPT {attempt}] Connection refused", flush=True)
            last_error = "TMS connection refused"

        except Exception as e:
            print(f"[ATTEMPT {attempt}] {type(e).__name__}: {e}", flush=True)
            last_error = str(e)

        # Wait before retrying (skip delay after last attempt)
        if attempt < MAX_RETRIES:
            print(f"[RETRY] Waiting {RETRY_DELAY}s before next attempt...", flush=True)
            time.sleep(RETRY_DELAY)

    # All retries exhausted
    print(f"[FAILED] All {MAX_RETRIES} attempts failed. "
          f"Last error: {last_error}", flush=True)

    return jsonify({
        "error": f"TMS unavailable after {MAX_RETRIES} attempts: {last_error}",
        "raw_response": last_raw  # include partial data if we got any
    }), 504


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
