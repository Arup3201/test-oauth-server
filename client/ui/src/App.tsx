import React, { useState, useEffect } from "react";

export default function App() {
  const [notes, setNotes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [authInfo, setAuthInfo] = useState(null);
  const [error, setError] = useState(null);

  const API_BASE = "http://localhost:5002"; // OAuth client backend

  const fetchSession = async () => {
    try {
      const resp = await fetch(`${API_BASE}/session/info`, {
        credentials: "include",
      });
      if (!resp.ok) {
        setAuthInfo(null);
        return;
      }
      const data = await resp.json();
      setAuthInfo(data);
    } catch (e) {
      console.error("fetchSession error", e);
      setAuthInfo(null);
    }
  };

  const login = () => {
    // Redirect the browser to the backend login endpoint which will start the OAuth flow
    window.location.href = `${API_BASE}/oauth/login`;
  };

  const loadNotes = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${API_BASE}/client/notes`, {
        credentials: "include",
      });
      // The backend returns a JSON object like { status: <code>, data: <notes|error> }
      const json = await resp.json().catch(() => ({}));

      // If the backend proxied a non-200 from the resource server, handle it
      if (resp.status === 401 || json.error === "not_authenticated") {
        setError("Not authenticated. Please login.");
        setNotes([]);
      } else if (resp.status >= 400) {
        setError(json.error || json.message || `Error ${resp.status}`);
        setNotes([]);
      } else {
        // Some backends return {status: 200, data: [...]}
        if (json && Array.isArray(json.data)) {
          setNotes(json.data);
        } else if (Array.isArray(json)) {
          setNotes(json);
        } else {
          setNotes([]);
        }
      }
    } catch (e) {
      console.error("loadNotes error", e);
      setError("Failed to load notes");
      setNotes([]);
    } finally {
      setLoading(false);
    }
  };

  const createNote = async () => {
    if (!title.trim()) {
      setError("Title is required");
      return;
    }
    setError(null);
    try {
      const resp = await fetch(`${API_BASE}/client/create-note`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: title.trim(), content: content.trim() }),
      });
      const json = await resp.json().catch(() => ({}));
      if (
        resp.status === 201 ||
        (json && (json.status === 201 || json.status === 200))
      ) {
        setTitle("");
        setContent("");
        await loadNotes();
      } else if (resp.status === 401 || json.error === "not_authenticated") {
        setError("Not authenticated. Please login.");
      } else {
        setError(
          json.error ||
            json.message ||
            `Failed to create (status ${resp.status})`
        );
      }
    } catch (e) {
      console.error("createNote error", e);
      setError("Failed to create note");
    }
  };

  useEffect(() => {
    // On app load, fetch session and, if authenticated, load notes
    (async () => {
      await fetchSession();
    })();
  }, []);

  useEffect(() => {
    if (authInfo && authInfo.access_token) {
      loadNotes();
    }
  }, [authInfo]);

  return (
    <div
      style={{
        maxWidth: 800,
        margin: "2rem auto",
        fontFamily: "system-ui, sans-serif",
        padding: "1rem",
      }}
    >
      <h1 style={{ fontSize: "1.5rem", marginBottom: "1rem" }}>
        Notes — OAuth Client UI
      </h1>

      <div
        style={{
          border: "1px solid #e5e7eb",
          padding: "1rem",
          borderRadius: 8,
          marginBottom: "1rem",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "1rem" }}>Authentication</h2>
        <div style={{ marginTop: "0.5rem" }}>
          {authInfo && authInfo.access_token ? (
            <div style={{ color: "green" }}>Authenticated</div>
          ) : (
            <button
              onClick={login}
              style={{
                padding: "0.5rem 1rem",
                borderRadius: 8,
                background: "#2563eb",
                color: "white",
                border: "none",
              }}
            >
              Login with OAuth
            </button>
          )}
        </div>
      </div>

      {error && (
        <div style={{ color: "crimson", marginBottom: "1rem" }}>{error}</div>
      )}

      {authInfo && authInfo.access_token && (
        <div
          style={{
            border: "1px solid #e5e7eb",
            padding: "1rem",
            borderRadius: 8,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <h2 style={{ margin: 0 }}>Your Notes</h2>
            <div>
              <button
                onClick={loadNotes}
                style={{
                  marginRight: 8,
                  padding: "0.4rem 0.8rem",
                  borderRadius: 6,
                }}
              >
                Refresh
              </button>
            </div>
          </div>

          <div style={{ marginTop: "0.75rem" }}>
            {loading ? (
              <div>Loading...</div>
            ) : (
              <div>
                {notes.length === 0 && <div>No notes yet.</div>}
                <ul
                  style={{ listStyle: "none", padding: 0, marginTop: "0.5rem" }}
                >
                  {notes.map((n) => (
                    <li
                      key={n.id}
                      style={{
                        padding: "0.75rem",
                        border: "1px solid #f3f4f6",
                        marginBottom: "0.5rem",
                        borderRadius: 6,
                      }}
                    >
                      <div style={{ fontWeight: 600 }}>{n.title}</div>
                      <div style={{ color: "#374151" }}>{n.content}</div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <div
            style={{
              marginTop: "1rem",
              borderTop: "1px solid #e5e7eb",
              paddingTop: "1rem",
            }}
          >
            <h3 style={{ margin: 0 }}>Create Note</h3>
            <div style={{ marginTop: "0.5rem" }}>
              <input
                type="text"
                placeholder="Title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                style={{
                  width: "100%",
                  padding: "0.5rem",
                  borderRadius: 6,
                  border: "1px solid #d1d5db",
                  marginBottom: "0.5rem",
                }}
              />
              <textarea
                placeholder="Content"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={4}
                style={{
                  width: "100%",
                  padding: "0.5rem",
                  borderRadius: 6,
                  border: "1px solid #d1d5db",
                  marginBottom: "0.5rem",
                }}
              />
              <div>
                <button
                  onClick={createNote}
                  disabled={!title.trim()}
                  style={{
                    padding: "0.5rem 1rem",
                    borderRadius: 6,
                    background: "#16a34a",
                    color: "white",
                    border: "none",
                  }}
                >
                  Add Note
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {!authInfo && (
        <div style={{ marginTop: "1rem", color: "#6b7280" }}>
          You are not logged in. Click Login to start OAuth authorization.
        </div>
      )}
    </div>
  );
}
