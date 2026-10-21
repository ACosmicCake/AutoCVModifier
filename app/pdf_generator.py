# cv_tailor_project/app/pdf_generator.py
import json
import logging
import os
import traceback
from xml.sax.saxutils import escape

from reportlab.lib.colors import black, gray, lightgrey
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

logger = logging.getLogger(__name__)

# --- Font Setup ---
FONT_NAME = 'Helvetica'
FONT_NAME_BOLD = 'Helvetica-Bold'
FONT_NAME_ITALIC = 'Helvetica-Oblique'

PLACEHOLDER_DATES = {"", "dates not specified", "n/a"}


def esc(value) -> str:
    """Escapes model-generated text so ReportLab doesn't parse it as markup (e.g. 'a<b' or 'R&D')."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value if v not in (None, ""))
    return escape(str(value).strip())


def as_list(value) -> list:
    """Model output sometimes has a string where a list is expected (or vice versa)."""
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [v for v in value if v not in (None, "")]
    return [value]


def parse_cv_json(json_text_block: str) -> dict | None:
    """
    Parses the JSON text block of CV data into a Python dictionary.
    """
    try:
        data = json.loads(json_text_block)
    except (json.JSONDecodeError, TypeError) as e:
        logger.error("Error decoding CV JSON: %s", e)
        return None
    if isinstance(data, dict) and isinstance(data.get("CV"), dict):
        return data["CV"]
    if isinstance(data, dict):
        logger.warning("'CV' root key not found in JSON. Assuming the entire JSON object is the CV data.")
        return data
    logger.error("Parsed CV JSON is not an object.")
    return None


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='NameStyle', fontName=FONT_NAME_BOLD, fontSize=20, alignment=TA_CENTER, spaceAfter=0.03*inch, textColor=black, leading=24))
    styles.add(ParagraphStyle(name='ContactStyle', fontName=FONT_NAME, fontSize=9.5, alignment=TA_CENTER, spaceAfter=0.1*inch, textColor=black, leading=11))
    styles.add(ParagraphStyle(name='SummaryStyle', fontName=FONT_NAME, fontSize=9.5, textColor=black, leading=12, spaceBefore=0.02*inch, spaceAfter=0.08*inch, alignment=TA_JUSTIFY))
    styles.add(ParagraphStyle(name='TemplateSectionTitle', fontName=FONT_NAME_BOLD, fontSize=10.5, textColor=black, spaceBefore=0.1*inch, spaceAfter=0.05*inch, alignment=TA_LEFT, keepWithNext=1))
    styles.add(ParagraphStyle(name='EntryHeader', fontName=FONT_NAME_BOLD, fontSize=9.5, textColor=black, spaceAfter=0.01*inch, alignment=TA_LEFT, leading=11))
    styles.add(ParagraphStyle(name='EntrySubHeader', fontName=FONT_NAME, fontSize=9.5, textColor=black, spaceAfter=0.01*inch, alignment=TA_LEFT, leading=11))
    styles.add(ParagraphStyle(name='DateLocation', fontName=FONT_NAME_ITALIC, fontSize=9.5, textColor=gray, alignment=TA_RIGHT, leading=11))
    styles.add(ParagraphStyle(name='SubDetail', fontName=FONT_NAME, fontSize=9.5, textColor=black, leading=11, spaceAfter=0.02*inch, leftIndent=0.05*inch))
    styles.add(ParagraphStyle(name='TemplateBullet', fontName=FONT_NAME, fontSize=9.5, textColor=black, leading=12, spaceBefore=0.01*inch, leftIndent=0.2*inch, bulletIndent=0.08*inch, firstLineIndent=0))
    styles.add(ParagraphStyle(name='SkillsCategory', fontName=FONT_NAME_BOLD, fontSize=9.5, textColor=black, leading=11, spaceBefore=0.02*inch, spaceAfter=0.005*inch, keepWithNext=1))
    styles.add(ParagraphStyle(name='SkillInTableStyle', fontName=FONT_NAME, fontSize=9.5, textColor=black, leading=11, alignment=TA_LEFT))
    return styles


def create_cv_pdf(data: dict, output_filepath: str) -> bool:
    """
    Generates a PDF CV from the provided data dictionary and saves it to output_filepath.
    """
    if not data or not isinstance(data, dict):
        logger.error("No valid CV data provided to create_cv_pdf. PDF not generated.")
        return False

    doc = SimpleDocTemplate(output_filepath, pagesize=(8.5 * inch, 11 * inch),
                            leftMargin=0.6*inch, rightMargin=0.6*inch,
                            topMargin=0.4*inch, bottomMargin=0.4*inch,
                            title=f"CV - {data.get('PersonalInformation', {}).get('Name', '') if isinstance(data.get('PersonalInformation'), dict) else ''}")
    styles = _build_styles()
    story = []

    def header_row(left_text, right_text):
        right = esc(right_text)
        date_p = Paragraph(right if right.lower() not in PLACEHOLDER_DATES else "", styles['DateLocation'])
        return Table([[Paragraph(left_text, styles['EntryHeader']), date_p]], colWidths=['75%', '25%'],
                     style=[('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)])

    def joined(*parts, sep=", "):
        return sep.join(esc(p) for p in parts if p and esc(p))

    # --- Personal Information ---
    personal_info = data.get("PersonalInformation", {})
    if isinstance(personal_info, dict):
        story.append(Paragraph(esc(personal_info.get("Name")) or "N/A", styles['NameStyle']))
        contact_info = joined(personal_info.get("PhoneNumber"), personal_info.get("EmailAddress"),
                              personal_info.get("WebsiteOrLinkedInURL"), sep=" / ")
        if contact_info:
            story.append(Paragraph(contact_info, styles['ContactStyle']))
        story.append(HRFlowable(width="100%", thickness=0.5, color=lightgrey, spaceBefore=0, spaceAfter=0.08*inch))

    # --- Summary/Objective (only when the tailored CV includes one) ---
    summary_data = data.get("SummaryOrObjective")
    statement = summary_data.get("Statement") if isinstance(summary_data, dict) else summary_data
    if isinstance(statement, str) and statement.strip():
        story.append(KeepTogether([
            Paragraph("Summary", styles['TemplateSectionTitle']),
            Paragraph(esc(statement), styles['SummaryStyle']),
        ]))

    # --- Generic Section Renderer ---
    def render_section(title, items_data, render_item_func, section_key):
        items = [item for item in as_list(items_data) if isinstance(item, dict)]
        if len(items) != len(as_list(items_data)):
            logger.warning("Some items in section '%s' were not objects and were skipped.", section_key)
        for i, item in enumerate(items):
            render_item_func(item, section_title=title if i == 0 else None)
            if i < len(items) - 1:
                story.append(Spacer(1, 0.05*inch))
        if items:
            story.append(Spacer(1, 0.05*inch))

    def render_education_item(entry, section_title=None):
        flowables = [Paragraph(section_title, styles['TemplateSectionTitle'])] if section_title else []
        flowables.append(header_row(joined(entry.get('InstitutionName') or 'N/A', entry.get('Location')),
                                    entry.get('GraduationDateOrExpected')))
        degree_major = joined(entry.get('DegreeEarned'), entry.get('MajorOrFieldOfStudy'), sep=" - ")
        if degree_major:
            flowables.append(Paragraph(degree_major, styles['EntrySubHeader']))
        honors = as_list(entry.get("HonorsAndAwardsOrRelevantCoursework"))
        if honors:
            honors_text = esc(honors)
            flowables.append(Paragraph(f"<i>{honors_text}</i>" if "thesis:" in honors_text.lower() else honors_text, styles['SubDetail']))
        story.append(KeepTogether(flowables))

    def render_experience_item(job, section_title=None):
        flowables = [Paragraph(section_title, styles['TemplateSectionTitle'])] if section_title else []
        flowables.append(header_row(joined(job.get('CompanyName') or 'N/A', job.get('Location')), job.get("EmploymentDates")))
        if job.get("JobTitle"):
            flowables.append(Paragraph(esc(job.get("JobTitle")), styles['EntrySubHeader']))
        for resp in as_list(job.get("ResponsibilitiesAndAchievements")):
            flowables.append(Paragraph(esc(resp), styles['TemplateBullet'], bulletText='•'))
        story.append(KeepTogether(flowables))

    def render_project_item(proj, section_title=None):
        flowables = [Paragraph(section_title, styles['TemplateSectionTitle'])] if section_title else []
        flowables.append(header_row(esc(proj.get("ProjectName")) or "N/A", proj.get("DatesOrDuration")))
        if proj.get("Description"):
            flowables.append(Paragraph(esc(proj.get("Description")), styles['EntrySubHeader']))
        for contrib in as_list(proj.get("KeyContributionsOrTechnologiesUsed")):
            flowables.append(Paragraph(esc(contrib), styles['TemplateBullet'], bulletText='•'))
        story.append(KeepTogether(flowables))

    def render_volunteer_item(vol_entry, section_title=None):
        flowables = [Paragraph(section_title, styles['TemplateSectionTitle'])] if section_title else []
        flowables.append(header_row(esc(vol_entry.get("OrganizationName")) or "N/A", vol_entry.get("Dates")))
        if vol_entry.get("Role"):
            flowables.append(Paragraph(esc(vol_entry.get("Role")), styles['EntrySubHeader']))
        if vol_entry.get("Description"):
            flowables.append(Paragraph(esc(vol_entry.get("Description")), styles['SubDetail']))
        story.append(KeepTogether(flowables))

    # --- Render Sections ---
    render_section("Education", data.get("Education"), render_education_item, "Education")
    render_section("Professional Experience", data.get("ProfessionalExperience"), render_experience_item, "ProfessionalExperience")
    render_section("Projects", data.get("Projects"), render_project_item, "Projects")

    # --- Skills Section (5 column layout) ---
    skill_groups = [s for s in as_list(data.get("Skills")) if isinstance(s, dict) and as_list(s.get("Skill"))]
    if skill_groups:
        num_cols = 5
        skills_block = [Paragraph("Skills", styles['TemplateSectionTitle'])]
        for skill_item in skill_groups:
            skills_block.append(Paragraph(esc(skill_item.get("SkillCategory")) or "General Skills", styles['SkillsCategory']))
            cells = [Paragraph(esc(skill), styles['SkillInTableStyle']) for skill in as_list(skill_item.get("Skill"))]
            rows = []
            for i in range(0, len(cells), num_cols):
                row = cells[i:i+num_cols]
                row += [Paragraph("", styles['SkillInTableStyle'])] * (num_cols - len(row))
                rows.append(row)
            skill_table = Table(rows, colWidths=['20%'] * num_cols, repeatRows=0)
            skill_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 1),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                ('TOPPADDING', (0, 0), (-1, -1), 1),
            ]))
            skills_block.append(skill_table)
            skills_block.append(Spacer(1, 0.02*inch))
        story.append(KeepTogether(skills_block))
        story.append(Spacer(1, 0.05*inch))

    # --- Certifications & Awards ---
    def render_simple_list_section(title, items_data, fields):
        items = [item for item in as_list(items_data) if isinstance(item, dict)]
        lines = [joined(*(item.get(f) for f in fields), sep=" - ") for item in items]
        lines = [line for line in lines if line]
        if lines:
            block = [Paragraph(title, styles['TemplateSectionTitle'])]
            block += [Paragraph(line, styles['SubDetail']) for line in lines]
            story.append(KeepTogether(block))
            story.append(Spacer(1, 0.05*inch))

    render_simple_list_section("Certifications", data.get("Certifications"), ["CertificationName", "IssuingOrganization", "DateObtained"])
    render_simple_list_section("Awards and Recognition", data.get("AwardsAndRecognition"), ["AwardName", "AwardingBody", "Date"])
    render_section("Volunteer Experience", data.get("VolunteerExperience"), render_volunteer_item, "VolunteerExperience")

    try:
        doc.build(story)
        logger.info("CV generated successfully: %s", output_filepath)
        return True
    except Exception as e:
        logger.error("Error building PDF at %s: %s\n%s", output_filepath, e, traceback.format_exc())
        return False


def generate_cv_pdf_from_json_string(cv_json_string: str, output_filepath: str) -> bool:
    """
    Parses a JSON string containing CV data and generates a PDF CV.
    """
    if not cv_json_string or not output_filepath:
        logger.error("Missing CV JSON or output path for PDF generation.")
        return False
    parsed_cv_data = parse_cv_json(cv_json_string)
    if not parsed_cv_data:
        logger.error("Could not parse CV data. PDF not generated for %s.", output_filepath)
        return False
    return create_cv_pdf(parsed_cv_data, output_filepath)


# --- Main Execution (for testing this module directly) ---
if __name__ == "__main__":
    example = {
        "CV": {
            "PersonalInformation": {"Name": "Johnathan M. Doe", "PhoneNumber": "(555) 123-4567",
                                    "EmailAddress": "john.doe@email.com", "WebsiteOrLinkedInURL": "linkedin.com/in/johndoe"},
            "SummaryOrObjective": {"Statement": "Test Engineer with 5+ years of experience in R&D <QA> automation."},
            "Education": [{"InstitutionName": "State University", "Location": "Anytown, USA",
                           "DegreeEarned": "Bachelor of Science", "MajorOrFieldOfStudy": "Computer Science",
                           "GraduationDateOrExpected": "May 2018",
                           "HonorsAndAwardsOrRelevantCoursework": ["Dean's List", "Thesis: Advanced Algorithms"]}],
            "ProfessionalExperience": [{"CompanyName": "Tech Solutions Inc.", "Location": "Innovate City, USA",
                                        "JobTitle": "Senior Test Engineer", "EmploymentDates": "June 2020 - Present",
                                        "ResponsibilitiesAndAchievements": ["Cut manual testing time by 40% with Selenium and Python.",
                                                                            "Kept p99 latency < 200ms for List<Order> APIs."]}],
            "Skills": [{"SkillCategory": "Programming Languages", "Skill": ["Python", "Java", "C#", "SQL", "HTML5", "CSS3"]}],
            "Certifications": [{"CertificationName": "ISTQB Certified Tester", "IssuingOrganization": "ISTQB"}],
        }
    }
    out_dir = os.path.join("instance", "generated_pdfs_test")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "test_generated_cv.pdf")
    logging.basicConfig(level=logging.INFO)
    print("Success" if generate_cv_pdf_from_json_string(json.dumps(example), out_path) else "Failed", out_path)
