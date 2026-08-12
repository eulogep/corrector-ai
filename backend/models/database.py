"""
Initialisation de la base SQLite et fonctions CRUD.
Gère les tables : professors, students, exams, exercises.
Toutes les données restent en local (RGPD).
"""

import sqlite3
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from backend.config import DATABASE_PATH, DATABASE_URL

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # PostgreSQL reste une dépendance optionnelle en développement.
    psycopg = None
    dict_row = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Connexion
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CompatRow(dict):
    """Dict-like row that also preserves SQLite's positional access contract."""

    def __getitem__(self, key: Any):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class PostgresCursor:
    """Minimal DB-API adapter so existing repository code stays backend-neutral."""

    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def fetchone(self):
        row = self._cursor.fetchone()
        return CompatRow(row) if row is not None else None

    def fetchall(self):
        return [CompatRow(row) for row in self._cursor.fetchall()]


class PostgresConnection:
    """Translate SQLite placeholders to PostgreSQL placeholders at the boundary."""

    def __init__(self, connection):
        self._connection = connection

    @staticmethod
    def _translate(query: str) -> str:
        return query.replace("?", "%s").replace("datetime('now')", "CURRENT_TIMESTAMP")

    def execute(self, query: str, params=None) -> PostgresCursor:
        cursor = self._connection.execute(self._translate(query), params or ())
        return PostgresCursor(cursor)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def uses_postgres() -> bool:
    """Return True only when a PostgreSQL connection URL was explicitly configured."""
    return bool(DATABASE_URL)


