"""
Initialisation de la base SQLite et fonctions CRUD.
Gère les tables : professors, students, exams, exercises.
Toutes les données restent en local (RGPD).
"""

import sqlite3
import os
from contextlib import contextmanager
from backend.config import DATABASE_PATH


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Connexion
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_connection() -> sqlite3.Connection:
    """Create a new SQLite connection with row factory."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Initialisation des tables
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def init_db():
    """Create all tables if they don't exist."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS professors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT NOT NULL,
                prenom TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                professor_id INTEGER NOT NULL,
                nom TEXT NOT NULL,
                prenom TEXT NOT NULL,
                classe TEXT NOT NULL,
                email TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (professor_id) REFERENCES professors(id)
            );

            CREATE TABLE IF NOT EXISTS exams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                professor_id INTEGER NOT NULL,
                matiere TEXT NOT NULL,
                niveau TEXT DEFAULT '',
                date_examen TEXT DEFAULT (date('now')),
                note_totale REAL DEFAULT 0,
                note_sur REAL DEFAULT 20,
                appreciation TEXT DEFAULT '',
                image_path TEXT DEFAULT '',
                alerte_anomalie INTEGER DEFAULT 0,
                message_anomalie TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (student_id) REFERENCES students(id),
                FOREIGN KEY (professor_id) REFERENCES professors(id)
            );

            CREATE TABLE IF NOT EXISTS exercises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_id INTEGER NOT NULL,
                numero INTEGER NOT NULL,
                enonce TEXT DEFAULT '',
                reponse_eleve TEXT DEFAULT '',
                reponse_attendue TEXT DEFAULT '',
                points_obtenus REAL DEFAULT 0,
                points_max REAL DEFAULT 0,
                correct INTEGER DEFAULT 0,
                feedback TEXT DEFAULT '',
                erreurs_types TEXT DEFAULT '',
                FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
            );
        """)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers — conversion Row → dict
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows) -> list:
    """Convert a list of sqlite3.Row to a list of dicts."""
    return [dict(r) for r in rows]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CRUD — Professors
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_professor(nom: str, prenom: str, email: str, password_hash: str) -> int:
    """Insert a new professor and return their ID."""
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO professors (nom, prenom, email, password_hash) VALUES (?, ?, ?, ?)",
            (nom, prenom, email, password_hash)
        )
        return cursor.lastrowid


def get_professor_by_email(email: str) -> dict | None:
    """Find a professor by email."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM professors WHERE email = ?", (email,)).fetchone()
        return row_to_dict(row)


def get_professor_by_id(prof_id: int) -> dict | None:
    """Find a professor by ID."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM professors WHERE id = ?", (prof_id,)).fetchone()
        return row_to_dict(row)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CRUD — Students
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_student(professor_id: int, nom: str, prenom: str, classe: str, email: str = "") -> int:
    """Insert a new student and return their ID."""
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO students (professor_id, nom, prenom, classe, email) VALUES (?, ?, ?, ?, ?)",
            (professor_id, nom, prenom, classe, email)
        )
        return cursor.lastrowid


def get_students_by_professor(professor_id: int) -> list:
    """List all students for a given professor."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM students WHERE professor_id = ? ORDER BY classe, nom",
            (professor_id,)
        ).fetchall()
        return rows_to_list(rows)


def get_student_by_id(student_id: int) -> dict | None:
    """Get a single student by ID."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        return row_to_dict(row)


def update_student(student_id: int, nom: str, prenom: str, classe: str, email: str) -> bool:
    """Update a student's info. Returns True if found."""
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE students SET nom=?, prenom=?, classe=?, email=? WHERE id=?",
            (nom, prenom, classe, email, student_id)
        )
        return cursor.rowcount > 0


def delete_student(student_id: int) -> bool:
    """Delete a student by ID. Returns True if found."""
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
        return cursor.rowcount > 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CRUD — Exams
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_exam(student_id: int, professor_id: int, matiere: str, niveau: str,
                date_examen: str, note_totale: float, note_sur: float,
                appreciation: str, image_path: str,
                alerte_anomalie: int = 0, message_anomalie: str = "") -> int:
    """Insert a new exam and return its ID."""
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO exams
               (student_id, professor_id, matiere, niveau, date_examen,
                note_totale, note_sur, appreciation, image_path,
                alerte_anomalie, message_anomalie)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (student_id, professor_id, matiere, niveau, date_examen,
             note_totale, note_sur, appreciation, image_path,
             alerte_anomalie, message_anomalie)
        )
        return cursor.lastrowid


def get_exam_by_id(exam_id: int) -> dict | None:
    """Get a single exam with student name."""
    with get_db() as conn:
        row = conn.execute(
            """SELECT e.*, s.nom as student_nom, s.prenom as student_prenom, s.classe
               FROM exams e JOIN students s ON e.student_id = s.id
               WHERE e.id = ?""",
            (exam_id,)
        ).fetchone()
        return row_to_dict(row)


