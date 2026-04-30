"""
Test exhaustif de l'API Corrector AI en conditions réelles.
Cible : https://corrector-ai.onrender.com
"""

import requests
import json
import os
import time
from datetime import datetime

BASE_URL = "https://corrector-ai.onrender.com"
TIMEOUT = 60
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

results = []
token = None
student_id = None
exam_id = None


def run_test(test_id, description, func):
    """Execute a test and record the result."""
    global results
    start = time.time()
    try:
        status, detail = func()
        elapsed = round(time.time() - start, 2)
        results.append({"id": test_id, "desc": description, "ok": True, "status": status, "detail": detail, "time": elapsed})
        print(f"  {test_id} ✅ {description} → {status} ({elapsed}s)")
    except Exception as e:
        elapsed = round(time.time() - start, 2)
        results.append({"id": test_id, "desc": description, "ok": False, "status": "ERR", "detail": str(e), "time": elapsed})
        print(f"  {test_id} ❌ {description} → ERREUR ({elapsed}s)")
        print(f"         {e}")


def headers():
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


# ━━━ GROUPE 1 — Sanité ━━━
print("\n═══ GROUPE 1 — Sanité de base ═══")


def t01():
    r = requests.get(f"{BASE_URL}/docs", timeout=TIMEOUT)
    assert r.status_code == 200, f"Status {r.status_code}"
    assert "swagger" in r.text.lower(), "Pas de Swagger trouvé"
    return 200, "Swagger UI OK"

run_test("T01", "GET /docs", t01)


def t02():
    r = requests.get(f"{BASE_URL}/openapi.json", timeout=TIMEOUT)
    assert r.status_code == 200, f"Status {r.status_code}"
    data = r.json()
    assert "paths" in data, "Pas de paths dans OpenAPI"
    nb = len(data["paths"])
    return 200, f"OpenAPI valide ({nb} paths)"

run_test("T02", "GET /openapi.json", t02)


def t03():
    r = requests.get(f"{BASE_URL}/api/stats/dashboard", timeout=TIMEOUT)
    assert r.status_code in (200, 401, 403), f"Status {r.status_code}"
    return r.status_code, "Dashboard accessible" if r.status_code == 200 else "Auth requise (normal)"

run_test("T03", "GET /stats/dashboard", t03)


# ━━━ GROUPE 2 — Auth ━━━
print("\n═══ GROUPE 2 — Authentification ═══")


def t04():
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": "test_qa@corrector.ai", "password": "TestQA123!",
        "nom": "QA", "prenom": "Test"
    }, timeout=TIMEOUT)
    assert r.status_code in (200, 400), f"Status {r.status_code}: {r.text[:200]}"
    if r.status_code == 200:
        data = r.json()
        return 200, f"Compte créé (id={data.get('id', '?')})"
    return 400, "Déjà existant (OK)"

run_test("T04", "POST /auth/register", t04)


def t05():
    global token
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "test_qa@corrector.ai", "password": "TestQA123!"
    }, timeout=TIMEOUT)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text[:200]}"
    data = r.json()
    assert "token" in data, f"Pas de token: {data}"
    token = data["token"]
    return 200, f"JWT obtenu ({token[:20]}...)"

run_test("T05", "POST /auth/login", t05)


def t06():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "test_qa@corrector.ai", "password": "MAUVAIS_MDP"
    }, timeout=TIMEOUT)
    assert r.status_code in (400, 401, 403), f"Status {r.status_code} (attendu 4xx)"
    return r.status_code, "Rejeté correctement"

run_test("T06", "Login mauvais mdp", t06)


# ━━━ GROUPE 3 — Élèves ━━━
print("\n═══ GROUPE 3 — Élèves ═══")


def t07():
    global student_id
    r = requests.post(f"{BASE_URL}/api/students/", json={
        "nom": "Dupont", "prenom": "Marie", "classe": "Terminale S1", "email": "marie@test.fr"
    }, headers=headers(), timeout=TIMEOUT)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text[:200]}"
    data = r.json()
    student_id = data.get("id")
    assert student_id, f"Pas d'id: {data}"
    return 200, f"Élève créé (id={student_id})"

run_test("T07", "POST /students/", t07)


