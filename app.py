
import os
import sys
import json
import shutil
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, make_response
from pathlib import Path

# ───── Paths ───────────────────────────────────────────
# A frozen Windows application lives in a read-only install directory. Its
# templates/seed dorks are bundled, while user results live in LocalAppData.
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
IS_FROZEN = bool(getattr(sys, "frozen", False))
DATA = (Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "DeepRake") if IS_FROZEN else ROOT / "data"
app = Flask(__name__, template_folder=str(ROOT / "templates"))
DORKS_DIR = DATA / "dorks"
OUT = DATA / "out"
DORKS_DIR.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

SEED_DORKS = DORKS_DIR / "DEEP-RAKE_Dorks_GodMind.txt"
PACKAGED_SEED = ROOT / "data" / "dorks" / "DEEP-RAKE_Dorks_GodMind.txt"
if not SEED_DORKS.exists() and PACKAGED_SEED.exists() and PACKAGED_SEED != SEED_DORKS:
    shutil.copy2(PACKAGED_SEED, SEED_DORKS)
RESULTS_JSONL = OUT / "search_results.jsonl"
NEXT_QUERIES = OUT / "next_queries.txt"
PIVOT_STATE = OUT / "pivot_state.jsonl"


# ───── CORS Headers for Bookmarklet ───────────────────
@app.after_request
def add_cors_headers(resp):
    if request.path.startswith("/api/"):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp


@app.route("/api/<path:_any>", methods=["OPTIONS"])
def api_preflight(_any):
    return ("", 204)


# ───── UI Pages ────────────────────────────────────────
@app.route("/")
def home():
    return redirect("/dorks")


@app.route("/dorks")
def dorks_page():
    return render_template("dorks.html")


# ───── API: Load Seed Dorks ────────────────────────────
@app.route("/api/dorks/seed", methods=["GET"])
def api_seed_dorks():
    text = SEED_DORKS.read_text(encoding="utf-8") if SEED_DORKS.exists() else ""
    return jsonify({"seed": text})


# ───── API: Receive and Save Search Results ────────────
@app.route("/api/results", methods=["POST"])
def api_results():
    if request.is_json:
        items = request.get_json(silent=True) or []
        if isinstance(items, dict):
            items = [items]
        with open(RESULTS_JSONL, "a", encoding="utf-8") as f:
            for obj in items:
                rec = {
                    "title": obj.get("title", ""),
                    "snippet": obj.get("snippet", ""),
                    "url": obj.get("url", ""),
                    "site": obj.get("site", ""),
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return jsonify({"ok": True, "appended": len(items)})

    raw = (request.form.get("text") or "").strip()
    if not raw:
        return jsonify({"ok": False, "error": "No content"}), 400

    with open(RESULTS_JSONL, "a", encoding="utf-8") as f:
        f.write(raw)
        f.write("\n" if not raw.endswith("\n") else "")
    return jsonify({"ok": True, "mode": "jsonl-raw"})


# ───── API: Run Pivot Script ───────────────────────────
@app.route("/api/pivot", methods=["POST"])
def api_pivot():
    # The original launched `python pivot_engine.py`. In a PyInstaller build,
    # sys.executable is DeepRake.exe, so invoke the same engine directly.
    from modules.pivot_engine import PivotEngine, load_results_jsonl
    try:
        max_new = int(request.args.get("max", "150"))
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid max value"}), 400
    results = load_results_jsonl(str(RESULTS_JSONL)) if RESULTS_JSONL.exists() else []
    engine = PivotEngine(state_path=str(PIVOT_STATE))
    queries = engine.propose_queries(
        results, max_new=max_new, enable_lang_pivots=request.args.get("no_lang") != "1"
    )
    PivotEngine.write_queries(queries, str(NEXT_QUERIES))
    txt = NEXT_QUERIES.read_text(encoding="utf-8") if NEXT_QUERIES.exists() else ""
    return jsonify({"ok": True, "next_queries": txt})


# ───── API: Harvest Feed (last 100 URLs) ───────────────
@app.route("/api/latest", methods=["GET"])
def api_latest():
    urls = []
    try:
        if RESULTS_JSONL.exists():
            with open(RESULTS_JSONL, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        url = obj.get("url")
                        if url:
                            urls.append({"url": url})
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify(urls[-100:])  # last 100 only


# ───── API: Download Next Queries ──────────────────────
@app.route("/api/next/download", methods=["GET"])
def api_next_download():
    if NEXT_QUERIES.exists():
        return send_file(NEXT_QUERIES, as_attachment=True, download_name="next_queries.txt")
    return jsonify({"ok": False, "error": "next_queries.txt not found"}), 404


# ───── API: Download Harvested URLs Only ───────────────
@app.route("/api/harvest/download")
def download_harvest():
    path = RESULTS_JSONL
    if not path.exists():
        return "No harvest data found.", 404

    urls = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
                url = item.get("url", "").strip()
                if url:
                    urls.append(url)
            except:
                continue

    out_path = OUT / "harvest_urls.txt"
    out_path.write_text("\n".join(urls), encoding="utf-8")
    return send_file(out_path, as_attachment=True)


# ───── API: Clear Dig Portal Files ─────────────────────
@app.route("/api/clear", methods=["POST"])
def clear_files():
    try:
        # Clear .jsonl files
        PIVOT_STATE.write_text("", encoding="utf-8")
        RESULTS_JSONL.write_text("", encoding="utf-8")

        # Clear .txt files
        (OUT / "harvest_urls.txt").write_text("", encoding="utf-8")
        NEXT_QUERIES.write_text("", encoding="utf-8")

        return jsonify({"ok": True})
    except Exception as e:
        print(f"Error clearing files: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500




# ───── Main Entry ──────────────────────────────────────
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
