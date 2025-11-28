# protected_notes_api.py
"""
Simple Flask app implementing a protected Notes API backed by an in-memory DB.

Features:
- Endpoints: GET /notes, GET /notes/<id>, POST /notes, DELETE /notes/<id>
- Token protection via Authorization: Bearer <token>
- Scope checks: 'read:notes' for GET, 'write:notes' for POST/DELETE
- Two validation modes:
  1. TEST_MODE: accept a hard-coded token 'test-token' and inject scopes
  2. INTROSPECTION: call OAuth2 Token Introspection endpoint (RFC 7662)
  3. JWKS: validate JWT using JWKS public keys (optional)

Usage (quick):
  - python protected_notes_api.py
  - By default it runs in TEST_MODE and accepts token 'test-token'.

Environment variables (optional):
  - TEST_MODE (default 'true')
  - INTROSPECTION_URL: if set, used to validate opaque tokens
  - INTROSPECTION_CLIENT_ID, INTROSPECTION_CLIENT_SECRET: for basic auth to introspection
  - JWKS_URL: if set, used to validate JWTs (PyJWT + requests)

Dependencies:
  pip install Flask requests PyJWT cryptography

This is intentionally minimal and easy to hook to your OAuth server later.
"""

from flask import Flask, request, jsonify, abort
from functools import wraps
import os
import time
import requests
import jwt
from jwt import PyJWKClient

app = Flask(__name__)

# In-memory "database"
NOTES = {}
NEXT_ID = 1

# Configuration (read from env)
TEST_MODE = os.getenv('TEST_MODE', 'true').lower() in ('1', 'true', 'yes')
INTROSPECTION_URL = os.getenv('INTROSPECTION_URL')
INTROSPECTION_CLIENT_ID = os.getenv('INTROSPECTION_CLIENT_ID')
INTROSPECTION_CLIENT_SECRET = os.getenv('INTROSPECTION_CLIENT_SECRET')
JWKS_URL = os.getenv('JWKS_URL')

# Helper: create sample note
def _create_note(owner, title, content):
    global NEXT_ID
    note = {
        'id': NEXT_ID,
        'owner': owner,
        'title': title,
        'content': content,
        'created_at': int(time.time())
    }
    NOTES[NEXT_ID] = note
    NEXT_ID += 1
    return note

# Seed with a sample note
_create_note('user:alice', 'Welcome', 'This is your first note')

# Token validation / introspection helpers

def _introspect_token(token):
    """Call the configured introspection endpoint.
    Expected response: JSON with at least 'active': true/false and optionally 'scope' and 'sub'.
    Returns a dict with token info or None if invalid/unavailable.
    """
    if not INTROSPECTION_URL:
        return None
    data = {'token': token}
    auth = None
    if INTROSPECTION_CLIENT_ID and INTROSPECTION_CLIENT_SECRET:
        auth = (INTROSPECTION_CLIENT_ID, INTROSPECTION_CLIENT_SECRET)
    try:
        resp = requests.post(INTROSPECTION_URL, data=data, auth=auth, timeout=5)
        if resp.status_code != 200:
            app.logger.warning('Introspection endpoint returned %s', resp.status_code)
            return None
        info = resp.json()
        if not info.get('active'):
            return None
        # normalize scopes into a list
        scope_str = info.get('scope', '')
        scopes = scope_str.split() if scope_str else []
        return {
            'active': True,
            'scopes': scopes,
            'sub': info.get('sub') or info.get('username')
        }
    except Exception as e:
        app.logger.exception('Error calling introspection: %s', e)
        return None


def _validate_jwt(token):
    """Validate a JWT using a JWKS URL if provided. Returns token claims dict if valid.
    Requires PyJWT and requests.
    """
    if not JWKS_URL:
        return None
    try:
        jwk_client = PyJWKClient(JWKS_URL)
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(token, signing_key.key, algorithms=["RS256"], options={"verify_aud": False})
        # parse scopes
        scope = claims.get('scope') or claims.get('scp') or ''
        scopes = scope.split() if isinstance(scope, str) else scope
        return {
            'active': True,
            'scopes': scopes,
            'sub': claims.get('sub')
        }
    except Exception as e:
        app.logger.warning('JWT validation failed: %s', e)
        return None


