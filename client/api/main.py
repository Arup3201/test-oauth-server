# oauth_client_backend.py
"""
OAuth Client Backend API for requesting authorization to access the Protected Notes API.

This acts as a confidential OAuth client registered with your OAuth server.
It handles the OAuth Authorization Code Flow with PKCE or with client_secret
(depending on your OAuth server setup). For simplicity, this example uses
client_id + client_secret (confidential backend client).

Responsibilities:
- Redirect user to your OAuth server's authorization endpoint
- Handle authorization callback (receive authorization code)
- Exchange authorization code for access token
- Store user session + access tokens in memory (for testing)
- Provide endpoints for the front-end to initiate OAuth and fetch notes via the protected Notes API

Environment variables required:
  OAUTH_AUTH_URL        = Authorization endpoint (e.g., http://localhost:8000/oauth/authorize)
  OAUTH_TOKEN_URL       = Token endpoint         (e.g., http://localhost:8000/oauth/token)
  CLIENT_ID             = Issued by OAuth server
  CLIENT_SECRET         = Issued by OAuth server
  REDIRECT_URI          = Callback URL (must match what is registered)
  NOTES_API_URL         = Base URL of Notes API (e.g., http://localhost:5001)

Run:
  python oauth_client_backend.py

Dependencies:
  pip install Flask requests
"""

from flask import Flask, request, redirect, jsonify, session
import requests
import os

app = Flask(__name__)
app.secret_key = "dev-secret"  # For demo only

# Configuration
OAUTH_AUTH_URL = os.getenv("OAUTH_AUTH_URL", "")
OAUTH_TOKEN_URL = os.getenv("OAUTH_TOKEN_URL", "")
CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("REDIRECT_URI", "")
NOTES_API_URL = os.getenv("NOTES_API_URL", "")

REQUESTED_SCOPES = "notes:read notes:write"

# Simple in-memory token storage per session
# In real systems, use a DB or encrypted store

@app.route("/oauth/login")
def oauth_login():
    """
    Step 1: Redirect user to OAuth server with required query params.
    """
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": REQUESTED_SCOPES,
        "state": "random-state",  # CSRF protection placeholder
    }

    # Build redirect URL
    query = "&".join(f"{k}={requests.utils.quote(v)}" for k, v in params.items())
    return redirect(f"{OAUTH_AUTH_URL}?{query}")


@app.route("/oauth/callback")
def oauth_callback():
    """
    Step 2: Receive authorization code from OAuth server.
    Step 3: Exchange authorization code for tokens.
    """
    error = request.args.get("error")
    if error:
        return jsonify({"error": error}), 400

    code = request.args.get("code")
    if not code:
        return jsonify({"error": "missing_code"}), 400

    # Exchange code for token
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }

    token_resp = requests.post(OAUTH_TOKEN_URL, data=data)

    if token_resp.status_code != 200:
        return jsonify({"error": "token_exchange_failed", "details": token_resp.text}), 400

    token_data = token_resp.json()

    # Store tokens in session
    session["access_token"] = token_data.get("access_token")
    session["refresh_token"] = token_data.get("refresh_token")
    session["scope"] = token_data.get("scope")

    return jsonify({"message": "Authorization success", "token": token_data})


@app.route("/client/notes", methods=["GET"])
def client_list_notes():
    """
    Called by the client's frontend.
    Uses stored access_token to call the protected Notes API.
    """
    access_token = session.get("access_token")
    if not access_token:
        return jsonify({"error": "not_authenticated"}), 401

    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(f"{NOTES_API_URL}/notes", headers=headers)

    return jsonify({"status": resp.status_code, "data": resp.json()})


@app.route("/client/create-note", methods=["POST"])
def client_create_note():
    access_token = session.get("access_token")
    if not access_token:
        return jsonify({"error": "not_authenticated"}), 401

    data = request.get_json() or {}
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    resp = requests.post(f"{NOTES_API_URL}/notes", json=data, headers=headers)

    return jsonify({"status": resp.status_code, "data": resp.json()})


@app.route("/session/info")
def session_info():
    return jsonify({
        "access_token": session.get("access_token"),
        "refresh_token": session.get("refresh_token"),
        "scope": session.get("scope"),
    })


@app.route("/.well-known/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    print("Starting OAuth Client Backend API on port 5002...")
    print("AUTH_URL=", OAUTH_AUTH_URL)
    print("TOKEN_URL=", OAUTH_TOKEN_URL)
    app.run(host="0.0.0.0", port=5002, debug=True)
