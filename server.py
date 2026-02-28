#!/usr/bin/env python3
"""
QC Report → Excel Converter - Backend Server
Run: python server.py
Then open: http://localhost:8080
"""

import http.server
import json
import urllib.request
import urllib.error
import os
import base64

PORT = 8080

class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {format % args}")

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        # Serve the HTML file
        if self.path in ("/", "/index.html"):
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                html_path = os.path.join(script_dir, "index.html")
                with open(html_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"index.html not found")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/gemini":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                payload = json.loads(body)

                api_key = payload.get("apiKey", "")
                image_b64 = payload.get("imageB64", "")
                mime_type = payload.get("mimeType", "image/jpeg")

                if not api_key:
                    self._error(400, "Missing apiKey")
                    return
                if not image_b64:
                    self._error(400, "Missing imageB64")
                    return

                prompt = (
                    "You are a data extraction assistant. Extract ALL product entries from this "
                    "Quality Control Pre-Dispatched Product Report image.\n\n"
                    "For EACH product row in the table extract:\n"
                    "- variety: product name + weight (e.g. \"Rolled Oats 800gm\")\n"
                    "- batch_code\n"
                    "- mfg_date\n"
                    "- expiry_date\n"
                    "- mrp (number only)\n"
                    "- defects_status (Yes or No)\n"
                    "- total_dispatch_ctn (number)\n"
                    "- party_name (if visible)\n\n"
                    "Return ONLY a raw JSON array. No markdown, no backticks, no extra text. Example:\n"
                    '[{"variety":"Rolled Oats 800gm","batch_code":"AK19K26R800D","mfg_date":"26-11-2025",'
                    '"expiry_date":"25-11-2026","mrp":"405","defects_status":"No","total_dispatch_ctn":"5",'
                    '"party_name":"Dautal Trading"}]\n\n'
                    'Use empty string "" for any field not visible.'
                )

                gemini_payload = {
                    "contents": [{
                        "parts": [
                            {"inline_data": {"mime_type": mime_type, "data": image_b64}},
                            {"text": prompt}
                        ]
                    }],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048}
                }

                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
                req = urllib.request.Request(
                    url,
                    data=json.dumps(gemini_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )

                try:
                    with urllib.request.urlopen(req, timeout=60) as response:
                        result = json.loads(response.read())
                        text = result["candidates"][0]["content"]["parts"][0]["text"]
                        clean = text.replace("```json", "").replace("```", "").strip()
                        rows = json.loads(clean)
                        if not isinstance(rows, list):
                            rows = [rows]

                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_cors_headers()
                        self.end_headers()
                        self.wfile.write(json.dumps({"rows": rows}).encode())

                except urllib.error.HTTPError as e:
                    err_body = e.read().decode()
                    try:
                        err_json = json.loads(err_body)
                        msg = err_json.get("error", {}).get("message", err_body)
                    except Exception:
                        msg = err_body
                    self._error(e.code, f"Gemini API error: {msg}")

                except urllib.error.URLError as e:
                    self._error(502, f"Could not reach Gemini API: {e.reason}")

                except (json.JSONDecodeError, KeyError, IndexError) as e:
                    self._error(500, f"Failed to parse Gemini response: {e}")

            except Exception as e:
                self._error(500, str(e))
        else:
            self.send_response(404)
            self.end_headers()

    def _error(self, code, message):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode())


if __name__ == "__main__":
    print("=" * 55)
    print("  QC Report → Excel Converter")
    print(f"  Running at: http://localhost:{PORT}")
    print("  Press Ctrl+C to stop")
    print("=" * 55)
    server = http.server.HTTPServer(("localhost", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")