def get_connection():
    """Create a PostgreSQL connection when configured, otherwise a local SQLite one."""
    if uses_postgres():
        if psycopg is None:
            raise RuntimeError("PostgreSQL configuré mais la dépendance psycopg est absente.")
        # Le pool transactionnel Supabase (PgBouncer) ne doit pas recevoir de
        # prepared statements de session ; chaque opération reste courte.
        connection = psycopg.connect(
            DATABASE_URL, row_factory=dict_row, prepare_threshold=None
        )
        return PostgresConnection(connection)

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
    """Create all tables if they don't exist in the selected persistence backend."""
    with get_db() as conn:
        if uses_postgres():
            schema_path = Path(__file__).resolve().parent.parent / "migrations" / "001_supabase_postgres.sql"
            schema = schema_path.read_text(encoding="utf-8")
            # psycopg exécute le script dans la transaction déjà ouverte par get_db.
            schema = schema.replace("BEGIN;", "").replace("COMMIT;", "")
            conn.execute(schema)
            return
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

            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                professor_id INTEGER NOT NULL,
                matiere TEXT DEFAULT '',
                niveau TEXT DEFAULT '',
                titre TEXT DEFAULT '',
                total_points REAL DEFAULT 20,
                exercices_json TEXT NOT NULL,
                pdf_path TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (professor_id) REFERENCES professors(id)
            );

            CREATE TABLE IF NOT EXISTS review_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_id INTEGER NOT NULL,
                professor_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                previous_status TEXT DEFAULT '',
                new_status TEXT NOT NULL,
                note_before REAL,
                note_after REAL,
                comment TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE,
                FOREIGN KEY (professor_id) REFERENCES professors(id)
            );

            CREATE TABLE IF NOT EXISTS calibration_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_id INTEGER NOT NULL UNIQUE,
                professor_id INTEGER NOT NULL,
                reference_note REAL NOT NULL,
                reference_note_sur REAL NOT NULL DEFAULT 20,
                reference_source TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE,
                FOREIGN KEY (professor_id) REFERENCES professors(id)
            );
        """)
        # Migrations douces : compatibles avec les bases existantes.
        for statement in [
            "ALTER TABLE exams ADD COLUMN subject_id INTEGER DEFAULT NULL",
            "ALTER TABLE exams ADD COLUMN review_status TEXT NOT NULL DEFAULT 'pending_review'",
            "ALTER TABLE exams ADD COLUMN reviewed_at TEXT DEFAULT NULL",
            "ALTER TABLE exams ADD COLUMN reviewed_by INTEGER DEFAULT NULL",
            "ALTER TABLE exams ADD COLUMN review_comment TEXT DEFAULT ''",
            "ALTER TABLE exams ADD COLUMN ai_note_totale REAL DEFAULT NULL",
            "ALTER TABLE exams ADD COLUMN ai_appreciation TEXT DEFAULT ''",
        ]:
            try:
                conn.execute(statement)
            except sqlite3.OperationalError:
                pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers — conversion Row → dict
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def row_to_dict(row) -> dict:
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
        query = "INSERT INTO professors (nom, prenom, email, password_hash) VALUES (?, ?, ?, ?)"
        if uses_postgres():
            query += " RETURNING id"
        cursor = conn.execute(query, (nom, prenom, email, password_hash))
        return cursor.fetchone()["id"] if uses_postgres() else cursor.lastrowid


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
        query = "INSERT INTO students (professor_id, nom, prenom, classe, email) VALUES (?, ?, ?, ?, ?)"
        if uses_postgres():
            query += " RETURNING id"
        cursor = conn.execute(query, (professor_id, nom, prenom, classe, email))
        return cursor.fetchone()["id"] if uses_postgres() else cursor.lastrowid


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
                alerte_anomalie: int = 0, message_anomalie: str = "",
                subject_id: int | None = None) -> int:
    """Insert a new exam and return its ID."""
    with get_db() as conn:
        query = """INSERT INTO exams
               (student_id, professor_id, matiere, niveau, date_examen,
                note_totale, note_sur, appreciation, image_path,
                alerte_anomalie, message_anomalie, subject_id,
                review_status, ai_note_totale, ai_appreciation)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', ?, ?)"""
        if uses_postgres():
            query += " RETURNING id"
        cursor = conn.execute(
            query,
            (student_id, professor_id, matiere, niveau, date_examen,
             note_totale, note_sur, appreciation, image_path,
             alerte_anomalie, message_anomalie, subject_id,
             note_totale, appreciation),
        )
        return cursor.fetchone()["id"] if uses_postgres() else cursor.lastrowid


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
        query = """INSERT INTO exercises
               (exam_id, numero, enonce, reponse_eleve, reponse_attendue,
                points_obtenus, points_max, correct, feedback, erreurs_types)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        if uses_postgres():
            query += " RETURNING id"
        cursor = conn.execute(
            query,
            (exam_id, numero, enonce, reponse_eleve, reponse_attendue,
             points_obtenus, points_max, correct, feedback, erreurs_types),
        )
        return cursor.fetchone()["id"] if uses_postgres() else cursor.lastrowid


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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CRUD — Subjects (sujets d'examen + barème)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def save_subject(professor_id: int, data: dict) -> int:
    """
    Save a parsed/validated subject with its barème.
    data = {matiere, niveau, titre, total_points, exercices (list), pdf_path}
    """
    import json as _json
    exercices_json = _json.dumps(data.get("exercices", []), ensure_ascii=False)
    with get_db() as conn:
        query = """INSERT INTO subjects
               (professor_id, matiere, niveau, titre, total_points, exercices_json, pdf_path)
               VALUES (?, ?, ?, ?, ?, ?, ?)"""
        if uses_postgres():
            query += " RETURNING id"
        cursor = conn.execute(
            query,
            (
                professor_id,
                data.get("matiere", ""),
                data.get("niveau", ""),
                data.get("titre", ""),
                float(data.get("total_points", 20)),
                exercices_json,
                data.get("pdf_path", ""),
            ),
        )
        return cursor.fetchone()["id"] if uses_postgres() else cursor.lastrowid


def get_subject(subject_id: int) -> dict | None:
    """Fetch a subject by ID, exercices deserialized from JSON."""
    import json as _json
    with get_db() as conn:
        row = conn.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        try:
            d["exercices"] = _json.loads(d.get("exercices_json") or "[]")
        except Exception:
            d["exercices"] = []
        return d


def list_subjects(professor_id: int) -> list:
    """List all subjects owned by a professor, most recent first."""
    import json as _json
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, professor_id, matiere, niveau, titre, total_points,
                      pdf_path, created_at, exercices_json
               FROM subjects WHERE professor_id = ?
               ORDER BY created_at DESC""",
            (professor_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                exs = _json.loads(d.get("exercices_json") or "[]")
            except Exception:
                exs = []
            d["nb_exercices"] = len(exs)
            d.pop("exercices_json", None)
            result.append(d)
        return result


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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Revue humaine et pilote de calibration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def update_exam_review(
    exam_id: int,
    professor_id: int,
    status: str,
    comment: str = "",
    final_note: float | None = None,
    final_appreciation: str | None = None,
) -> dict | None:
    """Apply a teacher review and persist an immutable business audit event."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM exams WHERE id = ? AND professor_id = ?", (exam_id, professor_id)
        ).fetchone()
        if row is None:
            return None

        exam = dict(row)
        note_after = exam["note_totale"] if final_note is None else final_note
        appreciation_after = exam["appreciation"] if final_appreciation is None else final_appreciation
        action = "approved" if status == "approved" else "sent_back_for_revision"
        conn.execute(
            """UPDATE exams
               SET review_status = ?, reviewed_at = datetime('now'), reviewed_by = ?,
                   review_comment = ?, note_totale = ?, appreciation = ?
               WHERE id = ?""",
            (status, professor_id, comment, note_after, appreciation_after, exam_id),
        )
        conn.execute(
            """INSERT INTO review_events
               (exam_id, professor_id, action, previous_status, new_status,
                note_before, note_after, comment)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                exam_id,
                professor_id,
                action,
                exam.get("review_status", "pending_review"),
                status,
                exam["note_totale"],
                note_after,
                comment,
            ),
        )
    return get_exam_by_id(exam_id)


def get_review_events(exam_id: int, professor_id: int) -> list:
    """Return the teacher-facing audit history for an owned exam."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, action, previous_status, new_status, note_before, note_after,
                      comment, created_at
               FROM review_events
               WHERE exam_id = ? AND professor_id = ?
               ORDER BY id ASC""",
            (exam_id, professor_id),
        ).fetchall()
        return rows_to_list(rows)


