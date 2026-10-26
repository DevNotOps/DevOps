"""
Website Up/Down Checker with latency.

Run:
    pip install flask requests
    python app.py
Then open http://127.0.0.1:5000
"""
import ipaddress
import socket
import time
from urllib.parse import urlparse

import requests
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

TIMEOUT = 10  # seconds


def normalize(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def is_private_host(hostname: str) -> bool:
    """Block localhost / private IPs so the server can't be abused to probe internal networks."""
    try:
        for info in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
    except socket.gaierror:
        return False  # DNS failure is reported later as "down"
    return False


def check_site(url: str) -> dict:
    url = normalize(url)
    parsed = urlparse(url)
    if not parsed.hostname:
        return {"url": url, "status": "error", "error": "Invalid URL"}
    if is_private_host(parsed.hostname):
        return {"url": url, "status": "error", "error": "Private/local addresses are not allowed"}

    start = time.perf_counter()
    try:
        r = requests.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,  # don't download the body, we only care about the response
            headers={"User-Agent": "UptimeChecker/1.0"},
        )
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        code = r.status_code
        final_url = r.url
        r.close()
        return {
            "url": url,
            "final_url": final_url,
            "status": "up" if code < 400 else "down",
            "status_code": code,
            "latency_ms": latency_ms,
        }
    except requests.exceptions.Timeout:
        err = f"Timed out after {TIMEOUT}s"
    except requests.exceptions.SSLError:
        err = "SSL certificate error"
    except requests.exceptions.ConnectionError:
        err = "Connection failed (DNS or server unreachable)"
    except requests.exceptions.RequestException as e:
        err = str(e)
    return {"url": url, "status": "down", "error": err}


@app.get("/api/check")
def api_check():
    url = request.args.get("url", "")
    if not url:
        return jsonify({"status": "error", "error": "Missing ?url= parameter"}), 400
    return jsonify(check_site(url))


PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Website Up/Down Checker</title>
<style>
  body { font-family: system-ui, sans-serif; background:#0f172a; color:#e2e8f0;
         display:flex; justify-content:center; padding:48px 16px; margin:0; }
  .card { width:100%; max-width:520px; }
  h1 { font-size:1.5rem; margin-bottom:20px; }
  .row { display:flex; gap:8px; }
  input { flex:1; padding:12px; border-radius:8px; border:1px solid #334155;
          background:#1e293b; color:inherit; font-size:1rem; }
  button { padding:12px 20px; border:0; border-radius:8px; background:#3b82f6;
           color:#fff; font-size:1rem; cursor:pointer; }
  button:disabled { opacity:.6; cursor:wait; }
  #result { margin-top:24px; padding:20px; border-radius:12px; background:#1e293b; display:none; }
  .badge { display:inline-block; padding:4px 14px; border-radius:999px; font-weight:700; }
  .up { background:#16a34a; } .down { background:#dc2626; } .error { background:#d97706; }
  dl { display:grid; grid-template-columns:auto 1fr; gap:6px 16px; margin:16px 0 0; }
  dt { color:#94a3b8; } dd { margin:0; word-break:break-all; }
</style>
</head>
<body>
<div class="card">
  <h1>Website Up/Down Checker</h1>
  <div class="row">
    <input id="url" placeholder="example.com" autofocus>
    <button id="btn">Check</button>
  </div>
  <div id="result"></div>
</div>
<script>
const $ = id => document.getElementById(id);
async function check() {
  const url = $("url").value.trim();
  if (!url) return;
  $("btn").disabled = true; $("btn").textContent = "Checking...";
  try {
    const res = await fetch("/api/check?url=" + encodeURIComponent(url));
    const d = await res.json();
    let html = `<span class="badge ${d.status}">${d.status.toUpperCase()}</span><dl>`;
    if (d.status_code) html += `<dt>HTTP status</dt><dd>${d.status_code}</dd>`;
    if (d.latency_ms !== undefined) html += `<dt>Latency</dt><dd>${d.latency_ms} ms</dd>`;
    if (d.final_url) html += `<dt>Final URL</dt><dd>${d.final_url}</dd>`;
    if (d.error) html += `<dt>Error</dt><dd>${d.error}</dd>`;
    $("result").innerHTML = html + "</dl>";
  } catch (e) {
    $("result").innerHTML = `<span class="badge error">ERROR</span><dl><dt>Error</dt><dd>${e}</dd></dl>`;
  }
  $("result").style.display = "block";
  $("btn").disabled = false; $("btn").textContent = "Check";
}
$("btn").onclick = check;
$("url").addEventListener("keydown", e => e.key === "Enter" && check());
</script>
</body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(PAGE)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