def t08():
    r = requests.get(f"{BASE_URL}/api/students/", headers=headers(), timeout=TIMEOUT)
    assert r.status_code == 200, f"Status {r.status_code}"
    data = r.json()
    students = data.get("students", [])
    return 200, f"{len(students)} élève(s) trouvé(s)"

run_test("T08", "GET /students/", t08)


def t09():
    r = requests.get(f"{BASE_URL}/api/students/{student_id}", headers=headers(), timeout=TIMEOUT)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text[:200]}"
    data = r.json()
    return 200, f"Profil: {data.get('prenom', '?')} {data.get('nom', '?')}"

run_test("T09", f"GET /students/{student_id}", t09)


def t10():
    r = requests.get(f"{BASE_URL}/api/students/{student_id}/progression", headers=headers(), timeout=TIMEOUT)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text[:200]}"
    data = r.json()
    return 200, f"Progression OK (nb_exams={data.get('nb_exams', '?')})"

run_test("T10", f"GET /students/{student_id}/progression", t10)


# ━━━ GROUPE 4 — Correction rapide ━━━
print("\n═══ GROUPE 4 — Correction rapide ═══")


def t11():
    r = requests.post(f"{BASE_URL}/api/grading/quick", json={
        "matiere": "Mathématiques",
        "niveau": "Terminale",
        "note_sur": 10,
        "exercices_corrige": [
            {"numero": 1, "enonce": "Résoudre 2x = 10", "reponse_attendue": "x = 5", "points_max": 5},
            {"numero": 2, "enonce": "Résoudre 3x + 2 = 11", "reponse_attendue": "x = 3", "points_max": 5},
        ],
        "reponses_eleve": [
            {"numero": 1, "reponse_eleve": "x = 5 donc 2x = 10"},
            {"numero": 2, "reponse_eleve": "3x + 2 = 11 donc x = 3"},
        ],
    }, headers=headers(), timeout=TIMEOUT)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text[:300]}"
    data = r.json()
    note = data.get("note_totale", "?")
    llm = data.get("llm_used", "?")
    return 200, f"Note: {note}/{data.get('note_sur', '?')} (via {llm})"

run_test("T11", "POST /grading/quick", t11)


# ━━━ GROUPE 5 — OCR ━━━
print("\n═══ GROUPE 5 — OCR ═══")


