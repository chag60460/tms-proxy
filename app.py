import socket
import json
import os
import sys
from flask import Flask, request, jsonify

app = Flask(__name__)

TMS_HOST = os.environ.get("TMS_HOST", "tramway.proxy.rlwy.net")
TMS_PORT = int(os.environ.get("TMS_PORT", 17159))
TIMEOUT = int(os.environ.get("TMS_TIMEOUT", 10))

print(f"[CONFIG] TMS_HOST={TMS_HOST}, TMS_PORT={TMS_PORT}, TIMEOUT={TIMEOUT}", flush=True)

@app.route("/", methods=["POST"])
def proxy():
    body = request.get_json(force=True)
    command = body.get("command")
    print(f"[REQUEST] command={command!r}", flush=True)

    if not command:
        return jsonify({"error": "Missing 'command' field"}), 400

    try:
        print(f"[SOCKET] Connecting to {TMS_HOST}:{TMS_PORT}...", flush=True)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        sock.connect((TMS_HOST, TMS_PORT))
        print("[SOCKET] Connected", flush=True)

        payload = (command + "\n").encode("utf-8")
        print(f"[SOCKET] Sending {len(payload)} bytes: {payload!r}", flush=True)
        sock.sendall(payload)

        chunks = []
        while True:
            try:
                data = sock.recv(4096)
                print(f"[SOCKET] recv -> {len(data)} bytes: {data!r}", flush=True)
                if not data:
                    print("[SOCKET] Server closed connection", flush=True)
                    break
                chunks.append(data.decode("utf-8"))
            except socket.timeout:
                print("[SOCKET] recv timed out (no more data)", flush=True)
                break

        sock.close()
        raw_response = "".join(chunks)
        print(f"[RESPONSE] raw_response length={len(raw_response)}, content={raw_response[:500]!r}", flush=True)

        return jsonify({"raw_response": raw_response})

    except socket.timeout:
        print("[ERROR] Connection timed out", flush=True)
        return jsonify({"error": "TMS connection timed out"}), 504
    except ConnectionRefusedError:
        print("[ERROR] Connection refused", flush=True)
        return jsonify({"error": "TMS connection refused"}), 502
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}", flush=True)
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
