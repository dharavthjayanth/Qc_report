import os
import json
import urllib.request
import urllib.error
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder="static")

GEMINI_MODEL = "gemini-2.5-flash-preview-04-17"

PROMPT = (
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


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/status")
def status():
    key_configured = bool(os.environ.get("GEMINI_API_KEY"))
    return jsonify({"keyConfigured": key_configured})


@app.route("/api/gemini", methods=["POST"])
def gemini_proxy():
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({"error": "Invalid JSON body"}), 400

        # API key: prefer env variable, fallback to request body
        api_key = os.environ.get("GEMINI_API_KEY") or payload.get("apiKey", "")
        image_b64 = payload.get("imageB64", "")
        mime_type = payload.get("mimeType", "image/jpeg")

        if not api_key:
            return jsonify({"error": "Gemini API key not configured. Set GEMINI_API_KEY environment variable on Render."}), 400
        if not image_b64:
            return jsonify({"error": "No image data received"}), 400

        gemini_payload = {
            "contents": [{
                "parts": [
                    {"inline_data": {"mime_type": mime_type, "data": image_b64}},
                    {"text": PROMPT}
                ]
            }],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096}
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(gemini_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read())
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            clean = text.replace("```json", "").replace("```", "").strip()
            rows = json.loads(clean)
            if not isinstance(rows, list):
                rows = [rows]
            return jsonify({"rows": rows})

    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        try:
            msg = json.loads(err_body).get("error", {}).get("message", err_body)
        except Exception:
            msg = err_body
        return jsonify({"error": f"Gemini API error: {msg}"}), e.code

    except urllib.error.URLError as e:
        return jsonify({"error": f"Could not reach Gemini API: {e.reason}"}), 502

    except (json.JSONDecodeError, KeyError, IndexError) as e:
        return jsonify({"error": f"Failed to parse Gemini response: {e}"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)