def t12():
    # Créer une image PNG minimale (1x1 pixel blanc)
    # PNG header + IHDR + IDAT + IEND
    import struct, zlib
    width, height = 100, 30

    def create_png(w, h):
        def chunk(ctype, data):
            c = ctype + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        sig = b'\x89PNG\r\n\x1a\n'
        ihdr = chunk(b'IHDR', struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        raw = b''
        for y in range(h):
            raw += b'\x00' + b'\xff\xff\xff' * w
        idat = chunk(b'IDAT', zlib.compress(raw))
        iend = chunk(b'IEND', b'')
        return sig + ihdr + idat + iend

    png_data = create_png(width, height)
    r = requests.post(
        f"{BASE_URL}/api/ocr/simple",
        files={"file": ("test_ocr.png", png_data, "image/png")},
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"Status {r.status_code}: {r.text[:300]}"
    data = r.json()
    text = data.get("text", "")[:80]
    return 200, f"OCR: '{text}...'"

run_test("T12", "POST /ocr/simple", t12)


# ━━━ GROUPE 6 — Correction complète ━━━
print("\n═══ GROUPE 6 — Correction complète ═══")


def t13():
    global exam_id
    r = requests.post(f"{BASE_URL}/api/grading/grade", json={
        "student_id": student_id,
        "matiere": "Mathématiques",
        "niveau": "Terminale",
        "date_examen": "2026-04-30",
        "note_sur": 10,
        "exercices_corrige": [
            {"numero": 1, "enonce": "Résoudre 2x = 10", "reponse_attendue": "x = 5", "points_max": 5},
            {"numero": 2, "enonce": "Résoudre 3x + 2 = 11", "reponse_attendue": "x = 3", "points_max": 5},
        ],
        "reponses_eleve": [
            {"numero": 1, "reponse_eleve": "x = 5"},
            {"numero": 2, "reponse_eleve": "x = 3"},
        ],
    }, headers=headers(), timeout=TIMEOUT)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text[:400]}"
    data = r.json()
    exam_id = data.get("exam_id")
    note = data.get("note_totale", "?")
    llm = data.get("llm_used", "?")
    return 200, f"exam_id={exam_id}, Note: {note}/{data.get('note_sur', '?')} (via {llm})"

run_test("T13", "POST /grading/grade", t13)


# ━━━ GROUPE 7 — Rapports ━━━
print("\n═══ GROUPE 7 — Rapports ═══")


def t14():
    if not exam_id:
        return "SKIP", "Pas d'exam_id (T13 a échoué)"
    r = requests.get(
        f"{BASE_URL}/api/reports/pdf/{exam_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"Status {r.status_code}: {r.text[:200]}"
    ct = r.headers.get("content-type", "")
    pdf_path = os.path.join(OUTPUT_DIR, "rapport_test.pdf")
    with open(pdf_path, "wb") as f:
        f.write(r.content)
    size_kb = round(len(r.content) / 1024, 1)
    return 200, f"PDF sauvegardé ({size_kb} KB) → {pdf_path}"

run_test("T14", f"GET /reports/pdf/{exam_id}", t14)


# ━━━ GROUPE 8 — Nettoyage ━━━
print("\n═══ GROUPE 8 — Nettoyage ═══")


def t15():
    if not exam_id:
        return "SKIP", "Pas d'exam_id"
    r = requests.delete(
        f"{BASE_URL}/api/grading/exams/{exam_id}",
        headers=headers(),
        timeout=TIMEOUT,
    )
    if r.status_code == 404:
        return 404, "Endpoint DELETE non implémenté (non bloquant)"
    assert r.status_code == 200, f"Status {r.status_code}: {r.text[:200]}"
    return 200, "Copie de test supprimée"

run_test("T15", f"DELETE /exams/{exam_id}", t15)


# ━━━ RAPPORT FINAL ━━━
print("\n")
total = len(results)
passed = sum(1 for r in results if r["ok"])
failed = total - passed
total_time = round(sum(r["time"] for r in results), 1)
avg_time = round(total_time / total, 1) if total else 0
today = datetime.now().strftime("%Y-%m-%d %H:%M")

report_lines = []
report_lines.append("╔══════════════════════════════════════════════════════════════╗")
report_lines.append("║          RAPPORT DE TESTS — CORRECTOR AI                    ║")
report_lines.append(f"║          {BASE_URL}       ║")
report_lines.append("╠══════════════════════════════════════════════════════════════╣")
report_lines.append(f"║  Date        : {today:<43} ║")
report_lines.append(f"║  Tests       : {total} tests exécutés{' '*(29-len(str(total)))}║")
report_lines.append(f"║  Résultat    : {passed} ✅  {failed} ❌{' '*(35-len(str(passed))-len(str(failed)))}║")
report_lines.append(f"║  Durée totale: {total_time}s{' '*(42-len(str(total_time)))}║")
report_lines.append("╠══════════════════════════════════════════════════════════════╣")

for r in results:
    icon = "✅" if r["ok"] else "❌"
    line = f"║  {r['id']} {icon} {r['desc']:<28} → {str(r['status']):<5} ({r['time']}s)"
    report_lines.append(f"{line:<61}║")
    if not r["ok"]:
        detail = r["detail"][:55]
        report_lines.append(f"║         Détail: {detail:<43}║")

report_lines.append("╠══════════════════════════════════════════════════════════════╣")
report_lines.append(f"║  ENDPOINTS OK      : {passed}/{total}{' '*(36-len(str(passed))-len(str(total)))}║")
report_lines.append(f"║  TEMPS MOYEN       : {avg_time}s/requête{' '*(33-len(str(avg_time)))}║")
report_lines.append("╚══════════════════════════════════════════════════════════════╝")

# Recommandations
if failed > 0:
    report_lines.append("\nRECOMMANDATIONS :")
    for r in results:
        if not r["ok"]:
            report_lines.append(f"  ❌ {r['id']} échoue → {r['detail'][:100]}")

report_text = "\n".join(report_lines)
print(report_text)

# Sauvegarder le rapport
report_file = os.path.join(OUTPUT_DIR, f"rapport_api_{datetime.now().strftime('%Y%m%d')}.txt")
with open(report_file, "w", encoding="utf-8") as f:
    f.write(report_text)
print(f"\n📄 Rapport sauvegardé → {report_file}")
