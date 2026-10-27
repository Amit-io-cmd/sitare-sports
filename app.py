import os, sqlite3, json
from datetime import datetime, timedelta
from functools import wraps
from flask import (Flask, g, render_template, request, redirect, url_for,
                   session, flash, jsonify, abort)
from werkzeug.security import generate_password_hash, check_password_hash

# Automatically load .env if present
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
DATABASE_URL = os.environ.get("DATABASE_URL")
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sports.db")
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
DOMAIN = "@sitare.org"

COORDINATORS = [e.strip().lower() for e in os.environ.get("COORDINATORS", "sports@sitare.org").split(",")]
ADMIN_EMAILS = [e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "admin@sitare.org").split(",")]
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
COORDINATOR_KEY = os.environ.get("COORDINATOR_KEY", "Mission")
ADMIN_KEY = os.environ.get("ADMIN_KEY", "Admin2026")
SPORTS = ["Football", "Cricket", "Badminton", "Volleyball", "Athletics", "Basketball", "Table Tennis"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'student', pw TEXT NOT NULL, override INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS equipment(
  id INTEGER PRIMARY KEY, sku TEXT UNIQUE, name TEXT NOT NULL, sport TEXT NOT NULL,
  brand TEXT DEFAULT '', rack TEXT DEFAULT '', grade TEXT NOT NULL DEFAULT 'A',
  status TEXT NOT NULL DEFAULT 'available');
CREATE TABLE IF NOT EXISTS loans(
  id INTEGER PRIMARY KEY, equipment_id INTEGER NOT NULL REFERENCES equipment(id),
  lead_id INTEGER NOT NULL REFERENCES users(id), status TEXT NOT NULL DEFAULT 'requested',
  hours INTEGER NOT NULL DEFAULT 4, requested_at TEXT, issued_at TEXT, due_at TEXT, returned_at TEXT,
  issue_grade TEXT, issue_notes TEXT DEFAULT '', return_grade TEXT, return_notes TEXT DEFAULT '',
  fine REAL NOT NULL DEFAULT 0, issue_photo TEXT DEFAULT '', return_photo TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS loan_members(
  id INTEGER PRIMARY KEY, loan_id INTEGER NOT NULL REFERENCES loans(id),
  user_id INTEGER NOT NULL REFERENCES users(id), share REAL NOT NULL DEFAULT 0, paid INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS audit_logs(
  id INTEGER PRIMARY KEY, user_id INTEGER, user_name TEXT, action TEXT NOT NULL,
  details TEXT DEFAULT '', timestamp TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notifications(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
  title TEXT NOT NULL, message TEXT NOT NULL, type TEXT NOT NULL DEFAULT 'info',
  read INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
"""
SEED = [("Football (Size 5)", "Football", "Nivia", "Rack A1", 3), ("Cricket Bat", "Cricket", "SG", "Rack B2", 2),
        ("Badminton Racquet", "Badminton", "Yonex", "Rack C1", 4), ("Volleyball", "Volleyball", "Cosco", "Rack A3", 2),
        ("Basketball (Size 7)", "Basketball", "Spalding", "Rack A2", 2), ("Relay Baton Set", "Athletics", "Generic", "Rack D1", 1)]


def save_photo(file_obj, base64_str, prefix):
    if file_obj and file_obj.filename:
        ext = os.path.splitext(file_obj.filename)[1].lower() or ".jpg"
        filename = f"{prefix}_{int(datetime.now().timestamp())}{ext}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file_obj.save(filepath)
        return f"/static/uploads/{filename}"
    return ""


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def fmt_datetime(val):
    if not val:
        return ""
    try:
        val_str = str(val).strip()
        parts = val_str.split(" ")
        if len(parts) >= 2 and "-" in parts[0]:
            y, m, d = parts[0].split("-")
            dt_obj = datetime(int(y), int(m), int(d))
            date_fmt = dt_obj.strftime("%d %b %Y")
            time_fmt = parts[1][:5]
            return f"{date_fmt}<br>{time_fmt}"
    except Exception:
        pass
    return str(val)


app.jinja_env.filters['fmt_dt'] = fmt_datetime


def db():
    if "db" not in g:
        if DATABASE_URL:
            import psycopg2
            from psycopg2.extras import DictCursor
            g.db = psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)
        else:
            g.db = sqlite3.connect(DB)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d:
        d.close()


def q(sql, *a, one=False):
    conn = db()
    if DATABASE_URL:
        pg_sql = sql.replace("?", "%s")
        with conn.cursor() as cur:
            cur.execute(pg_sql, a)
            r = cur.fetchall()
            return (r[0] if r else None) if one else r
    else:
        r = conn.execute(sql, a).fetchall()
        return (r[0] if r else None) if one else r


def run(sql, *a):
    conn = db()
    if DATABASE_URL:
        pg_sql = sql.replace("?", "%s")
        with conn.cursor() as cur:
            trimmed = pg_sql.strip()
            if trimmed.upper().startswith("INSERT INTO") and "RETURNING" not in trimmed.upper():
                trimmed = trimmed.rstrip(";") + " RETURNING id"
                cur.execute(trimmed, a)
                row = cur.fetchone()
                conn.commit()
                return row["id"] if (row and "id" in row) else (row[0] if row else None)
            else:
                cur.execute(pg_sql, a)
                conn.commit()
                return cur.rowcount
    else:
        c = conn.execute(sql, a)
        conn.commit()
        return c.lastrowid


def log_audit(action, details=""):
    u = me()
    uid = u["id"] if u else 0
    uname = u["name"] if u else "System"
    run("INSERT INTO audit_logs(user_id, user_name, action, details, timestamp) VALUES(?,?,?,?,?)",
        uid, uname, action, details, now())


def send_notification(user_id, title, message, type_str="info"):
    run("INSERT INTO notifications(user_id, title, message, type, created_at) VALUES(?,?,?,?,?)",
        user_id, title, message, type_str, now())


def notify_coordinators(title, message, type_str="info"):
    coords = q("SELECT id FROM users WHERE role IN ('coordinator', 'admin')")
    for c in coords:
        send_notification(c["id"], title, message, type_str)


def check_overdue_alerts():
    overdue_loans = loans_where("l.status='issued' AND l.due_at<?", now())
    for l in overdue_loans:
        ms = q("SELECT user_id FROM loan_members WHERE loan_id=?", l["id"])
        for m in ms:
            if not q("SELECT 1 FROM notifications WHERE user_id=? AND title LIKE ? AND created_at>? LIMIT 1",
                     m["user_id"], f"%Overdue: {l['ename']}%", (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"), one=True):
                send_notification(m["user_id"], f"⚠️ Overdue: {l['ename']}",
                                  f"Loan #REQ-{l['id']:04d} ({l['ename']}) is overdue. Please return it to the sports desk.", "error")


def add_units(name, sport, brand, rack, grade, qty):
    for _ in range(qty):
        eid = run("INSERT INTO equipment(name,sport,brand,rack,grade) VALUES(?,?,?,?,?)", name, sport, brand, rack, grade)
        run("UPDATE equipment SET sku=? WHERE id=?", f"{sport[:3].upper()}-{eid:04d}", eid)


def init_db():
    with app.app_context():
        if not DATABASE_URL:
            db().executescript(SCHEMA)

            # Ensure photos columns exist if older schema
            try:
                db().execute("ALTER TABLE loans ADD COLUMN issue_photo TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            try:
                db().execute("ALTER TABLE loans ADD COLUMN return_photo TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass

        # Seed Admins
        for a_email in ADMIN_EMAILS:
            u = q("SELECT * FROM users WHERE email=?", a_email, one=True)
            if not u:
                run("INSERT INTO users(email,name,role,pw) VALUES(?,?,?,?)",
                    a_email, "System Admin", "admin", generate_password_hash(ADMIN_PASSWORD))
            elif u["role"] != "admin":
                run("UPDATE users SET role='admin' WHERE id=?", u["id"])

        # Seed Coordinators
        for c_email in COORDINATORS:
            if c_email in ADMIN_EMAILS:
                continue
            u = q("SELECT * FROM users WHERE email=?", c_email, one=True)
            if not u:
                run("INSERT INTO users(email,name,role,pw) VALUES(?,?,?,?)",
                    c_email, "Sports Desk Coord", "coordinator", generate_password_hash("coord123"))

        # Seed initial equipment stock
        if not q("SELECT 1 FROM equipment LIMIT 1", one=True):
            for n, s, b, r, qty in SEED:
                add_units(n, s, b, r, "A", qty)


def me():
    return q("SELECT * FROM users WHERE id=?", session["uid"], one=True) if "uid" in session else None


def login_required(role=None):
    def deco(f):
        @wraps(f)
        def wrap(*a, **k):
            u = me()
            if not u:
                return redirect(url_for("login"))
            if role:
                if role == "coordinator" and u["role"] not in ("coordinator", "admin"):
                    abort(403)
                elif role == "admin" and u["role"] != "admin":
                    abort(403)
                elif role == "student" and u["role"] not in ("student", "coordinator", "admin"):
                    abort(403)
            return f(*a, **k)
        return wrap
    return deco


def standing(uid):
    """Return a suspension reason, or None if the student is in good standing."""
    if q("SELECT override FROM users WHERE id=?", uid, one=True)["override"]:
        return None
    if q("""SELECT 1 FROM loans l JOIN loan_members m ON m.loan_id=l.id
            WHERE m.user_id=? AND l.status='issued' AND l.due_at<? LIMIT 1""", uid, now(), one=True):
        return "Overdue equipment"
    dues = q("SELECT COALESCE(SUM(share),0) s FROM loan_members WHERE user_id=? AND paid=0", uid, one=True)["s"]
    return f"Unpaid damage/late dues of ₹{dues:.2f}" if dues > 0 else None


def loans_where(where, *a):
    rows = q(f"""SELECT l.*, e.name ename, e.sku, e.sport, u.name lead_name FROM loans l
                 JOIN equipment e ON e.id=l.equipment_id JOIN users u ON u.id=l.lead_id
                 WHERE {where} ORDER BY l.id DESC""", *a)
    out = []
    for r in rows:
        d = dict(r)
        d["members"] = q("""SELECT m.*, u.name, u.email FROM loan_members m JOIN users u ON u.id=m.user_id
                            WHERE m.loan_id=?""", r["id"])
        d["overdue"] = r["status"] == "issued" and r["due_at"] < now()
        out.append(d)
    return out


# ---------- auth ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        role_type = request.form.get("role_type", "student")
        coord_key = request.form.get("coordinator_key", "").strip()
        admin_key = request.form.get("admin_key", "").strip()

        if not email.endswith(DOMAIN) or len(email) <= len(DOMAIN):
            flash("Only @sitare.org accounts can sign in.", "error")
            return redirect(url_for("login"))

        u = q("SELECT * FROM users WHERE email=?", email, one=True)

        if role_type == "admin":
            if admin_key != ADMIN_KEY:
                flash("Invalid Admin Security Key! Access denied to Admin portal.", "error")
                return redirect(url_for("login"))
        elif role_type == "coordinator" or (u and u["role"] == "coordinator"):
            if coord_key != COORDINATOR_KEY:
                flash("Invalid Coordinator Security Key! Access denied to coordinator portal.", "error")
                return redirect(url_for("login"))

        if u is None:  # first valid login auto-creates account
            if len(pw) < 6:
                flash("Choose a password of at least 6 characters.", "error")
                return redirect(url_for("login"))
            name = email.split("@")[0].replace(".", " ").replace("_", " ").title()
            if role_type == "admin" or email in ADMIN_EMAILS:
                role = "admin"
            elif role_type == "coordinator" or email in COORDINATORS:
                role = "coordinator"
            else:
                role = "student"
            run("INSERT INTO users(email,name,role,pw) VALUES(?,?,?,?)", email, name, role, generate_password_hash(pw))
            u = q("SELECT * FROM users WHERE email=?", email, one=True)
        else:
            if not check_password_hash(u["pw"], pw):
                flash("Incorrect password.", "error")
                return redirect(url_for("login"))
            if role_type == "admin" and u["role"] != "admin":
                run("UPDATE users SET role='admin' WHERE id=?", u["id"])
                u = q("SELECT * FROM users WHERE email=?", email, one=True)
            elif role_type == "coordinator" and u["role"] == "student":
                run("UPDATE users SET role='coordinator' WHERE id=?", u["id"])
                u = q("SELECT * FROM users WHERE email=?", email, one=True)

        session["uid"] = u["id"]
        log_audit("LOGIN", f"Signed in as {u['role'].upper()}")
        return redirect(url_for("home"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    if "uid" in session:
        log_audit("LOGOUT", "Signed out")
    session.clear()
    return redirect(url_for("login"))


# ---------- dashboards ----------
@app.route("/")
@login_required()
def home():
    u = me()
    common = dict(user=u, sports=SPORTS, out=loans_where("l.status='issued'"), now=now())

    if u["role"] in ("coordinator", "admin"):
        dues = q("""SELECT m.id, m.share, u.name, u.email, e.name ename, l.id lid FROM loan_members m
                    JOIN users u ON u.id=m.user_id JOIN loans l ON l.id=m.loan_id
                    JOIN equipment e ON e.id=l.equipment_id WHERE m.paid=0 AND m.share>0""")
        flagged = []
        for s in q("SELECT * FROM users WHERE role='student'"):
            r = standing(s["id"])
            if r:
                flagged.append(dict(s, reason=r))

        admin_data = {}
        if u["role"] == "admin":
            all_users = q("SELECT * FROM users ORDER BY id DESC")
            audit_logs = q("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 150")

            total_fines_assessed = q("SELECT COALESCE(SUM(fine), 0) s FROM loans", one=True)["s"]
            total_fines_collected = q("SELECT COALESCE(SUM(share), 0) s FROM loan_members WHERE paid=1", one=True)["s"]
            total_unpaid_dues = q("SELECT COALESCE(SUM(share), 0) s FROM loan_members WHERE paid=0 AND share>0", one=True)["s"]

            user_counts = {
                "total": len(all_users),
                "students": sum(1 for usr in all_users if usr["role"] == "student"),
                "coordinators": sum(1 for usr in all_users if usr["role"] == "coordinator"),
                "admins": sum(1 for usr in all_users if usr["role"] == "admin")
            }

            equipment_stats = {
                "total": q("SELECT COUNT(*) c FROM equipment", one=True)["c"],
                "available": q("SELECT COUNT(*) c FROM equipment WHERE status='available'", one=True)["c"],
                "issued": q("SELECT COUNT(*) c FROM equipment WHERE status='issued'", one=True)["c"],
                "maintenance": q("SELECT COUNT(*) c FROM equipment WHERE status='maintenance'", one=True)["c"],
                "condemned": q("SELECT COUNT(*) c FROM equipment WHERE status='condemned'", one=True)["c"]
            }

            admin_data = dict(
                all_users=all_users,
                audit_logs=audit_logs,
                total_fines_assessed=total_fines_assessed,
                total_fines_collected=total_fines_collected,
                total_unpaid_dues=total_unpaid_dues,
                user_counts=user_counts,
                equipment_stats=equipment_stats,
                coord_key=COORDINATOR_KEY,
                admin_key=ADMIN_KEY
            )

        return render_template("coord.html", pending=loans_where("l.status='requested'"), dues=dues,
                               flagged=flagged, **admin_data, **common)

    mine = loans_where("l.id IN (SELECT loan_id FROM loan_members WHERE user_id=?)", u["id"])
    return render_template("student.html", mine=mine, suspended=standing(u["id"]), **common)


@app.route("/api/equipment")
@login_required()
def api_equipment():
    term, sport = request.args.get("q", "").strip().lower(), request.args.get("sport", "")
    stats = {s: q("SELECT COUNT(*) c FROM equipment WHERE status=?", s, one=True)["c"]
             for s in ("available", "issued", "maintenance")}
    stats["total"] = q("SELECT COUNT(*) c FROM equipment WHERE status!='condemned'", one=True)["c"]
    rows = q("""SELECT e.*, (SELECT due_at FROM loans WHERE equipment_id=e.id AND status='issued') due_at,
                (SELECT 1 FROM loans WHERE equipment_id=e.id AND status='requested' LIMIT 1) reserved
                FROM equipment e WHERE (?='' OR sport=?) AND (lower(name) LIKE ? OR lower(sport) LIKE ?
                OR lower(sku) LIKE ? OR lower(brand) LIKE ?) ORDER BY sport, name, id""",
             sport, sport, *([f"%{term}%"] * 4))
    return jsonify(stats=stats, items=[dict(r) for r in rows])


@app.route("/api/notifications")
@login_required()
def api_notifications():
    u = me()
    check_overdue_alerts()
    unread_count = q("SELECT COUNT(*) c FROM notifications WHERE user_id=? AND read=0", u["id"], one=True)["c"]
    logs = q("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 25", u["id"])
    return jsonify(unread=unread_count, items=[dict(r) for r in logs])


@app.post("/api/notifications/read")
@login_required()
def api_notifications_read():
    u = me()
    run("UPDATE notifications SET read=1 WHERE user_id=?", u["id"])
    return jsonify(ok=True)


@app.route("/api/scan/<path:code>")
@login_required()
def api_scan(code):
    code_clean = code.strip()
    
    # Check if request ID e.g., REQ-0001 or 1
    req_match = None
    if code_clean.upper().startswith("REQ-"):
        try:
            lid = int(code_clean.upper().replace("REQ-", ""))
            req_match = q("SELECT l.*, e.name ename, e.sku FROM loans l JOIN equipment e ON e.id=l.equipment_id WHERE l.id=?", lid, one=True)
        except Exception:
            pass
    elif code_clean.isdigit():
        req_match = q("SELECT l.*, e.name ename, e.sku FROM loans l JOIN equipment e ON e.id=l.equipment_id WHERE l.id=?", int(code_clean), one=True)
        
    if req_match:
        return jsonify(type="loan", data=dict(req_match))
        
    # Check if equipment SKU or name or ID
    eq = q("SELECT * FROM equipment WHERE sku=? OR lower(name)=? OR id=?",
           code_clean.upper(), code_clean.lower(), code_clean, one=True)
    if eq:
        active_loan = q("SELECT l.*, u.name lead_name FROM loans l JOIN users u ON u.id=l.lead_id WHERE equipment_id=? AND status IN ('requested', 'issued') ORDER BY id DESC LIMIT 1", eq["id"], one=True)
        return jsonify(type="equipment", data=dict(eq), active_loan=dict(active_loan) if active_loan else None)
        
    return jsonify(type="none", error=f"No matching item or request found for '{code_clean}'.")


# ---------- student: group request ----------
@app.post("/request")
@login_required("student")
def request_loan():
    u, f = me(), request.form
    eid, hours = f.get("equipment_id", type=int), min(max(f.get("hours", 4, type=int), 1), 72)
    lead_email = u["email"].strip().lower()
    co_emails = []
    for e in f.getlist("co"):
        e_clean = e.strip().lower()
        if e_clean and e_clean != lead_email and e_clean not in co_emails:
            co_emails.append(e_clean)
    emails = [lead_email] + co_emails

    def fail(msg):
        flash(msg, "error")
        return redirect(url_for("home"))

    if not 1 <= len(emails) <= 4:
        return fail("A borrowing group can have 1 to 4 students.")
    members = []
    for e in emails:
        if not e.endswith(DOMAIN):
            return fail(f"{e} is not a valid @sitare.org address.")
        s = q("SELECT * FROM users WHERE email=?", e, one=True)
        if not s:
            name = e.split("@")[0].replace(".", " ").replace("_", " ").title()
            sid = run("INSERT INTO users(email,name,role,pw) VALUES(?,?,?,?)", e, name, "student", generate_password_hash("sitare123"))
            s = q("SELECT * FROM users WHERE id=?", sid, one=True)
        if s["role"] not in ("student", "coordinator", "admin"):
            return fail(f"{e} is invalid.")
        if standing(s["id"]):
            return fail(f"{s['name']} is suspended: {standing(s['id'])}.")
        members.append(s["id"])
    eq = q("SELECT * FROM equipment WHERE id=?", eid, one=True)
    if not eq or eq["status"] != "available":
        return fail("That item is no longer available.")
    if q("SELECT 1 FROM loans WHERE equipment_id=? AND status='requested'", eid, one=True):
        return fail("Another group has already requested this item.")
    lid = run("INSERT INTO loans(equipment_id,lead_id,hours,requested_at) VALUES(?,?,?,?)", eid, u["id"], hours, now())
    for m in members:
        run("INSERT INTO loan_members(loan_id,user_id) VALUES(?,?)", lid, m)
    log_audit("REQUEST_LOAN", f"Loan #REQ-{lid:04d} requested for {eq['name']} ({eq['sku']}) for {hours}h")
    notify_coordinators("📥 New Loan Request", f"{u['name']} requested {eq['name']} (SKU: {eq['sku']}) for {hours}h")
    flash(f"Request sent for {eq['name']}. Collect it at the sports desk.", "ok")
    return redirect(url_for("home"))


# ---------- coordinator: issue / return ----------
@app.post("/coord/issue/<int:lid>")
@login_required("coordinator")
def issue(lid):
    l = q("SELECT * FROM loans WHERE id=? AND status='requested'", lid, one=True) or abort(404)
    grade = request.form.get("grade", "A")
    if grade not in ("A", "B"):
        abort(400)
    if q("SELECT status FROM equipment WHERE id=?", l["equipment_id"], one=True)["status"] != "available":
        flash("Item is not on the shelf.", "error")
        return redirect(url_for("home"))
    due = (datetime.now() + timedelta(hours=l["hours"])).strftime("%Y-%m-%d %H:%M")
    photo_path = save_photo(request.files.get("photo"), request.form.get("photo_base64"), f"issue_{lid}")
    run("UPDATE loans SET status='issued',issued_at=?,due_at=?,issue_grade=?,issue_notes=?,issue_photo=? WHERE id=?",
        now(), due, grade, request.form.get("notes", ""), photo_path, lid)
    run("UPDATE equipment SET status='issued', grade=? WHERE id=?", grade, l["equipment_id"])
    run("UPDATE users SET override=0 WHERE id IN (SELECT user_id FROM loan_members WHERE loan_id=?)", lid)
    log_audit("ISSUE_LOAN", f"Issued Loan #REQ-{lid:04d} with condition Grade {grade}")
    ms = q("SELECT user_id FROM loan_members WHERE loan_id=?", lid)
    for m in ms:
        send_notification(m["user_id"], "⚽ Equipment Issued", f"Your group issued {l['ename']} ({l['sku']}). Due back {due}.", "info")
    flash(f"Issued. Due back {due}.", "ok")
    return redirect(url_for("home"))


@app.post("/coord/reject/<int:lid>")
@login_required("coordinator")
def reject(lid):
    run("UPDATE loans SET status='rejected' WHERE id=? AND status='requested'", lid)
    log_audit("REJECT_LOAN", f"Rejected Loan #REQ-{lid:04d}")
    return redirect(url_for("home"))


@app.post("/coord/return/<int:lid>")
@login_required("coordinator")
def process_return(lid):
    l = q("SELECT * FROM loans WHERE id=? AND status='issued'", lid, one=True) or abort(404)
    grade = request.form.get("grade", "A")
    if grade not in "ABCD" or len(grade) != 1:
        abort(400)
    fine = max(request.form.get("fine", 0, type=float), 0)
    photo_path = save_photo(request.files.get("photo"), request.form.get("photo_base64"), f"return_{lid}")
    run("UPDATE loans SET status='returned',returned_at=?,return_grade=?,return_notes=?,fine=?,return_photo=? WHERE id=?",
        now(), grade, request.form.get("notes", ""), fine, photo_path, lid)
    status = {"A": "available", "B": "available", "C": "maintenance", "D": "condemned"}[grade]
    run("UPDATE equipment SET status=?, grade=? WHERE id=?", status, grade, l["equipment_id"])
    ms = q("SELECT id FROM loan_members WHERE loan_id=?", lid)
    share = round(fine / len(ms), 2)  # equal split across every group member
    for m in ms:
        run("UPDATE loan_members SET share=?, paid=? WHERE id=?", share, 0 if share > 0 else 1, m["id"])
        send_notification(m["user_id"], "✅ Equipment Returned", f"{l['ename']} returned." + (f" Fine: ₹{share:.2f}" if share > 0 else " No fine."), "ok")
    log_audit("RETURN_LOAN", f"Returned Loan #REQ-{lid:04d} Grade {grade}, Fine ₹{fine:.2f}")
    flash(f"Return logged. {'Fine of ₹%.2f split %d ways (₹%.2f each).' % (fine, len(ms), share) if fine else 'No fine.'}", "ok")
    return redirect(url_for("home"))


@app.post("/coord/pay/<int:mid>")
@login_required("coordinator")
def pay(mid):
    run("UPDATE loan_members SET paid=1 WHERE id=?", mid)
    log_audit("DUE_PAID", f"Marked share paid for member ID #{mid}")
    return redirect(url_for("home"))


@app.post("/coord/reinstate/<int:uid>")
@login_required("coordinator")
def reinstate(uid):
    run("UPDATE loan_members SET paid=1 WHERE user_id=?", uid)
    run("UPDATE users SET override=1 WHERE id=?", uid)
    log_audit("REINSTATE_STUDENT", f"Reinstated student User #{uid}")
    flash("Student reinstated. Dues cleared.", "ok")
    return redirect(url_for("home"))


# ---------- coordinator: inventory ----------
@app.post("/coord/equipment")
@login_required("coordinator")
def equipment_save():
    f = request.form
    eid, name = f.get("id", type=int), f.get("name", "").strip()
    if not name or f.get("sport") not in SPORTS or f.get("grade") not in list("ABCD"):
        flash("Name, sport and condition are required.", "error")
        return redirect(url_for("home"))
    if eid:
        cur = q("SELECT status FROM equipment WHERE id=?", eid, one=True) or abort(404)
        status = "issued" if cur["status"] == "issued" else f.get("status", "available")
        run("UPDATE equipment SET name=?,sport=?,brand=?,rack=?,grade=?,status=? WHERE id=?",
            name, f["sport"], f.get("brand", ""), f.get("rack", ""), f["grade"], status, eid)
        log_audit("UPDATE_EQUIPMENT", f"Updated equipment ID #{eid} ({name})")
    else:
        qty = min(max(f.get("qty", 1, type=int), 1), 50)
        add_units(name, f["sport"], f.get("brand", ""), f.get("rack", ""), f["grade"], qty)
        log_audit("ADD_EQUIPMENT", f"Added {qty} units of '{name}' ({f.get('sport')})")
    flash("Inventory updated.", "ok")
    return redirect(url_for("home"))


@app.route("/coord/history/<int:eid>")
@login_required("coordinator")
def history(eid):
    ls = loans_where("l.equipment_id=?", eid)
    return jsonify([{"id": l["id"], "status": l["status"], "issued_at": l["issued_at"], "returned_at": l["returned_at"],
                     "issue_grade": l["issue_grade"], "return_grade": l["return_grade"], "notes": l["return_notes"],
                     "fine": l["fine"], "group": ", ".join(m["name"] for m in l["members"])} for l in ls])


@app.route("/coord/label/<int:eid>")
@login_required("coordinator")
def label(eid):
    return render_template("label.html", e=q("SELECT * FROM equipment WHERE id=?", eid, one=True) or abort(404))


# ---------- Admin Management Routes ----------
@app.post("/admin/user/role")
@login_required("admin")
def admin_change_role():
    uid = request.form.get("user_id", type=int)
    new_role = request.form.get("role", "")
    if new_role not in ("student", "coordinator", "admin"):
        flash("Invalid role specified.", "error")
        return redirect(url_for("home"))
    target = q("SELECT * FROM users WHERE id=?", uid, one=True)
    if not target:
        abort(404)
    if target["id"] == me()["id"] and new_role != "admin":
        flash("You cannot demote yourself from Admin role.", "error")
        return redirect(url_for("home"))
    run("UPDATE users SET role=? WHERE id=?", new_role, uid)
    log_audit("ROLE_CHANGED", f"Changed role of user #{uid} ({target['email']}) from {target['role']} to {new_role}")
    flash(f"User {target['name']} is now a {new_role}.", "ok")
    return redirect(url_for("home"))


@app.post("/admin/user/password")
@login_required("admin")
def admin_reset_password():
    uid = request.form.get("user_id", type=int)
    new_pw = request.form.get("new_password", "").strip()
    if len(new_pw) < 6:
        flash("Password must be at least 6 characters.", "error")
        return redirect(url_for("home"))
    target = q("SELECT * FROM users WHERE id=?", uid, one=True)
    if not target:
        abort(404)
    run("UPDATE users SET pw=? WHERE id=?", generate_password_hash(new_pw), uid)
    log_audit("PASSWORD_RESET", f"Reset password for user #{uid} ({target['email']})")
    flash(f"Password reset for {target['name']}.", "ok")
    return redirect(url_for("home"))


@app.post("/admin/user/create")
@login_required("admin")
def admin_create_user():
    email = request.form.get("email", "").strip().lower()
    name = request.form.get("name", "").strip()
    role = request.form.get("role", "coordinator")
    pw = request.form.get("password", "").strip()
    if not email.endswith(DOMAIN):
        flash(f"Email must end with {DOMAIN}.", "error")
        return redirect(url_for("home"))
    if not name or len(pw) < 6 or role not in ("student", "coordinator", "admin"):
        flash("All fields are required. Password min 6 characters.", "error")
        return redirect(url_for("home"))
    if q("SELECT 1 FROM users WHERE email=?", email, one=True):
        flash("A user with this email already exists.", "error")
        return redirect(url_for("home"))
    uid = run("INSERT INTO users(email,name,role,pw) VALUES(?,?,?,?)", email, name, role, generate_password_hash(pw))
    log_audit("USER_CREATED", f"Created user #{uid} ({email}) with role '{role}'")
    flash(f"Created {role} account for {name} ({email}).", "ok")
    return redirect(url_for("home"))


@app.post("/admin/config/keys")
@login_required("admin")
def admin_update_keys():
    global COORDINATOR_KEY, ADMIN_KEY
    new_ckey = request.form.get("coordinator_key", "").strip()
    new_akey = request.form.get("admin_key", "").strip()
    if new_ckey:
        COORDINATOR_KEY = new_ckey
    if new_akey:
        ADMIN_KEY = new_akey
    log_audit("CONFIG_UPDATED", "Updated Security Keys.")
    flash("Security keys updated.", "ok")
    return redirect(url_for("home"))


init_db()
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "True").lower() in ("true", "1")
    app.run(host="0.0.0.0", port=port, debug=debug)
