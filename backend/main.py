import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pickem.db")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
ADMIN_KEY = os.getenv("ADMIN_KEY", "dev-admin-change-me")
CORS_ORIGINS = [
    x.strip()
    for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if x.strip()
]

POINTS_CORRECT = 10
POINTS_INCORRECT = -5
# Solo se puntúan los pronósticos realizados; una ausencia vale cero.
POINTS_MISSING = 0

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, nullable=False, index=True)
    pin_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Matchup(Base):
    __tablename__ = "matchups"
    id = Column(Integer, primary_key=True)
    week = Column(Integer, nullable=False, index=True)
    team_a = Column(String(120), nullable=False)
    team_b = Column(String(120), nullable=False)

    # En esta app todos los matchups de una misma semana comparten el mismo
    # starts_at: el kickoff del PRIMER partido NFL de esa semana.
    starts_at = Column(DateTime(timezone=True), nullable=True)

    manually_locked = Column(Boolean, default=False, nullable=False)
    winner_choice = Column(String(1), nullable=True)  # "A" o "B"


class Pick(Base):
    __tablename__ = "picks"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    matchup_id = Column(Integer, ForeignKey("matchups.id"), nullable=False)
    choice = Column(String(1), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    user = relationship("User")
    matchup = relationship("Matchup")
    __table_args__ = (
        UniqueConstraint("user_id", "matchup_id", name="uq_user_matchup"),
    )


class PickHistory(Base):
    __tablename__ = "pick_history"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    matchup_id = Column(Integer, ForeignKey("matchups.id"), nullable=False)
    choice = Column(String(1), nullable=False)
    changed_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    user = relationship("User")
    matchup = relationship("Matchup")


Base.metadata.create_all(bind=engine)

app = FastAPI(title="League Pick'em API", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def now_utc():
    return datetime.now(timezone.utc)


def normalize_dt(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        # SQLite puede devolver DateTime sin tzinfo. Los guardamos siempre en UTC.
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def matchup_locked(m: Matchup) -> bool:
    if m.manually_locked:
        return True
    if m.starts_at is None:
        return False
    return now_utc() >= normalize_dt(m.starts_at)


def week_complete(matchups) -> bool:
    return bool(matchups) and all(m.winner_choice in {"A", "B"} for m in matchups)


def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 210_000
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, iterations)
    return "$".join(
        [
            "pbkdf2_sha256",
            str(iterations),
            base64.urlsafe_b64encode(salt).decode(),
            base64.urlsafe_b64encode(digest).decode(),
        ]
    )


def verify_pin(pin: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64)
        expected = base64.urlsafe_b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "name": user.name,
        "exp": now_utc() + timedelta(days=30),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Falta Authorization: Bearer <token>")

    token = authorization.split(" ", 1)[1].strip()

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(401, "Token inválido o vencido")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(401, "Usuario no encontrado")
    return user


def require_admin(x_admin_key: Optional[str] = Header(default=None)):
    if not x_admin_key or not hmac.compare_digest(x_admin_key, ADMIN_KEY):
        raise HTTPException(403, "Admin key inválida")


def calculate_user_week(db: Session, user: User, week: int):
    matchups = (
        db.query(Matchup)
        .filter(Matchup.week == week)
        .order_by(Matchup.id)
        .all()
    )

    if not week_complete(matchups):
        return None

    picks = {
        p.matchup_id: p
        for p in db.query(Pick)
        .join(Matchup)
        .filter(Pick.user_id == user.id, Matchup.week == week)
        .all()
    }

    correct = 0
    wrong = 0
    missing = 0

    for m in matchups:
        pick = picks.get(m.id)
        if pick is None:
            missing += 1
        elif pick.choice == m.winner_choice:
            correct += 1
        else:
            wrong += 1

    points = (
        correct * POINTS_CORRECT
        + wrong * POINTS_INCORRECT
        + missing * POINTS_MISSING
    )

    return {
        "correct": correct,
        "wrong": wrong,
        "missing": missing,
        "points": points,
        "total_games": len(matchups),
    }


def cumulative_points_through(db: Session, user: User, through_week: int):
    total = 0
    completed_weeks = 0

    for w in range(1, through_week + 1):
        result = calculate_user_week(db, user, w)
        if result is not None:
            total += result["points"]
            completed_weeks += 1

    return total, completed_weeks


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    pin: str = Field(min_length=4, max_length=32)


class LoginIn(BaseModel):
    name: str
    pin: str


class PickIn(BaseModel):
    choice: str


class LockIn(BaseModel):
    locked: bool


class ResultIn(BaseModel):
    winner_choice: Optional[str] = None


class MatchupTimeIn(BaseModel):
    starts_at: Optional[datetime] = None


class WeekLockIn(BaseModel):
    lock_at: datetime


@app.get("/")
def root():
    return {"ok": True, "service": "League Pick'em API"}


@app.post("/auth/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    name = data.name.strip()
    if db.query(User).filter(User.name == name).first():
        raise HTTPException(409, "Ese nombre ya está registrado")

    user = User(name=name, pin_hash=hash_pin(data.pin))
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "token": create_token(user),
        "user": {"id": user.id, "name": user.name},
    }


@app.post("/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.name == data.name.strip()).first()

    if not user or not verify_pin(data.pin, user.pin_hash):
        raise HTTPException(401, "Nombre o PIN incorrectos")

    return {
        "token": create_token(user),
        "user": {"id": user.id, "name": user.name},
    }


@app.get("/weeks/{week}/matchups")
def week_matchups(
    week: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    matchups = (
        db.query(Matchup)
        .filter(Matchup.week == week)
        .order_by(Matchup.id)
        .all()
    )

    picks = {
        p.matchup_id: p
        for p in db.query(Pick)
        .join(Matchup)
        .filter(Pick.user_id == user.id, Matchup.week == week)
        .all()
    }

    completed = week_complete(matchups)

    return [
        {
            "id": m.id,
            "week": m.week,
            "team_a": m.team_a,
            "team_b": m.team_b,
            "starts_at": m.starts_at,
            "locked": matchup_locked(m),
            "my_pick": picks[m.id].choice if m.id in picks else None,
            # No revelamos resultados parciales. Aparecen cuando la fecha completa.
            "winner_choice": m.winner_choice if completed else None,
            "week_complete": completed,
        }
        for m in matchups
    ]


@app.put("/picks/{matchup_id}")
def save_pick(
    matchup_id: int,
    data: PickIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    choice = data.choice.upper().strip()
    if choice not in {"A", "B"}:
        raise HTTPException(400, "choice debe ser A o B")

    matchup = db.query(Matchup).filter(Matchup.id == matchup_id).first()
    if not matchup:
        raise HTTPException(404, "Matchup no encontrado")

    if matchup_locked(matchup):
        raise HTTPException(
            423,
            "La fecha ya cerró: no se pueden cambiar predicciones.",
        )

    pick = (
        db.query(Pick)
        .filter(Pick.user_id == user.id, Pick.matchup_id == matchup_id)
        .first()
    )

    changed = pick is None or pick.choice != choice
    timestamp = now_utc()

    if pick is None:
        pick = Pick(
            user_id=user.id,
            matchup_id=matchup_id,
            choice=choice,
            updated_at=timestamp,
        )
        db.add(pick)
    else:
        pick.choice = choice
        pick.updated_at = timestamp

    if changed:
        db.add(
            PickHistory(
                user_id=user.id,
                matchup_id=matchup_id,
                choice=choice,
                changed_at=timestamp,
            )
        )

    db.commit()

    selected_team = matchup.team_a if choice == "A" else matchup.team_b

    return {
        "saved": True,
        "matchup_id": matchup_id,
        "choice": choice,
        "team": selected_team,
        "updated_at": timestamp,
    }


@app.get("/me/picks")
def my_picks(
    week: int = 1,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Pick)
        .join(Matchup)
        .filter(Pick.user_id == user.id, Matchup.week == week)
        .order_by(Matchup.id)
        .all()
    )

    return [
        {
            "matchup_id": p.matchup_id,
            "matchup": f"{p.matchup.team_a} vs {p.matchup.team_b}",
            "choice": p.choice,
            "team": p.matchup.team_a if p.choice == "A" else p.matchup.team_b,
            "updated_at": p.updated_at,
        }
        for p in rows
    ]


@app.get("/weeks/{week}/leaderboard")
def leaderboard(
    week: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.name).all()
    matchups = (
        db.query(Matchup)
        .filter(Matchup.week == week)
        .order_by(Matchup.id)
        .all()
    )

    results_entered = sum(1 for m in matchups if m.winner_choice in {"A", "B"})
    completed = week_complete(matchups)

    base = {
        "week": week,
        "week_complete": completed,
        "results_entered": results_entered,
        "total_games": len(matchups),
        "points_correct": POINTS_CORRECT,
        "points_incorrect": POINTS_INCORRECT,
        "points_missing": POINTS_MISSING,
        "players": [],
    }

    if not completed:
        return base

    table = []
    for u in users:
        weekly = calculate_user_week(db, u, week)
        cumulative, completed_weeks = cumulative_points_through(db, u, week)

        table.append(
            {
                "player": u.name,
                "correct": weekly["correct"],
                "wrong": weekly["wrong"],
                "missing": weekly["missing"],
                "week_points": weekly["points"],
                "cumulative_points": cumulative,
                "completed_weeks": completed_weeks,
            }
        )

    table.sort(
        key=lambda x: (
            -x["week_points"],
            -x["correct"],
            x["player"].lower(),
        )
    )

    base["players"] = table
    return base


@app.get("/standings")
def standings(
    through_week: int = 14,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.name).all()
    out = []

    for u in users:
        cumulative, completed_weeks = cumulative_points_through(
            db,
            u,
            min(max(through_week, 1), 14),
        )
        out.append(
            {
                "player": u.name,
                "cumulative_points": cumulative,
                "completed_weeks": completed_weeks,
            }
        )

    return sorted(
        out,
        key=lambda x: (-x["cumulative_points"], x["player"].lower()),
    )


@app.get(
    "/admin/weeks/{week}/picks",
    dependencies=[Depends(require_admin)],
)
def admin_week_picks(week: int, db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.name).all()
    matchups = (
        db.query(Matchup)
        .filter(Matchup.week == week)
        .order_by(Matchup.id)
        .all()
    )

    rows = []
    for u in users:
        for m in matchups:
            pick = (
                db.query(Pick)
                .filter(Pick.user_id == u.id, Pick.matchup_id == m.id)
                .first()
            )
            rows.append(
                {
                    "player": u.name,
                    "matchup_id": m.id,
                    "matchup": f"{m.team_a} vs {m.team_b}",
                    "pick": (
                        None
                        if not pick
                        else (m.team_a if pick.choice == "A" else m.team_b)
                    ),
                    "choice": None if not pick else pick.choice,
                    "updated_at": None if not pick else pick.updated_at,
                }
            )

    return rows


@app.get(
    "/admin/weeks/{week}/history",
    dependencies=[Depends(require_admin)],
)
def admin_week_history(week: int, db: Session = Depends(get_db)):
    rows = (
        db.query(PickHistory)
        .join(Matchup)
        .filter(Matchup.week == week)
        .order_by(PickHistory.changed_at)
        .all()
    )

    return [
        {
            "player": h.user.name,
            "matchup_id": h.matchup_id,
            "matchup": f"{h.matchup.team_a} vs {h.matchup.team_b}",
            "choice": h.choice,
            "pick": h.matchup.team_a if h.choice == "A" else h.matchup.team_b,
            "changed_at": h.changed_at,
        }
        for h in rows
    ]


@app.get(
    "/admin/weeks/{week}/results",
    dependencies=[Depends(require_admin)],
)
def admin_week_results(week: int, db: Session = Depends(get_db)):
    matchups = (
        db.query(Matchup)
        .filter(Matchup.week == week)
        .order_by(Matchup.id)
        .all()
    )

    return {
        "week": week,
        "week_complete": week_complete(matchups),
        "results_entered": sum(
            1 for m in matchups if m.winner_choice in {"A", "B"}
        ),
        "total_games": len(matchups),
        "lock_at": matchups[0].starts_at if matchups else None,
        "matchups": [
            {
                "id": m.id,
                "team_a": m.team_a,
                "team_b": m.team_b,
                "winner_choice": m.winner_choice,
            }
            for m in matchups
        ],
    }


@app.put(
    "/admin/weeks/{week}/lock-at",
    dependencies=[Depends(require_admin)],
)
def admin_week_lock_at(
    week: int,
    data: WeekLockIn,
    db: Session = Depends(get_db),
):
    rows = db.query(Matchup).filter(Matchup.week == week).all()
    if not rows:
        raise HTTPException(404, "Semana no encontrada")

    lock_at = data.lock_at
    if lock_at.tzinfo is None:
        lock_at = lock_at.replace(tzinfo=timezone.utc)
    lock_at = lock_at.astimezone(timezone.utc)

    for m in rows:
        m.starts_at = lock_at

    db.commit()

    return {
        "saved": True,
        "week": week,
        "lock_at": lock_at,
        "updated_matchups": len(rows),
    }


@app.put(
    "/admin/matchups/{matchup_id}/lock",
    dependencies=[Depends(require_admin)],
)
def admin_lock(
    matchup_id: int,
    data: LockIn,
    db: Session = Depends(get_db),
):
    m = db.query(Matchup).filter(Matchup.id == matchup_id).first()
    if not m:
        raise HTTPException(404, "Matchup no encontrado")

    m.manually_locked = data.locked
    db.commit()

    return {
        "saved": True,
        "matchup_id": matchup_id,
        "locked": m.manually_locked,
    }


@app.put(
    "/admin/matchups/{matchup_id}/starts-at",
    dependencies=[Depends(require_admin)],
)
def admin_starts_at(
    matchup_id: int,
    data: MatchupTimeIn,
    db: Session = Depends(get_db),
):
    m = db.query(Matchup).filter(Matchup.id == matchup_id).first()
    if not m:
        raise HTTPException(404, "Matchup no encontrado")

    m.starts_at = data.starts_at
    db.commit()

    return {
        "saved": True,
        "matchup_id": matchup_id,
        "starts_at": m.starts_at,
    }


@app.put(
    "/admin/matchups/{matchup_id}/result",
    dependencies=[Depends(require_admin)],
)
def admin_result(
    matchup_id: int,
    data: ResultIn,
    db: Session = Depends(get_db),
):
    winner = (
        data.winner_choice.upper().strip()
        if data.winner_choice
        else None
    )

    if winner not in {None, "A", "B"}:
        raise HTTPException(400, "winner_choice debe ser A, B o null")

    m = db.query(Matchup).filter(Matchup.id == matchup_id).first()
    if not m:
        raise HTTPException(404, "Matchup no encontrado")

    m.winner_choice = winner
    db.commit()

    return {
        "saved": True,
        "matchup_id": matchup_id,
        "winner_choice": m.winner_choice,
    }
