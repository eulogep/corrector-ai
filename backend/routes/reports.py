"""
Routes de rapports — génération PDF et envoi email.
Utilise ReportLab pour le PDF et smtplib pour l'email.
"""

import os
import io
import csv
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from backend.auth import get_current_professor
from backend.config import REPORTS_DIR, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
from backend.models.database import (
    get_exam_by_id, get_exercises_by_exam, get_students_by_professor,
    get_exams_by_student, get_exams_by_professor,
)

router = APIRouter(prefix="/api/reports", tags=["Rapports"])


# ━━━ Couleurs du thème ━━━
PRIMARY = HexColor("#0EA5E9")
DARK = HexColor("#0F172A")
LIGHT = HexColor("#F8FAFC")
SUCCESS = HexColor("#10B981")
DANGER = HexColor("#EF4444")
ACCENT = HexColor("#6366F1")


def _generate_pdf(exam: dict, exercises: list) -> str:
    """Generate a PDF report for an exam. Returns the file path."""
    filename = f"rapport_{exam['id']}_{exam.get('student_nom', 'eleve')}.pdf"
    filepath = os.path.join(REPORTS_DIR, filename)

    doc = SimpleDocTemplate(filepath, pagesize=A4,
                            topMargin=1.5*cm, bottomMargin=1.5*cm,
                            leftMargin=2*cm, rightMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    # Styles personnalisés
    title_style = ParagraphStyle("Title", parent=styles["Title"],
                                  fontSize=20, textColor=DARK, spaceAfter=12)
    heading_style = ParagraphStyle("Heading", parent=styles["Heading2"],
                                    fontSize=14, textColor=PRIMARY, spaceBefore=16, spaceAfter=8)
    body_style = ParagraphStyle("Body", parent=styles["Normal"],
                                 fontSize=10, leading=14)

    # En-tête
    story.append(Paragraph("Corrector AI — Rapport de correction", title_style))
    story.append(Spacer(1, 0.3*cm))

    # Infos élève
    info_data = [
        ["Élève", f"{exam.get('student_prenom', '')} {exam.get('student_nom', '')}"],
        ["Classe", exam.get("classe", "")],
        ["Matière", exam.get("matiere", "")],
        ["Date", exam.get("date_examen", "")],
        ["Note", f"{exam.get('note_totale', 0)} / {exam.get('note_sur', 20)}"],
    ]
    info_table = Table(info_data, colWidths=[4*cm, 12*cm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), PRIMARY),
        ("TEXTCOLOR", (0, 0), (0, -1), LIGHT),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.5*cm))

    # Alerte anomalie
    if exam.get("alerte_anomalie"):
        alert_text = f"⚠ ALERTE : {exam.get('message_anomalie', 'Anomalie détectée')}"
        story.append(Paragraph(alert_text, ParagraphStyle(
            "Alert", parent=body_style, textColor=DANGER, fontSize=11,
            fontName="Helvetica-Bold"
        )))
        story.append(Spacer(1, 0.3*cm))

    # Appréciation
    story.append(Paragraph("Appréciation générale", heading_style))
    story.append(Paragraph(exam.get("appreciation", "—"), body_style))
    story.append(Spacer(1, 0.3*cm))

    # Détail par exercice
    story.append(Paragraph("Détail par exercice", heading_style))
    for ex in exercises:
        # En-tête exercice
        note_color = SUCCESS if ex.get("correct") else DANGER
        ex_header = f"<b>Exercice {ex.get('numero', '?')}</b> — {ex.get('points_obtenus', 0)} / {ex.get('points_max', 0)} pts"
        story.append(Paragraph(ex_header, ParagraphStyle(
            "ExHeader", parent=body_style, fontSize=11, textColor=DARK,
            fontName="Helvetica-Bold", spaceBefore=10
        )))

        if ex.get("enonce"):
            story.append(Paragraph(f"<i>Énoncé : {ex['enonce']}</i>", body_style))
        if ex.get("reponse_eleve"):
            story.append(Paragraph(f"Réponse élève : {ex['reponse_eleve']}", body_style))
        if ex.get("feedback"):
            story.append(Paragraph(f"Feedback : {ex['feedback']}", body_style))
        if ex.get("erreurs_types"):
            story.append(Paragraph(f"Erreurs types : {ex['erreurs_types']}", body_style))
        story.append(Spacer(1, 0.2*cm))

    # Pied de page
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(
        "— Généré par Corrector AI • Données locales RGPD —",
        ParagraphStyle("Footer", parent=body_style, alignment=TA_CENTER,
                        fontSize=8, textColor=HexColor("#94A3B8"))
    ))

    doc.build(story)
    return filepath


@router.get("/pdf/{exam_id}")
async def download_pdf(exam_id: int, prof: dict = Depends(get_current_professor)):
    """Generate and download a PDF report for an exam."""
    exam = get_exam_by_id(exam_id)
    if not exam or exam["professor_id"] != prof["id"]:
        raise HTTPException(status_code=404, detail="Copie non trouvée")
    exercises = get_exercises_by_exam(exam_id)
    filepath = _generate_pdf(exam, exercises)
    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=os.path.basename(filepath),
    )


class EmailRequest(BaseModel):
    exam_id: int
    to_email: str
    message: str = "Veuillez trouver ci-joint votre rapport de correction."

@router.post("/email")
async def send_email_report(data: EmailRequest, prof: dict = Depends(get_current_professor)):
    """Generate a PDF and send it via email SMTP."""
    if not all([SMTP_USER, SMTP_PASSWORD]):
        raise HTTPException(status_code=400, detail="SMTP non configuré. Remplissez les variables SMTP dans .env")

    exam = get_exam_by_id(data.exam_id)
    if not exam or exam["professor_id"] != prof["id"]:
        raise HTTPException(status_code=404, detail="Copie non trouvée")

    exercises = get_exercises_by_exam(data.exam_id)
    filepath = _generate_pdf(exam, exercises)

    try:
        # Construire l'email
        msg = MIMEMultipart()
        msg["From"] = SMTP_FROM or SMTP_USER
        msg["To"] = data.to_email
        msg["Subject"] = f"Corrector AI — Rapport de correction ({exam.get('matiere', '')})"
        msg.attach(MIMEText(data.message, "plain", "utf-8"))

        # Pièce jointe PDF
        with open(filepath, "rb") as f:
            part = MIMEBase("application", "pdf")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(filepath)}")
            msg.attach(part)

        # Envoi SMTP
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        return {"message": f"Email envoyé à {data.to_email}"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'envoi email : {str(e)}")


@router.get("/csv/classe/{classe}")
async def export_csv_classe(classe: str, prof: dict = Depends(get_current_professor)):
    """Export all grades for a class as CSV."""
    students = get_students_by_professor(prof["id"])
    # Filtrer par classe
    students_in_class = [s for s in students if s["classe"] == classe]
    if not students_in_class:
        raise HTTPException(status_code=404, detail="Aucun élève trouvé pour cette classe")

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Nom", "Prénom", "Matière", "Date", "Note", "Sur", "Appréciation"])

    for student in students_in_class:
        exams = get_exams_by_student(student["id"])
        for exam in exams:
            writer.writerow([
                student["nom"], student["prenom"],
                exam["matiere"], exam["date_examen"],
                exam["note_totale"], exam["note_sur"],
                exam.get("appreciation", ""),
            ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=notes_{classe}.csv"},
    )
