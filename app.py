import socket
import json
import os
from flask import Flask, request, jsonify

app = Flask(__name__)

TMS_HOST = os.environ.get("TMS_HOST", "tramway.proxy.rlwy.net")
TMS_PORT = int(os.environ.get("TMS_PORT", 17159))
TIMEOUT = int(os.environ.get("TMS_TIMEOUT", 10))

@app.route("/", methods=["POST"])
def proxy():
    body = request.get_json(force=True)
    command = body.get("command")

    if not command:
        return jsonify({"error": "Missing 'command' field"}), 400

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        sock.connect((TMS_HOST, TMS_PORT))
        sock.sendall((command + "\n").encode("utf-8"))

        chunks = []
        while True:
            try:
                data = sock.recv(4096)
                if not data:
                    break
                chunks.append(data.decode("utf-8"))
            except socket.timeout:
                break

        sock.close()
        raw_response = "".join(chunks)

        return jsonify({"raw_response": raw_response})

    except socket.timeout:
        return jsonify({"error": "TMS connection timed out"}), 504
    except ConnectionRefusedError:
        return jsonify({"error": "TMS connection refused"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