def get_exams_by_student(student_id: int) -> list:
    """List all exams for a student, most recent first."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM exams WHERE student_id = ? ORDER BY date_examen DESC",
            (student_id,)
        ).fetchall()
        return rows_to_list(rows)


def get_exams_by_professor(professor_id: int, limit: int = 100, offset: int = 0) -> list:
    """List exams for a professor with pagination."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT e.*, s.nom as student_nom, s.prenom as student_prenom, s.classe
               FROM exams e JOIN students s ON e.student_id = s.id
               WHERE e.professor_id = ?
               ORDER BY e.created_at DESC LIMIT ? OFFSET ?""",
            (professor_id, limit, offset)
        ).fetchall()
        return rows_to_list(rows)


def get_recent_exams_by_student_matiere(student_id: int, matiere: str, limit: int = 5) -> list:
    """Get last N exams for a student in a given subject (for anomaly detection)."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM exams
               WHERE student_id = ? AND matiere = ?
               ORDER BY date_examen DESC LIMIT ?""",
            (student_id, matiere, limit)
        ).fetchall()
        return rows_to_list(rows)


def delete_exam(exam_id: int) -> bool:
    """Delete an exam and its exercises (CASCADE). Returns True if found."""
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
        return cursor.rowcount > 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CRUD — Exercises
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_exercise(exam_id: int, numero: int, enonce: str, reponse_eleve: str,
                    reponse_attendue: str, points_obtenus: float, points_max: float,
                    correct: int, feedback: str, erreurs_types: str = "") -> int:
    """Insert a new exercise and return its ID."""
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO exercises
               (exam_id, numero, enonce, reponse_eleve, reponse_attendue,
                points_obtenus, points_max, correct, feedback, erreurs_types)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (exam_id, numero, enonce, reponse_eleve, reponse_attendue,
             points_obtenus, points_max, correct, feedback, erreurs_types)
        )
        return cursor.lastrowid


def get_exercises_by_exam(exam_id: int) -> list:
    """List all exercises for an exam, ordered by numero."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM exercises WHERE exam_id = ? ORDER BY numero",
            (exam_id,)
        ).fetchall()
        return rows_to_list(rows)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Stats — Dashboard professeur
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_professor_stats(professor_id: int) -> dict:
    """Compute dashboard metrics for a professor."""
    with get_db() as conn:
        # Nombre total d'élèves
        nb_students = conn.execute(
            "SELECT COUNT(*) FROM students WHERE professor_id = ?", (professor_id,)
        ).fetchone()[0]

        # Nombre total de copies corrigées
        nb_exams = conn.execute(
            "SELECT COUNT(*) FROM exams WHERE professor_id = ?", (professor_id,)
        ).fetchone()[0]

        # Moyenne générale
        avg_row = conn.execute(
            "SELECT AVG(note_totale * 20.0 / note_sur) FROM exams WHERE professor_id = ? AND note_sur > 0",
            (professor_id,)
        ).fetchone()
        moyenne_generale = round(avg_row[0], 2) if avg_row[0] is not None else 0

        # Nombre d'alertes anomalies
        nb_alertes = conn.execute(
            "SELECT COUNT(*) FROM exams WHERE professor_id = ? AND alerte_anomalie = 1",
            (professor_id,)
        ).fetchone()[0]

        # Moyennes par matière
        rows = conn.execute(
            """SELECT matiere, AVG(note_totale * 20.0 / note_sur) as moy, COUNT(*) as nb
               FROM exams WHERE professor_id = ? AND note_sur > 0
               GROUP BY matiere ORDER BY matiere""",
            (professor_id,)
        ).fetchall()
        moyennes_par_matiere = [
            {"matiere": r["matiere"], "moyenne": round(r["moy"], 2), "nb_copies": r["nb"]}
            for r in rows
        ]

        # 5 dernières copies
        recent = conn.execute(
            """SELECT e.id, e.matiere, e.note_totale, e.note_sur, e.date_examen,
                      e.alerte_anomalie, s.nom, s.prenom, s.classe
               FROM exams e JOIN students s ON e.student_id = s.id
               WHERE e.professor_id = ?
               ORDER BY e.created_at DESC LIMIT 5""",
            (professor_id,)
        ).fetchall()
        recent_exams = rows_to_list(recent)

        return {
            "nb_students": nb_students,
            "nb_exams": nb_exams,
            "moyenne_generale": moyenne_generale,
            "nb_alertes": nb_alertes,
            "moyennes_par_matiere": moyennes_par_matiere,
            "recent_exams": recent_exams,
        }


def get_student_progression(student_id: int) -> dict:
    """Get progression data per subject for a student."""
    with get_db() as conn:
        # Moyenne globale
        avg_row = conn.execute(
            "SELECT AVG(note_totale * 20.0 / note_sur) FROM exams WHERE student_id = ? AND note_sur > 0",
            (student_id,)
        ).fetchone()
        moyenne = round(avg_row[0], 2) if avg_row[0] is not None else 0

        # Par matière avec historique
        matieres = conn.execute(
            "SELECT DISTINCT matiere FROM exams WHERE student_id = ?", (student_id,)
        ).fetchall()

        progression = {}
        for m in matieres:
            matiere = m["matiere"]
            rows = conn.execute(
                """SELECT date_examen, note_totale, note_sur
                   FROM exams WHERE student_id = ? AND matiere = ?
                   ORDER BY date_examen ASC""",
                (student_id, matiere)
            ).fetchall()
            progression[matiere] = [
                {
                    "date": r["date_examen"],
                    "note": r["note_totale"],
                    "sur": r["note_sur"],
                    "note_sur_20": round(r["note_totale"] * 20.0 / r["note_sur"], 2) if r["note_sur"] > 0 else 0,
                }
                for r in rows
            ]

        # Nombre total de copies
        nb_exams = conn.execute(
            "SELECT COUNT(*) FROM exams WHERE student_id = ?", (student_id,)
        ).fetchone()[0]

        return {
            "moyenne_generale": moyenne,
            "nb_exams": nb_exams,
            "progression": progression,
        }
