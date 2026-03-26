import os
import sqlite3
from collections import defaultdict
from datetime import datetime
from functools import wraps

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for, flash

DEFAULT_DB_PATH = os.getenv("DB_PATH", "/data/babylog.db")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.config["DATABASE"] = DEFAULT_DB_PATH


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(app.config["DATABASE"])
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)
    db = sqlite3.connect(app.config["DATABASE"])
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS days (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL UNIQUE,
            sort_order INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_id INTEGER NOT NULL,
            feed_time TEXT NOT NULL,
            amount_ml INTEGER NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(day_id) REFERENCES days(id) ON DELETE CASCADE
        );
        """
    )
    db.commit()
    db.close()


def seed_if_empty():
    db = sqlite3.connect(app.config["DATABASE"])
    db.row_factory = sqlite3.Row
    cur = db.execute("SELECT COUNT(*) AS n FROM days")
    if cur.fetchone()["n"]:
        db.close()
        return

    seed_days = [
        ("Dag 1", [("04:00", 120, ""), ("08:00", 50, ""), ("10:00", 100, ""), ("12:15", 130, ""), ("14:30", 30, ""), ("16:45", 100, ""), ("18:30", 90, ""), ("21:15", 100, "")]),
        ("Dag 2", [("09:00", 60, "huilmoment + reflux"), ("11:00", 140, ""), ("14:00", 135, ""), ("17:25", 90, ""), ("18:45", 70, ""), ("22:00", 80, ""), ("00:00", 90, "")]),
        ("Dag 3", [("07:00", 90, ""), ("10:00", 130, ""), ("13:00", 120, ""), ("15:30", 60, ""), ("16:30", 50, "extra om op 110 te komen"), ("18:00", 130, ""), ("21:00", 120, "")]),
        ("Dag 4", [("07:00", 130, ""), ("10:00", 90, ""), ("13:00", 90, ""), ("14:00", 70, ""), ("16:00", 20, ""), ("19:00", 120, ""), ("21:00", 80, ""), ("00:15", 110, "")]),
        ("Dag 5", [("07:30", 130, ""), ("10:30", 30, ""), ("11:00", 60, ""), ("11:30", 30, ""), ("13:00", 90, ""), ("15:00", 150, ""), ("17:30", 100, ""), ("20:00", 90, ""), ("00:00", 130, "")]),
        ("Dag 6", [("08:00", 80, "tot nu toe"), ("11:00", 90, ""), ("13:00", 110, "")]),
    ]

    for idx, (label, entries) in enumerate(seed_days, start=1):
        cur = db.execute("INSERT INTO days (label, sort_order) VALUES (?, ?)", (label, idx))
        day_id = cur.lastrowid
        for t, amount, note in entries:
            db.execute(
                "INSERT INTO entries (day_id, feed_time, amount_ml, note) VALUES (?, ?, ?, ?)",
                (day_id, t, amount, note),
            )
    db.commit()
    db.close()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def parse_minutes(t):
    try:
        hh, mm = t.split(":")
        return int(hh) * 60 + int(mm)
    except Exception:
        return 0


def load_dashboard_data():
    db = get_db()
    days = db.execute("SELECT * FROM days ORDER BY sort_order, id").fetchall()
    entries = db.execute(
        """
        SELECT e.*, d.label AS day_label
        FROM entries e
        JOIN days d ON d.id = e.day_id
        ORDER BY d.sort_order, e.feed_time, e.id
        """
    ).fetchall()

    totals = defaultdict(int)
    day_entries = defaultdict(list)

    for e in entries:
        totals[e["day_id"]] += int(e["amount_ml"])
        day_entries[e["day_id"]].append(
            {
                "id": e["id"],
                "time": e["feed_time"],
                "amount": int(e["amount_ml"]),
                "note": e["note"] or "",
                "minutes": parse_minutes(e["feed_time"]),
                "day_label": e["day_label"],
            }
        )

    daily_totals = [
        {"day_id": d["id"], "label": d["label"], "total": totals.get(d["id"], 0)}
        for d in days
    ]

    detail_by_day = [
        {
            "day_id": d["id"],
            "label": d["label"],
            "points": sorted(day_entries.get(d["id"], []), key=lambda x: (x["minutes"], x["id"])),
            "total": totals.get(d["id"], 0),
        }
        for d in days
    ]

    return {"days": [{"id": d["id"], "label": d["label"], "sort_order": d["sort_order"]} for d in days],
            "daily_totals": daily_totals, "detail_by_day": detail_by_day, "entries": entries}


@app.route("/")
def dashboard():
    data = load_dashboard_data()
    selected_day_id = request.args.get("day", type=int)
    if not selected_day_id and data["days"]:
        selected_day_id = data["days"][-1]["id"]
    return render_template(
        "dashboard.html",
        days=data["days"],
        daily_totals=data["daily_totals"],
        detail_by_day=data["detail_by_day"],
        entries=data["entries"],
        selected_day_id=selected_day_id,
        logged_in=bool(session.get("logged_in")),
        now=datetime.now(),
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next") or url_for("dashboard")
    if request.method == "POST":
        if request.form.get("password", "") == ADMIN_PASSWORD:
            session["logged_in"] = True
            flash("Ingelogd.", "success")
            return redirect(next_url)
        flash("Onjuiste wachtwoord.", "error")
    return render_template("login.html", next_url=next_url, logged_in=bool(session.get("logged_in")))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Uitgelogd.", "success")
    return redirect(url_for("dashboard"))


@app.route("/add", methods=["POST"])
@login_required
def add_entry():
    day_label = (request.form.get("day_label") or "").strip()
    feed_time = (request.form.get("feed_time") or "").strip()
    amount_ml = request.form.get("amount_ml", type=int)
    note = (request.form.get("note") or "").strip()

    if not day_label or not feed_time or amount_ml is None or amount_ml <= 0:
        flash("Dag, tijd en hoeveelheid zijn verplicht.", "error")
        return redirect(url_for("dashboard"))

    db = get_db()
    day = db.execute("SELECT * FROM days WHERE label = ?", (day_label,)).fetchone()
    if day is None:
        max_order = db.execute("SELECT COALESCE(MAX(sort_order), 0) AS m FROM days").fetchone()["m"]
        cur = db.execute("INSERT INTO days (label, sort_order) VALUES (?, ?)", (day_label, max_order + 1))
        day_id = cur.lastrowid
    else:
        day_id = day["id"]

    db.execute(
        "INSERT INTO entries (day_id, feed_time, amount_ml, note) VALUES (?, ?, ?, ?)",
        (day_id, feed_time, amount_ml, note),
    )
    db.commit()
    flash("Inname toegevoegd.", "success")
    return redirect(url_for("dashboard", day=day_id))


@app.route("/delete/<int:entry_id>", methods=["POST"])
@login_required
def delete_entry(entry_id):
    db = get_db()
    db.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    db.commit()
    flash("Inname verwijderd.", "success")
    return redirect(url_for("dashboard"))


@app.route("/api/data")
def api_data():
    return jsonify(load_dashboard_data())


if __name__ == "__main__":
    init_db()
    seed_if_empty()
    app.run(host="0.0.0.0", port=8000, debug=True)
