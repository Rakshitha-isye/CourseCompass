from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from database import init_db, seed_demo_data, seed_course_resources, get_db
from recommender import recommend_courses, get_popular_courses, get_recommendation_reason

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key-before-deployment"

init_db()
seed_demo_data()
seed_course_resources()

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "info")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

@app.route("/")
def index():
    db = get_db()
    courses = db.execute("SELECT * FROM courses ORDER BY rating DESC LIMIT 6").fetchall()
    return render_template("index.html", courses=courses)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 6:
            flash("Enter your name, a valid email, and a password with at least 6 characters.", "error")
            return render_template("register.html")
        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (name, email, password_hash, interests) VALUES (?, ?, ?, ?)",
                (name, email, generate_password_hash(password), "")
            )
            db.commit()
        except Exception:
            flash("That email may already be registered. Try logging in.", "error")
            return render_template("register.html")
        user = db.execute("SELECT id, name FROM users WHERE email = ?", (email,)).fetchone()
        session["user_id"], session["user_name"] = user["id"], user["name"]
        flash("Account created successfully!", "success")
        return redirect(url_for("dashboard"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"], session["user_name"] = user["id"], user["name"]
            return redirect(url_for("dashboard"))
        flash("Incorrect email or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    user_id = session["user_id"]
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    recommendations = recommend_courses(user_id, limit=6)
    popular = get_popular_courses(limit=4)
    rated = db.execute("""
        SELECT c.*, r.rating AS user_rating
        FROM ratings r JOIN courses c ON c.id = r.course_id
        WHERE r.user_id = ? ORDER BY r.created_at DESC
    """, (user_id,)).fetchall()
    return render_template("dashboard.html", user=user, recommendations=recommendations,
                           popular=popular, rated=rated)

@app.route("/courses")
def courses():
    db = get_db()
    category = request.args.get("category", "").strip()
    search = request.args.get("q", "").strip()
    sql, params = "SELECT * FROM courses WHERE 1=1", []
    if category:
        sql += " AND category = ?"
        params.append(category)
    if search:
        sql += " AND (title LIKE ? OR description LIKE ? OR tags LIKE ?)"
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])
    sql += " ORDER BY rating DESC"
    all_courses = db.execute(sql, params).fetchall()
    categories = db.execute("SELECT DISTINCT category FROM courses ORDER BY category").fetchall()
    return render_template("courses.html", courses=all_courses, categories=categories,
                           selected_category=category, search=search)

@app.route("/course/<int:course_id>")
def course_detail(course_id):
    db = get_db()

    course = db.execute(
        "SELECT * FROM courses WHERE id = ?",
        (course_id,)
    ).fetchone()

    if not course:
        flash("Course not found.", "error")
        return redirect(url_for("courses"))

    if "user_id" in session:
        db.execute(
            "INSERT INTO interactions (user_id, course_id, action) VALUES (?, ?, 'viewed')",
            (session["user_id"], course_id)
        )
        db.commit()
        resources = db.execute(
            "SELECT * FROM course_resources WHERE course_id = ? ORDER BY id",
            (course_id,)
            ).fetchall()
        return render_template(
            "course_detail.html",
            course=course,
            resources=resources
            )
@app.route("/rate/<int:course_id>", methods=["POST"])
@login_required
def rate_course(course_id):
    try:
        rating = int(request.form.get("rating", "0"))
    except ValueError:
        rating = 0
    if rating < 1 or rating > 5:
        flash("Please choose a rating between 1 and 5.", "error")
        return redirect(request.referrer or url_for("courses"))
    db = get_db()
    exists = db.execute("SELECT id FROM courses WHERE id = ?", (course_id,)).fetchone()
    if not exists:
        flash("Course not found.", "error")
        return redirect(url_for("courses"))
    db.execute("""
        INSERT INTO ratings (user_id, course_id, rating)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, course_id) DO UPDATE SET rating=excluded.rating, created_at=CURRENT_TIMESTAMP
    """, (session["user_id"], course_id, rating))
    db.execute("""
        INSERT INTO interactions (user_id, course_id, action)
        VALUES (?, ?, 'rated')
    """, (session["user_id"], course_id))
    db.commit()
    flash("Your rating has been saved. Recommendations can now use it.", "success")
    return redirect(request.referrer or url_for("dashboard"))

@app.route("/interact/<int:course_id>", methods=["POST"])
@login_required
def interact(course_id):
    db = get_db()
    if db.execute("SELECT id FROM courses WHERE id = ?", (course_id,)).fetchone():
        db.execute("INSERT INTO interactions (user_id, course_id, action) VALUES (?, ?, 'viewed')",
                   (session["user_id"], course_id))
        db.commit()
    return redirect(request.referrer or url_for("courses"))

@app.route("/interests", methods=["POST"])
@login_required
def interests():
    selected = request.form.getlist("interests")
    db = get_db()
    db.execute("UPDATE users SET interests = ? WHERE id = ?",
               (",".join(selected), session["user_id"]))
    db.commit()
    flash("Your interests have been updated.", "success")
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    app.run(debug=True)