def list_exams_for_review(professor_id: int, status: str | None = None, limit: int = 100) -> list:
    """List owned exams in a review queue, with a bounded result set."""
    query = """SELECT e.*, s.nom as student_nom, s.prenom as student_prenom, s.classe
               FROM exams e JOIN students s ON e.student_id = s.id
               WHERE e.professor_id = ?"""
    params: list = [professor_id]
    if status:
        query += " AND e.review_status = ?"
        params.append(status)
    query += " ORDER BY CASE e.review_status WHEN 'pending_review' THEN 0 WHEN 'needs_revision' THEN 1 ELSE 2 END, e.created_at DESC LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        return rows_to_list(conn.execute(query, params).fetchall())


def save_calibration_case(
    exam_id: int,
    professor_id: int,
    reference_note: float,
    reference_note_sur: float,
    reference_source: str = "",
    notes: str = "",
) -> dict | None:
    """Store or update an anonymised human reference for pilot quality measurement."""
    with get_db() as conn:
        exam = conn.execute(
            "SELECT id FROM exams WHERE id = ? AND professor_id = ?", (exam_id, professor_id)
        ).fetchone()
        if exam is None:
            return None
        conn.execute(
            """INSERT INTO calibration_cases
               (exam_id, professor_id, reference_note, reference_note_sur, reference_source, notes)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(exam_id) DO UPDATE SET
                 reference_note = excluded.reference_note,
                 reference_note_sur = excluded.reference_note_sur,
                 reference_source = excluded.reference_source,
                 notes = excluded.notes,
                 updated_at = datetime('now')""",
            (exam_id, professor_id, reference_note, reference_note_sur, reference_source, notes),
        )
        row = conn.execute(
            "SELECT * FROM calibration_cases WHERE exam_id = ?", (exam_id,)
        ).fetchone()
        return row_to_dict(row)


def get_pilot_metrics(professor_id: int) -> dict:
    """Compute transparent aggregate quality and review metrics for a professor pilot."""
    with get_db() as conn:
        review_rows = conn.execute(
            """SELECT review_status, COUNT(*) AS count
               FROM exams WHERE professor_id = ? GROUP BY review_status""",
            (professor_id,),
        ).fetchall()
        review_counts = {row["review_status"]: row["count"] for row in review_rows}

        quality = conn.execute(
            """SELECT
                 COUNT(*) AS count,
                 AVG(ABS((e.ai_note_totale * 20.0 / NULLIF(e.note_sur, 0)) -
                         (c.reference_note * 20.0 / NULLIF(c.reference_note_sur, 0)))) AS mae_sur_20,
                 AVG((e.ai_note_totale * 20.0 / NULLIF(e.note_sur, 0)) -
                     (c.reference_note * 20.0 / NULLIF(c.reference_note_sur, 0))) AS biais_moyen_sur_20,
                 AVG(CASE WHEN ABS((e.ai_note_totale * 20.0 / NULLIF(e.note_sur, 0)) -
                                   (c.reference_note * 20.0 / NULLIF(c.reference_note_sur, 0))) <= 1.0
                          THEN 1.0 ELSE 0.0 END) AS within_one_point,
                 AVG(CASE WHEN ABS((e.ai_note_totale * 20.0 / NULLIF(e.note_sur, 0)) -
                                   (c.reference_note * 20.0 / NULLIF(c.reference_note_sur, 0))) <= 2.0
                          THEN 1.0 ELSE 0.0 END) AS within_two_points
               FROM calibration_cases c
               JOIN exams e ON e.id = c.exam_id
               WHERE c.professor_id = ?""",
            (professor_id,),
        ).fetchone()

        approved_with_change = conn.execute(
            """SELECT COUNT(*) FROM exams
               WHERE professor_id = ? AND review_status = 'approved'
                 AND ai_note_totale IS NOT NULL
                 AND ABS(note_totale - ai_note_totale) > 0.001""",
            (professor_id,),
        ).fetchone()[0]
        approved_total = review_counts.get("approved", 0)

    return {
        "review": {
            "pending_review": review_counts.get("pending_review", 0),
            "needs_revision": review_counts.get("needs_revision", 0),
            "approved": approved_total,
            "approved_with_note_change": approved_with_change,
            "manual_note_change_rate": round(approved_with_change / approved_total, 4) if approved_total else None,
        },
        "calibration": {
            "count": quality["count"] or 0,
            "mae_sur_20": round(quality["mae_sur_20"], 3) if quality["mae_sur_20"] is not None else None,
            "biais_moyen_sur_20": round(quality["biais_moyen_sur_20"], 3) if quality["biais_moyen_sur_20"] is not None else None,
            "within_one_point": round(quality["within_one_point"], 4) if quality["within_one_point"] is not None else None,
            "within_two_points": round(quality["within_two_points"], 4) if quality["within_two_points"] is not None else None,
        },
    }
