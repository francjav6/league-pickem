import { useEffect, useMemo, useState } from "react";

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

async function api(path, options = {}) {
  const token = localStorage.getItem("pickem_token");
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API}${path}`, {
    ...options,
    headers,
  });

  const body = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(body.detail || `Error ${response.status}`);
  }

  return body;
}

function formatDate(value) {
  if (!value) return "Sin configurar";
  return new Date(value).toLocaleString();
}

function signedNumber(value) {
  if (value > 0) return `+${value}`;
  return `${value}`;
}

function Auth({ onAuth }) {
  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setWorking(true);
    setError("");

    try {
      const data = await api(`/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify({ name, pin }),
      });

      localStorage.setItem("pickem_token", data.token);
      localStorage.setItem("pickem_name", data.user.name);
      onAuth(data.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setWorking(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <h1>League Pick'em</h1>
        <p className="muted">
          Elige el ganador de cada matchup. Tus picks quedan registrados con fecha y hora.
        </p>

        <div className="rules-mini">
          <strong>Reglas:</strong> acierto +10 · error -5 · sin pick -5
        </div>

        <form onSubmit={submit}>
          <label>
            Nombre
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ej. Francisco"
              required
            />
          </label>

          <label>
            PIN
            <input
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              type="password"
              minLength={4}
              placeholder="Mínimo 4 caracteres"
              required
            />
          </label>

          {error && <div className="error">{error}</div>}

          <button className="primary" disabled={working}>
            {working
              ? "Procesando..."
              : mode === "login"
              ? "Entrar"
              : "Crear cuenta"}
          </button>
        </form>

        <button
          className="link-button"
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setError("");
          }}
        >
          {mode === "login"
            ? "¿Primera vez? Crear cuenta"
            : "Ya tengo cuenta"}
        </button>
      </section>
    </main>
  );
}