def _mock_token_info(token):
    """A simple mock for TEST_MODE. Accept token 'test-token' and return scopes.
    - 'test-token' => scopes: read:notes write:notes
    - 'read-only' => scopes: read:notes
    """
    if token == 'test-token':
        return {'active': True, 'scopes': ['read:notes', 'write:notes'], 'sub': 'user:alice'}
    if token == 'read-only':
        return {'active': True, 'scopes': ['read:notes'], 'sub': 'user:bob'}
    return None


def introspect(token):
    """Unified token introspection / validation pipeline.
    Tries, in order: JWT via JWKS, OAuth2 introspection endpoint, TEST_MODE mock.
    Returns dict with keys: active (True), scopes (list), sub (string) or None.
    """
    # Try JWT validation first (if JWKS_URL set)
    if JWKS_URL:
        info = _validate_jwt(token)
        if info:
            return info
    # Try introspection endpoint
    if INTROSPECTION_URL:
        info = _introspect_token(token)
        if info:
            return info
    # Fallback to test mock
    if TEST_MODE:
        return _mock_token_info(token)
    return None

# Auth decorator

def requires_auth(required_scopes=None):
    required_scopes = required_scopes or []
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            auth = request.headers.get('Authorization', '')
            if not auth.startswith('Bearer '):
                return jsonify({'error': 'missing_authorization'}), 401
            token = auth.split(' ', 1)[1].strip()
            info = introspect(token)
            if not info or not info.get('active'):
                return jsonify({'error': 'invalid_token'}), 401
            token_scopes = info.get('scopes', [])
            # Check required scopes
            missing = [s for s in required_scopes if s not in token_scopes]
            if missing:
                return jsonify({'error': 'insufficient_scope', 'missing': missing}), 403
            # attach token info to request context (simple)
            request.token_info = info
            return f(*args, **kwargs)
        return wrapped
    return decorator

# Routes

@app.route('/notes', methods=['GET'])
@requires_auth(required_scopes=['read:notes'])
def list_notes():
    """List notes belonging to the token subject (sub)."""
    sub = request.token_info.get('sub')
    user_notes = [n for n in NOTES.values() if n['owner'] == sub]
    return jsonify(user_notes)

@app.route('/notes/<int:note_id>', methods=['GET'])
@requires_auth(required_scopes=['read:notes'])
def get_note(note_id):
    sub = request.token_info.get('sub')
    note = NOTES.get(note_id)
    if not note or note['owner'] != sub:
        return jsonify({'error': 'not_found'}), 404
    return jsonify(note)

@app.route('/notes', methods=['POST'])
@requires_auth(required_scopes=['write:notes'])
def create_note():
    data = request.get_json() or {}
    title = data.get('title', '')
    content = data.get('content', '')
    if not title:
        return jsonify({'error': 'title_required'}), 400
    sub = request.token_info.get('sub')
    note = _create_note(sub, title, content)
    return jsonify(note), 201

@app.route('/notes/<int:note_id>', methods=['DELETE'])
@requires_auth(required_scopes=['write:notes'])
def delete_note(note_id):
    sub = request.token_info.get('sub')
    note = NOTES.get(note_id)
    if not note or note['owner'] != sub:
        return jsonify({'error': 'not_found'}), 404
    del NOTES[note_id]
    return '', 204

@app.route('/.well-known/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    # helpful startup info printed to console
    print('Starting Protected Notes API (Flask)')
    print('TEST_MODE=', TEST_MODE)
    if INTROSPECTION_URL:
        print('INTROSPECTION_URL=', INTROSPECTION_URL)
    if JWKS_URL:
        print('JWKS_URL=', JWKS_URL)
    app.run(host='0.0.0.0', port=5001, debug=True)
