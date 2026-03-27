import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Flask, flash, g, jsonify, redirect, render_template, request, session, url_for

DEFAULT_DB_PATH = os.getenv("DB_PATH", "/data/babylog.db")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")
TRANSLATIONS_FILE = os.getenv("TRANSLATIONS_FILE", "translations.json")
SUPPORTED_LANGUAGES = {"nl", "en"}

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.config["DATABASE"] = DEFAULT_DB_PATH


with open(TRANSLATIONS_FILE, "r", encoding="utf-8") as handle:
    TRANSLATIONS = json.load(handle)


def get_language():
    lang = request.args.get("lang")
    if lang in SUPPORTED_LANGUAGES:
        session["lang"] = lang
        return lang
    stored = session.get("lang")
    if stored in SUPPORTED_LANGUAGES:
        return stored
    return "nl"


def t(key, lang=None):
    selected = lang or session.get("lang") or "nl"
    return TRANSLATIONS.get(selected, TRANSLATIONS["nl"]).get(key, key)


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
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_date TEXT NOT NULL,
            feed_time TEXT NOT NULL,
            amount_ml INTEGER NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS weight_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            measure_date TEXT NOT NULL,
            weight_grams INTEGER NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_entries_date_time ON entries(entry_date, feed_time, id);")
    db.execute("CREATE INDEX IF NOT EXISTS idx_weight_entries_date ON weight_entries(measure_date, id);")
    db.commit()
    db.close()


def seed_if_empty():
    db = sqlite3.connect(app.config["DATABASE"])
    db.row_factory = sqlite3.Row
    n = db.execute("SELECT COUNT(*) AS n FROM entries").fetchone()["n"]
    if not n:
        seed_days = [
            [("04:00", 120, ""), ("08:00", 50, ""), ("10:00", 100, ""), ("12:15", 130, ""), ("14:30", 30, ""), ("16:45", 100, ""), ("18:30", 90, ""), ("21:15", 100, "")],
            [("09:00", 60, "crying moment + reflux"), ("11:00", 140, ""), ("14:00", 135, ""), ("17:25", 90, ""), ("18:45", 70, ""), ("22:00", 80, ""), ("00:00", 90, "")],
            [("07:00", 90, ""), ("10:00", 130, ""), ("13:00", 120, ""), ("15:30", 60, ""), ("16:30", 50, "top-up to reach 110 total"), ("18:00", 130, ""), ("21:00", 120, "")],
            [("07:00", 130, ""), ("10:00", 90, ""), ("13:00", 90, ""), ("14:00", 70, ""), ("16:00", 20, ""), ("19:00", 120, ""), ("21:00", 80, ""), ("00:15", 110, "")],
            [("07:30", 130, ""), ("10:30", 30, ""), ("11:00", 60, ""), ("11:30", 30, ""), ("13:00", 90, ""), ("15:00", 150, ""), ("17:30", 100, ""), ("20:00", 90, ""), ("00:00", 130, "")],
            [("08:00", 80, ""), ("11:00", 90, ""), ("13:00", 110, "")],
        ]

        base_date = date.today() - timedelta(days=5)
        for i, day_entries in enumerate(seed_days):
            entry_date = (base_date + timedelta(days=i)).isoformat()
            for feed_time, amount, note in day_entries:
                db.execute(
                    "INSERT INTO entries(entry_date, feed_time, amount_ml, note) VALUES (?, ?, ?, ?)",
                    (entry_date, feed_time, amount, note),
                )

    wn = db.execute("SELECT COUNT(*) AS n FROM weight_entries").fetchone()["n"]
    if not wn:
        base_date = date.today() - timedelta(days=5)
        sample_weights = [4100, 4140, 4205, 4250, 4290, 4340]
        for i, weight in enumerate(sample_weights):
            measure_date = (base_date + timedelta(days=i)).isoformat()
            db.execute(
                "INSERT INTO weight_entries(measure_date, weight_grams, note) VALUES (?, ?, ?)",
                (measure_date, weight, ""),
            )

    db.commit()
    db.close()


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path, lang=get_language()))
        return func(*args, **kwargs)

    return wrapper


def parse_minutes(value):
    try:
        hh, mm = value.split(":")
        return int(hh) * 60 + int(mm)
    except Exception:
        return 0


def parse_user_date(user_date):
    try:
        parsed = datetime.strptime(user_date, "%d-%m").date()
        current_year = date.today().year
        return parsed.replace(year=current_year).isoformat()
    except ValueError:
        return None


def as_dd_mm(iso_date):
    parsed = datetime.strptime(iso_date, "%Y-%m-%d").date()
    return parsed.strftime("%d-%m")