function Scoreboard({ data }) {
  if (!data) return null;

  if (!data.week_complete) {
    return (
      <section className="panel scoreboard-panel">
        <div>
          <span className="eyebrow">PUNTAJE WEEK {data.week}</span>
          <h2>Resultados pendientes</h2>
          <p className="muted">
            El puntaje se publica cuando el administrador haya cargado los 7 ganadores.
            Resultados cargados: {data.results_entered}/{data.total_games}.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="panel scoreboard-panel">
      <div className="scoreboard-title">
        <div>
          <span className="eyebrow">PUNTAJE WEEK {data.week}</span>
          <h2>Resultado de la fecha</h2>
        </div>
        <div className="rules-badge">Acierto +10 · Error -5</div>
      </div>

      <div className="table-wrap compact-table">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Jugador</th>
              <th>Aciertos</th>
              <th>Errores</th>
              <th>Sin pick</th>
              <th>Plata fecha</th>
              <th>Acumulado</th>
            </tr>
          </thead>
          <tbody>
            {data.players.map((p, index) => (
              <tr key={p.player}>
                <td>{index + 1}</td>
                <td><strong>{p.player}</strong></td>
                <td>{p.correct}</td>
                <td>{p.wrong}</td>
                <td>{p.missing}</td>
                <td className={p.week_points >= 0 ? "positive-score" : "negative-score"}>
                  <strong>{signedNumber(p.week_points)}</strong>
                </td>
                <td><strong>{signedNumber(p.cumulative_points)}</strong></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function AdminView({ onBack, initialWeek = 1 }) {
  const [adminKey, setAdminKey] = useState(
    sessionStorage.getItem("pickem_admin_key") || ""
  );
  const [week, setWeek] = useState(initialWeek);
  const [rows, setRows] = useState([]);
  const [history, setHistory] = useState([]);
  const [results, setResults] = useState(null);
  const [scoreboard, setScoreboard] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    setError("");
    setMessage("");

    try {
      sessionStorage.setItem("pickem_admin_key", adminKey);
      const headers = { "X-Admin-Key": adminKey };

      const [current, changes, resultData] = await Promise.all([
        api(`/admin/weeks/${week}/picks`, { headers }),
        api(`/admin/weeks/${week}/history`, { headers }),
        api(`/admin/weeks/${week}/results`, { headers }),
      ]);

      setRows(current);
      setHistory(changes);
      setResults(resultData);

      try {
        setScoreboard(await api(`/weeks/${week}/leaderboard`));
      } catch {
        setScoreboard(null);
      }
    } catch (err) {
      setError(err.message);
    }
  }

  async function setWinner(matchupId, choice) {
    setError("");
    setMessage("");

    try {
      const headers = { "X-Admin-Key": adminKey };

      await api(`/admin/matchups/${matchupId}/result`, {
        method: "PUT",
        headers,
        body: JSON.stringify({ winner_choice: choice }),
      });

      setMessage("Ganador actualizado.");
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  function changeWeek(nextWeek) {
    setWeek(nextWeek);
    setRows([]);
    setHistory([]);
    setResults(null);
    setScoreboard(null);
    setMessage("");
    setError("");
  }

  return (
    <main className="page">
      <div className="topbar">
        <div>
          <h1>Administrador</h1>
          <p className="muted">Picks, cierres y resultados</p>
        </div>
        <button onClick={onBack}>Volver</button>
      </div>

      <section className="panel">
        <div className="admin-week-row">
          <button
            disabled={week <= 1}
            onClick={() => changeWeek(Math.max(1, week - 1))}
          >
            ←
          </button>
          <strong>Week {week}</strong>
          <button
            disabled={week >= 14}
            onClick={() => changeWeek(Math.min(14, week + 1))}
          >
            →
          </button>
        </div>

        <div className="admin-key-row">
          <input
            value={adminKey}
            onChange={(e) => setAdminKey(e.target.value)}
            placeholder="ADMIN_KEY"
            type="password"
          />
          <button className="primary" onClick={load}>
            Cargar administración
          </button>
        </div>

        {error && <div className="error">{error}</div>}
        {message && <div className="success">{message}</div>}
      </section>

      {results && (
        <section className="panel admin-results-panel">
          <div className="scoreboard-title">
            <div>
              <span className="eyebrow">WEEK {week}</span>
              <h2>Cargar ganadores</h2>
            </div>
            <div className={results.week_complete ? "complete-badge" : "pending-badge"}>
              {results.results_entered}/{results.total_games} resultados
            </div>
          </div>

          <p className="deadline-line">
            🔒 Cierre automático de picks: <strong>{formatDate(results.lock_at)}</strong>
          </p>

          <div className="admin-result-list">
            {results.matchups.map((m) => (
              <div className="admin-result-row" key={m.id}>
                <button
                  className={`result-choice ${m.winner_choice === "A" ? "winner-selected" : ""}`}
                  onClick={() => setWinner(m.id, "A")}
                >
                  {m.team_a}
                </button>

                <span>vs</span>

                <button
                  className={`result-choice ${m.winner_choice === "B" ? "winner-selected" : ""}`}
                  onClick={() => setWinner(m.id, "B")}
                >
                  {m.team_b}
                </button>
              </div>
            ))}
          </div>

          <p className="muted small-text">
            Cuando hayas marcado los 7 ganadores, el puntaje de la fecha se publica automáticamente.
          </p>
        </section>
      )}

      {scoreboard?.week_complete && <Scoreboard data={scoreboard} />}

      {rows.length > 0 && (
        <section className="panel">
          <h2>Picks actuales</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Jugador</th>
                  <th>Matchup</th>
                  <th>Pick</th>
                  <th>Última modificación</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={`${r.player}-${r.matchup_id}-${i}`}>
                    <td>{r.player}</td>
                    <td>{r.matchup}</td>
                    <td>{r.pick || "—"}</td>
                    <td>
                      {r.updated_at
                        ? new Date(r.updated_at).toLocaleString()
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2>Historial de cambios</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Hora</th>
                  <th>Jugador</th>
                  <th>Matchup</th>
                  <th>Selección</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h, i) => (
                  <tr key={`${h.player}-${h.matchup_id}-${h.changed_at}-${i}`}>
                    <td>{new Date(h.changed_at).toLocaleString()}</td>
                    <td>{h.player}</td>
                    <td>{h.matchup}</td>
                    <td>{h.pick}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}

function Picks({ user, onLogout }) {
  const [week, setWeek] = useState(1);
  const [matchups, setMatchups] = useState([]);
  const [scoreboard, setScoreboard] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [adminMode, setAdminMode] = useState(false);

  async function loadWeek() {
    setError("");

    try {
      const [matchupData, scoreData] = await Promise.all([
        api(`/weeks/${week}/matchups`),
        api(`/weeks/${week}/leaderboard`),
      ]);

      setMatchups(matchupData);
      setScoreboard(scoreData);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    loadWeek();
  }, [week]);

  async function choose(matchupId, choice) {
    setMessage("");
    setError("");

    try {
      const saved = await api(`/picks/${matchupId}`, {
        method: "PUT",
        body: JSON.stringify({ choice }),
      });

      setMatchups((old) =>
        old.map((m) =>
          m.id === matchupId ? { ...m, my_pick: choice } : m
        )
      );

      setMessage(`Guardado: ${saved.team}`);
    } catch (err) {
      setError(err.message);
    }
  }

  const picksDone = useMemo(
    () => matchups.filter((m) => m.my_pick).length,
    [matchups]
  );

  const lockAt = matchups.length ? matchups[0].starts_at : null;
  const locked = matchups.length ? matchups[0].locked : false;
  const weekComplete = matchups.length ? matchups[0].week_complete : false;

  function choiceClass(m, choice) {
    const selected = m.my_pick === choice;
    if (!selected) return "team-choice";

    if (weekComplete && m.winner_choice) {
      return `team-choice selected ${
        m.winner_choice === choice ? "correct-pick" : "wrong-pick"
      }`;
    }

    return "team-choice selected";
  }

  if (adminMode) {
    return (
      <AdminView
        initialWeek={week}
        onBack={() => {
          setAdminMode(false);
          loadWeek();
        }}
      />
    );
  }

  return (
    <main className="page">
      <div className="topbar">
        <div>
          <h1>League Pick'em</h1>
          <p className="muted">
            Hola, <strong>{user?.name || localStorage.getItem("pickem_name")}</strong>
          </p>
        </div>

        <div className="top-actions">
          <button onClick={() => setAdminMode(true)}>Admin</button>
          <button onClick={onLogout}>Salir</button>
        </div>
      </div>

      <section className="panel summary">
        <div>
          <span className="eyebrow">WEEK {week}</span>
          <h2>Tus predicciones</h2>
          <p className="deadline-summary">
            {locked ? "🔒 Picks cerrados" : "⏳ Cierra"}:{" "}
            <strong>{formatDate(lockAt)}</strong>
          </p>
          <p className="rules-line">Acierto +10 · Error -5 · Sin pick -5</p>
        </div>

        <div className="week-navigation">
          <button
            className="week-arrow"
            disabled={week <= 1}
            onClick={() => {
              setMessage("");
              setWeek((w) => Math.max(1, w - 1));
            }}
          >
            ←
          </button>

          <strong>Week {week}</strong>

          <button
            className="week-arrow"
            disabled={week >= 14}
            onClick={() => {
              setMessage("");
              setWeek((w) => Math.min(14, w + 1));
            }}
          >
            →
          </button>
        </div>

        <div className="counter">{picksDone}/{matchups.length}</div>
      </section>

      {message && <div className="success">{message}</div>}
      {error && <div className="error">{error}</div>}

      <section className="matchup-list">
        {matchups.map((m, index) => (
          <article
            className={`matchup-card ${m.locked ? "locked" : ""}`}
            key={m.id}
          >
            <div className="matchup-meta">
              <span>Matchup #{index + 1}</span>
              <span>{m.locked ? "🔒 Cerrado" : "Abierto"}</span>
            </div>

            <div className="choices">
              <button
                className={choiceClass(m, "A")}
                disabled={m.locked}
                onClick={() => choose(m.id, "A")}
              >
                {m.team_a}
              </button>

              <span className="vs">VS</span>

              <button
                className={choiceClass(m, "B")}
                disabled={m.locked}
                onClick={() => choose(m.id, "B")}
              >
                {m.team_b}
              </button>
            </div>

            {weekComplete && m.winner_choice && (
              <p className="winner-line">
                Ganador:{" "}
                <strong>
                  {m.winner_choice === "A" ? m.team_a : m.team_b}
                </strong>
              </p>
            )}
          </article>
        ))}
      </section>

      <Scoreboard data={scoreboard} />
    </main>
  );
}

export default function App() {
  const [user, setUser] = useState(
    localStorage.getItem("pickem_token")
      ? { name: localStorage.getItem("pickem_name") }
      : null
  );

  function logout() {
    localStorage.removeItem("pickem_token");
    localStorage.removeItem("pickem_name");
    setUser(null);
  }

  if (!user) return <Auth onAuth={setUser} />;

  return <Picks user={user} onLogout={logout} />;
}
