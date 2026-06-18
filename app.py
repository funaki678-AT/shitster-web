import os, secrets, threading, uuid, tempfile
import requests
import spotipy
from flask import (Flask, render_template, request, redirect,
                   session, send_file, jsonify, url_for)
from generator import generate_pdfs_from_tracks, get_tracks_from_playlist

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

CLIENT_ID     = os.environ.get("SPOTIFY_CLIENT_ID",     "5839ffa0907243398d394ddb8b1f6acd")
CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "6a615238ad0d4ca0bfb046cb87b55e3b")
REDIRECT_URI  = os.environ.get("REDIRECT_URI",          "http://localhost:5000/callback")

jobs = {}   # { job_id: { status, progress, message, ... } }

# ── Seiten ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html",
                           authenticated=bool(session.get("spotify_token")))

# ── Spotify OAuth ─────────────────────────────────────────────────────────────
@app.route("/login")
def login():
    state = secrets.token_hex(16)
    session["oauth_state"] = state
    from urllib.parse import urlencode
    params = urlencode({
        "client_id":     CLIENT_ID,
        "response_type": "code",
        "redirect_uri":  REDIRECT_URI,
        "scope":         "playlist-read-private playlist-read-collaborative",
        "state":         state,
    })
    return redirect("https://accounts.spotify.com/authorize?" + params)

@app.route("/callback")
def callback():
    code  = request.args.get("code")
    state = request.args.get("state")
    if state != session.pop("oauth_state", None):
        return "State mismatch", 400
    res = requests.post("https://accounts.spotify.com/api/token", data={
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  REDIRECT_URI,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    data = res.json()
    if "error" in data:
        return f"Spotify Fehler: {data['error']}", 400
    session["spotify_token"]   = data["access_token"]
    session["spotify_refresh"] = data.get("refresh_token")
    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ── Karten generieren ─────────────────────────────────────────────────────────
@app.route("/generate", methods=["POST"])
def generate():
    token = session.get("spotify_token")
    if not token:
        return jsonify({"error": "Nicht angemeldet"}), 401
    playlist_urls = request.json.get("playlists", [])
    if not playlist_urls:
        return jsonify({"error": "Keine Playlists angegeben"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "running", "progress": 0,
                    "message": "Starte…", "total": 0}
    thread = threading.Thread(
        target=run_generation,
        args=(job_id, token, playlist_urls),
        daemon=True
    )
    thread.start()
    return jsonify({"job_id": job_id})

@app.route("/status/<job_id>")
def status(job_id):
    return jsonify(jobs.get(job_id, {"status": "not_found"}))

@app.route("/download/<job_id>/<side>")
def download(job_id, side):
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return "Nicht gefunden", 404
    if side == "front":
        path, name = job["front_path"],  "shitster_vorderseiten.pdf"
    elif side == "back":
        path, name = job["back_path"],   "shitster_rueckseiten.pdf"
    elif side == "duplex":
        path, name = job["duplex_path"], "shitster_duplex.pdf"
    else:
        return "Ungültige Seite", 400
    return send_file(path, as_attachment=True, download_name=name)

# ── Hintergrund-Job ───────────────────────────────────────────────────────────
def run_generation(job_id, token, playlist_urls):
    try:
        sp = spotipy.Spotify(auth=token)
        all_tracks = []

        for i, url in enumerate(playlist_urls):
            jobs[job_id]["message"] = (
                f"Lade Playlist {i+1} von {len(playlist_urls)}…"
            )
            tracks = get_tracks_from_playlist(sp, url)
            all_tracks.extend(tracks)
            jobs[job_id]["progress"] = int((i+1) / len(playlist_urls) * 20)

        if not all_tracks:
            jobs[job_id] = {
                "status": "error",
                "message": "Keine Tracks gefunden. Bitte URL prüfen.",
                "progress": 0,
            }
            return

        jobs[job_id]["total"]   = len(all_tracks)
        jobs[job_id]["message"] = (
            f"{len(all_tracks)} Lieder gefunden – erstelle Karten…"
        )

        out_dir = tempfile.mkdtemp()

        def progress_cb(current, total):
            jobs[job_id]["progress"] = 20 + int(current / total * 75)
            jobs[job_id]["message"]  = f"Erstelle Karte {current} von {total}…"

        front, back, duplex = generate_pdfs_from_tracks(all_tracks, out_dir, progress_cb)

        jobs[job_id] = {
            "status":       "done",
            "progress":     100,
            "message":      f"{len(all_tracks)} Karten erfolgreich erstellt!",
            "front_path":   front,
            "back_path":    back,
            "duplex_path":  duplex,
            "track_count":  len(all_tracks),
        }
    except Exception as e:
        jobs[job_id] = {
            "status":  "error",
            "message": str(e),
            "progress": 0,
        }

if __name__ == "__main__":
    app.run(debug=True, port=5000)