def load_dashboard_data():
    db = get_db()
    rows = db.execute(
        """
        SELECT id, entry_date, feed_time, amount_ml, note
        FROM entries
        ORDER BY entry_date ASC, feed_time ASC, id ASC
        """
    ).fetchall()

    weights = db.execute(
        """
        SELECT id, measure_date, weight_grams, note
        FROM weight_entries
        ORDER BY measure_date ASC, id ASC
        """
    ).fetchall()

    by_day = {}
    all_entries = []
    for row in rows:
        iso_date = row["entry_date"]
        if iso_date not in by_day:
            by_day[iso_date] = {
                "date": iso_date,
                "label": as_dd_mm(iso_date),
                "points": [],
                "total": 0,
            }
        point = {
            "id": row["id"],
            "date": iso_date,
            "day_label": as_dd_mm(iso_date),
            "time": row["feed_time"],
            "amount": int(row["amount_ml"]),
            "note": row["note"] or "",
            "minutes": parse_minutes(row["feed_time"]),
        }
        by_day[iso_date]["points"].append(point)
        by_day[iso_date]["total"] += point["amount"]
        all_entries.append(point)

    ordered_days = sorted(by_day.values(), key=lambda d: d["date"])
    for day in ordered_days:
        day["points"] = sorted(day["points"], key=lambda p: (p["minutes"], p["id"]))

    daily_totals = [{"date": d["date"], "label": d["label"], "total": d["total"]} for d in ordered_days]

    weight_points = [
        {
            "id": row["id"],
            "date": row["measure_date"],
            "label": as_dd_mm(row["measure_date"]),
            "weight": int(row["weight_grams"]),
            "note": row["note"] or "",
        }
        for row in weights
    ]

    return {
        "days": [{"date": d["date"], "label": d["label"]} for d in ordered_days],
        "detail_by_day": ordered_days,
        "daily_totals": daily_totals,
        "entries": list(reversed(all_entries)),
        "weight_points": weight_points,
    }


@app.route("/")
def dashboard():
    lang = get_language()
    data = load_dashboard_data()
    return render_template(
        "dashboard.html",
        days=data["days"],
        daily_totals=data["daily_totals"],
        detail_by_day=data["detail_by_day"],
        entries=data["entries"],
        weight_points=data["weight_points"],
        logged_in=bool(session.get("logged_in")),
        now=datetime.now(),
        lang=lang,
        i18n=TRANSLATIONS[lang],
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    lang = get_language()
    next_url = request.args.get("next") or url_for("dashboard", lang=lang)
    if request.method == "POST":
        if request.form.get("password", "") == ADMIN_PASSWORD:
            session["logged_in"] = True
            flash(t("logged_in_success", lang), "success")
            return redirect(next_url)
        flash(t("incorrect_password", lang), "error")
    return render_template("login.html", next_url=next_url, logged_in=bool(session.get("logged_in")), lang=lang, i18n=TRANSLATIONS[lang])


@app.route("/logout", methods=["POST"])
def logout():
    lang = get_language()
    session.clear()
    session["lang"] = lang
    flash(t("logged_out", lang), "success")
    return redirect(url_for("dashboard", lang=lang))


@app.route("/add", methods=["POST"])
@login_required
def add_entry():
    lang = get_language()
    date_dd_mm = (request.form.get("entry_date") or "").strip()
    feed_time = (request.form.get("feed_time") or "").strip().replace("-", ":")
    amount_ml = request.form.get("amount_ml", type=int)
    note = (request.form.get("note") or "").strip()

    iso_date = parse_user_date(date_dd_mm)
    if not iso_date:
        flash(t("date_format_error", lang), "error")
        return redirect(url_for("dashboard", lang=lang))

    if not feed_time or len(feed_time) != 5 or ":" not in feed_time:
        flash(t("time_format_error", lang), "error")
        return redirect(url_for("dashboard", lang=lang))

    if amount_ml is None or amount_ml <= 0:
        flash(t("intake_amount_error", lang), "error")
        return redirect(url_for("dashboard", lang=lang))

    db = get_db()
    db.execute(
        "INSERT INTO entries(entry_date, feed_time, amount_ml, note) VALUES (?, ?, ?, ?)",
        (iso_date, feed_time, amount_ml, note),
    )
    db.commit()
    flash(t("intake_added", lang), "success")
    return redirect(url_for("dashboard", lang=lang))


@app.route("/add-weight", methods=["POST"])
@login_required
def add_weight():
    lang = get_language()
    date_dd_mm = (request.form.get("weight_date") or "").strip()
    weight_grams = request.form.get("weight_grams", type=int)
    note = (request.form.get("weight_note") or "").strip()

    iso_date = parse_user_date(date_dd_mm)
    if not iso_date:
        flash(t("date_format_error", lang), "error")
        return redirect(url_for("dashboard", lang=lang))

    if weight_grams is None or weight_grams <= 0:
        flash(t("weight_amount_error", lang), "error")
        return redirect(url_for("dashboard", lang=lang))

    db = get_db()
    db.execute(
        "INSERT INTO weight_entries(measure_date, weight_grams, note) VALUES (?, ?, ?)",
        (iso_date, weight_grams, note),
    )
    db.commit()
    flash(t("weight_added", lang), "success")
    return redirect(url_for("dashboard", lang=lang))


@app.route("/delete/<int:entry_id>", methods=["POST"])
@login_required
def delete_entry(entry_id):
    lang = get_language()
    db = get_db()
    db.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    db.commit()
    flash(t("entry_deleted", lang), "success")
    return redirect(url_for("dashboard", lang=lang))


@app.route("/api/data")
def api_data():
    get_language()
    return jsonify(load_dashboard_data())


if __name__ == "__main__":
    init_db()
    seed_if_empty()
    app.run(host="0.0.0.0", port=8080)
