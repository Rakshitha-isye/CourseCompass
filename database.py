import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "elearning.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            interests TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            level TEXT NOT NULL,
            description TEXT NOT NULL,
            duration TEXT NOT NULL,
            rating REAL DEFAULT 0,
            tags TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, course_id)
        );
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
            action TEXT NOT NULL CHECK(action IN ('viewed', 'rated')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS course_resources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        url TEXT NOT NULL,
        resource_type TEXT DEFAULT 'Tutorial',
        UNIQUE(course_id, url)
        );
        """)
        db.commit()

def seed_demo_data():
    course_data = [
        ("Python Programming", "Programming", "Beginner", "Learn Python syntax, variables, loops, functions, and problem solving.", "6 weeks", 4.8, "python coding programming"),
        ("Data Structures and Algorithms", "Programming", "Intermediate", "Practice arrays, linked lists, stacks, queues, trees, and algorithms.", "8 weeks", 4.7, "dsa algorithms coding"),
        ("Web Development with Flask", "Web Development", "Beginner", "Build dynamic websites using Python, Flask, HTML, and CSS.", "5 weeks", 4.6, "python flask html css web"),
        ("Frontend Development", "Web Development", "Beginner", "Create responsive interfaces with HTML, CSS, and JavaScript.", "6 weeks", 4.5, "html css javascript frontend"),
        ("Data Analysis with Pandas", "Data Science", "Intermediate", "Clean, transform, analyze, and summarize datasets with Pandas.", "4 weeks", 4.6, "python pandas data analysis"),
        ("Machine Learning Fundamentals", "Data Science", "Intermediate", "Understand supervised learning, model evaluation, and feature engineering.", "8 weeks", 4.7, "machine learning python scikit-learn"),
        ("Deep Learning Basics", "Data Science", "Advanced", "Explore neural networks, training, and deep learning applications.", "10 weeks", 4.4, "deep learning ai neural networks"),
        ("SQL and Database Design", "Databases", "Beginner", "Learn SQL queries, joins, relational modeling, and normalization.", "4 weeks", 4.5, "sql database sqlite"),
        ("Cloud Computing Essentials", "Cloud", "Beginner", "Understand cloud services, deployment, scalability, and cloud architecture.", "5 weeks", 4.3, "cloud deployment architecture"),
        ("Cybersecurity Foundations", "Security", "Beginner", "Learn security principles, threats, authentication, and safe practices.", "6 weeks", 4.4, "security cybersecurity networks"),
        ("Statistics for Data Science", "Data Science", "Beginner", "Learn descriptive statistics, probability, and statistical reasoning.", "4 weeks", 4.5, "statistics probability data"),
        ("Java Programming", "Programming", "Beginner", "Learn object-oriented programming and core Java concepts.", "6 weeks", 4.4, "java programming oop"),
    ]
    demo_users = [
        ("Demo Learner 1", "demo1@example.com", "Programming,Data Science"),
        ("Demo Learner 2", "demo2@example.com", "Programming,Data Science"),
        ("Demo Learner 3", "demo3@example.com", "Web Development,Databases"),
        ("Demo Learner 4", "demo4@example.com", "Data Science,Cloud"),
        ("Demo Learner 5", "demo5@example.com", "Programming,Web Development"),
    ]
    with get_db() as db:
        count = db.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
        if count == 0:
            db.executemany("""INSERT INTO courses
                (title, category, level, description, duration, rating, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?)""", course_data)
        # Demo accounts use a known development-only password; change/remove before deployment.
        from werkzeug.security import generate_password_hash
        for name, email, interests in demo_users:
            found = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if not found:
                db.execute("INSERT INTO users (name,email,password_hash,interests) VALUES (?,?,?,?)",
                           (name, email, generate_password_hash("Demo123!"), interests))
        db.commit()
        # Create sample ratings only once, so collaborative filtering has interaction data.
        if db.execute("SELECT COUNT(*) FROM ratings").fetchone()[0] == 0:
            demo_rating_map = {
                1: {1:5, 2:5, 3:3, 5:5, 6:4, 12:4},
                2: {1:5, 2:4, 5:5, 6:5, 7:4, 11:4},
                3: {3:5, 4:5, 8:5, 9:3, 10:4},
                4: {5:5, 6:5, 7:4, 9:5, 11:4},
                5: {1:4, 2:4, 3:5, 4:5, 8:3},
            }
            for user_id, ratings in demo_rating_map.items():
                for course_id, rating in ratings.items():
                    db.execute("INSERT OR IGNORE INTO ratings (user_id, course_id, rating) VALUES (?,?,?)",
                               (user_id, course_id, rating))
def seed_course_resources():
    resource_data = {
        "Python Programming": [
            ("Official Python Tutorial",
             "https://docs.python.org/3/tutorial/", "Documentation"),
            ("Python for Everybody",
             "https://www.py4e.com/lessons", "Course")
        ],
        "Web Development with Flask": [
            ("Flask Quickstart",
             "https://flask.palletsprojects.com/en/stable/quickstart/", "Documentation")
        ],
        "Frontend Development": [
            ("HTML Learning Guide",
             "https://developer.mozilla.org/en-US/docs/Learn/HTML", "Tutorial"),
            ("CSS Learning Guide",
             "https://developer.mozilla.org/en-US/docs/Learn/CSS", "Tutorial")
        ],
        "Data Analysis with Pandas": [
            ("Pandas Getting Started",
             "https://pandas.pydata.org/docs/getting_started/index.html", "Documentation")
        ],
        "Machine Learning Fundamentals": [
            ("Scikit-learn Getting Started",
             "https://scikit-learn.org/stable/getting_started.html", "Tutorial")
        ],
        "SQL and Database Design": [
            ("SQLite Tutorial",
             "https://www.sqlitetutorial.net/", "Tutorial")
        ],
        "Java Programming": [
            ("Official Java Learning",
             "https://dev.java/learn/", "Documentation")
        ]
    }

    with get_db() as db:
        for course_title, resources in resource_data.items():
            course = db.execute(
                "SELECT id FROM courses WHERE title = ?",
                (course_title,)
            ).fetchone()

            if course:
                for title, url, resource_type in resources:
                    db.execute("""
                        INSERT OR IGNORE INTO course_resources
                        (course_id, title, url, resource_type)
                        VALUES (?, ?, ?, ?)
                    """, (course["id"], title, url, resource_type))
                    db.commit()
            db.commit()
