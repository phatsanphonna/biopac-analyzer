import os
import sys
import tempfile
import webbrowser
from threading import Timer
import pandas as pd
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# Import the analysis wrapper
from analysis_wrapper import analyze_biopac_file, analyze_biopac_path

app = Flask(__name__, static_folder="frontend/dist", static_url_path="/_static")
CORS(app)  # Enable CORS for development mode

# =========================
# BACKEND API ENDPOINTS
# =========================

@app.route("/api/columns", methods=["POST"])
def get_columns():
    """
    Reads the uploaded CSV file header and returns the column names.
    This lets the UI dynamically populate column selection dropdowns.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
        
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400
        
    try:
        # Read only the first row to get columns quickly
        df = pd.read_csv(file, nrows=0)
        columns = df.columns.tolist()
        return jsonify({"columns": columns})
    except Exception as e:
        return jsonify({"error": f"Failed to parse CSV columns: {str(e)}"}), 400

@app.route("/api/analyze", methods=["POST"])
def analyze_csv():
    """
    Receives CSV file or local file/folder path, subject metadata, and column configuration.
    Processes the signal and returns all calculations and charts.
    """
    time_col = request.form.get("time_col", "sec")
    ecg_col = request.form.get("ecg_col", "CH1")
    resp_col = request.form.get("resp_col", "CH2")
    
    try:
        fs = int(request.form.get("fs", 250))
    except ValueError:
        fs = 250

    # Check if a path parameter was provided (either JSON or form data)
    path = request.form.get("path")
    if not path and request.is_json:
        path = request.json.get("path")

    if path:
        try:
            results = analyze_biopac_path(
                path=path,
                time_col=time_col,
                ecg_col=ecg_col,
                resp_col=resp_col,
                fs=fs
            )
            if isinstance(results, dict) and "error" in results:
                return jsonify(results), 400
            return jsonify(results)
        except Exception as e:
            return jsonify({"error": f"Path analysis failed: {str(e)}"}), 500

    # Otherwise fallback to standard uploaded file
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded and no path provided"}), 400
        
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400
        
    # Save to a temporary file for analysis
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"upload_{os.urandom(8).hex()}.csv")
    
    try:
        file.save(temp_path)
        
        # Run calculations
        results = analyze_biopac_file(
            file_path=temp_path,
            time_col=time_col,
            ecg_col=ecg_col,
            resp_col=resp_col,
            fs=fs
        )
        
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        return jsonify(results)
        
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

# =========================
# FRONTEND STATIC ROUTING
# =========================

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    """
    Serves the React frontend.
    If the path exists in the static build folder, serve that file.
    Otherwise, fall back to index.html (supporting client-side routing).
    """
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, "index.html")

def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000")

# =========================
# INITIALIZATION & LAUNCH
# =========================

if __name__ == "__main__":
    # 1. Automate building the frontend if it does not exist
    frontend_dist_path = os.path.join("frontend", "dist")
    if not os.path.exists(frontend_dist_path) or not os.path.exists(os.path.join(frontend_dist_path, "index.html")):
        print("--- React production build not found. Compiling frontend... ---")
        
        # Build using pnpm
        frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
        
        # Run pnpm install and pnpm build
        install_success = os.system(f"cd {frontend_dir} && pnpm install") == 0
        if install_success:
            build_success = os.system(f"cd {frontend_dir} && pnpm run build") == 0
            if build_success:
                print("--- Frontend built successfully! ---")
            else:
                print("--- Error: Failed to compile React frontend. ---")
                sys.exit(1)
        else:
            print("--- Error: Failed to install frontend dependencies. ---")
            sys.exit(1)

    # 2. Start browser open timer (will trigger 1.5 seconds after server starts)
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        # Only open browser on primary process, not the reloader child
        Timer(1.5, open_browser).start()

    # 3. Start Flask server
    print("\n=======================================================")
    print("BIOPAC Signal Analyzer is starting on: http://localhost:5000")
    print("=======================================================\n")
    app.run(port=5000, debug=True)
