import re
import json # For parsing the new JSON input
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepInFrame, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black, navy, darkslategray, gray, lightgrey
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Attempt to register a common font; use Helvetica if fails
try:
    pdfmetrics.registerFont(TTFont('Calibri', 'C:/Windows/Fonts/calibri.ttf'))
    pdfmetrics.registerFont(TTFont('Calibri-Bold', 'C:/Windows/Fonts/calibrib.ttf'))
    pdfmetrics.registerFont(TTFont('Calibri-Italic', 'C:/Windows/Fonts/calibrii.ttf'))
    pdfmetrics.registerFont(TTFont('Calibri-BoldItalic', 'C:/Windows/Fonts/calibriz.ttf'))
    FONT_NAME = 'Calibri'
    FONT_NAME_BOLD = 'Calibri-Bold'
    FONT_NAME_ITALIC = 'Calibri-Italic'
except Exception as e:
    FONT_NAME = 'Helvetica'
    FONT_NAME_BOLD = 'Helvetica-Bold'
    FONT_NAME_ITALIC = 'Helvetica-Oblique'


# --- Updated Text Parsing Logic for JSON ---
def parse_cv_json(json_text_block):
    """
    Parses the JSON text block of CV data into a Python dictionary.
    """
    try:
        data = json.loads(json_text_block)
        if "CV" in data:
            return data["CV"]
        else:
            # If "CV" root key is missing, assume the entire content is the CV data.
            # This handles cases where the user pastes only the CV content from the Gemini output.
            print("Warning: 'CV' root key not found in JSON. Assuming pasted content is the CV data itself.")
            return data
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return None

# --- PDF Generation Logic (Adapted for new JSON structure and compactness) ---
def create_cv_pdf(data, filename_prefix="cv"):
    if not data:
        print("No valid data to generate PDF. Exiting PDF creation.")
        return

    personal_info = data.get("PersonalInformation", {})
    applicant_name_data = personal_info.get("Name", "Applicant")
    safe_filename = "".join(c if c.isalnum() else "_" for c in applicant_name_data)
    filename = f"{filename_prefix}_{safe_filename}.pdf"

    # Reduced margins for compactness
    doc = SimpleDocTemplate(filename, pagesize=(8.5 * inch, 11 * inch),
                            leftMargin=0.6*inch, rightMargin=0.6*inch,
                            topMargin=0.4*inch, bottomMargin=0.4*inch)

    styles = getSampleStyleSheet()

    # --- Define Styles (adjusted for compactness) ---
    styles.add(ParagraphStyle(name='NameStyle', fontName=FONT_NAME_BOLD, fontSize=20, alignment=TA_CENTER, spaceAfter=0.03*inch, textColor=black, leading=24))
    styles.add(ParagraphStyle(name='ContactStyle', fontName=FONT_NAME, fontSize=9.5, alignment=TA_CENTER, spaceAfter=0.1*inch, textColor=black, leading=11))
    styles.add(ParagraphStyle(name='SummaryStyle', fontName=FONT_NAME, fontSize=9.5, textColor=black, leading=12, spaceBefore=0.05*inch, spaceAfter=0.1*inch, alignment=TA_JUSTIFY, firstLineIndent=0.2*inch))

    styles.add(ParagraphStyle(name='TemplateSectionTitle', fontName=FONT_NAME_BOLD, fontSize=10.5, textColor=black, spaceBefore=0.1*inch, spaceAfter=0.05*inch, alignment=TA_LEFT, keepWithNext=1))

    styles.add(ParagraphStyle(name='EntryHeader', fontName=FONT_NAME_BOLD, fontSize=9.5, textColor=black, spaceAfter=0.01*inch, alignment=TA_LEFT, leading=11))
    styles.add(ParagraphStyle(name='EntrySubHeader', fontName=FONT_NAME, fontSize=9.5, textColor=black, spaceAfter=0.01*inch, alignment=TA_LEFT, leading=11))

    styles.add(ParagraphStyle(name='DateLocation', fontName=FONT_NAME, fontSize=9.5, textColor=gray, alignment=TA_RIGHT, leading=11))

    styles.add(ParagraphStyle(name='SubDetail', fontName=FONT_NAME, fontSize=9.5, textColor=black, leading=11, spaceAfter=0.02*inch, leftIndent=0.05*inch))

    styles.add(ParagraphStyle(name='TemplateBullet', fontName=FONT_NAME, fontSize=9.5, textColor=black, leading=12, spaceBefore=0.01*inch, leftIndent=0.2*inch, bulletIndent=0.08*inch, firstLineIndent=0))

    styles.add(ParagraphStyle(name='SkillsCategory', fontName=FONT_NAME_BOLD, fontSize=9.5, textColor=black, leading=11, spaceBefore=0.03*inch, spaceAfter=0.01*inch))
    styles.add(ParagraphStyle(name='SkillsText', fontName=FONT_NAME, fontSize=9.5, textColor=black, leading=11, leftIndent=0.15*inch))


    story = []

    # --- Personal Information ---
    if personal_info:
        story.append(Paragraph(personal_info.get("Name", ""), styles['NameStyle']))
        contact_parts = [personal_info.get("PhoneNumber"), personal_info.get("EmailAddress"), personal_info.get("WebsiteOrLinkedInURL")]
        contact_info = " / ".join(filter(None, contact_parts))
        story.append(Paragraph(contact_info, styles['ContactStyle']))
        story.append(HRFlowable(width="100%", thickness=0.5, color=lightgrey, spaceBefore=0, spaceAfter=0.08*inch))

    # --- Summary/Objective ---
    summary_data = data.get("SummaryOrObjective", {})
    if summary_data.get("Statement"):
        story.append(Paragraph("Summary", styles['TemplateSectionTitle']))
        story.append(Paragraph(summary_data["Statement"], styles['SummaryStyle']))
        # story.append(Spacer(1, 0.05*inch)) # Reduced spacer

    # --- Education Section ---
    education_list = data.get("Education", [])
    if education_list:
        story.append(Paragraph("Education", styles['TemplateSectionTitle']))
        for i, entry in enumerate(education_list):
            left_col_text = f"{entry.get('InstitutionName', '')}"
            if entry.get('Location'):
                left_col_text += f", {entry.get('Location', '')}"

            right_col_text = entry.get('GraduationDateOrExpected', '')
            date_paragraph = Paragraph(right_col_text, styles['DateLocation']) if right_col_text and right_col_text.strip() and right_col_text.lower() != "dates not specified" else Paragraph("", styles['DateLocation'])

            header_table_data = [[Paragraph(left_col_text, styles['EntryHeader']), date_paragraph]]
            header_table = Table(header_table_data, colWidths=['75%', '25%'])
            header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
            story.append(header_table)

            degree_major = f"{entry.get('DegreeEarned', '')}"
            if entry.get('MajorOrFieldOfStudy'):
                 degree_major += f" - {entry.get('MajorOrFieldOfStudy', '')}"
            story.append(Paragraph(degree_major, styles['EntrySubHeader']))

            honors = entry.get("HonorsAndAwardsOrRelevantCoursework", [])
            for honor in honors:
                if "Thesis:" in honor:
                    story.append(Paragraph(f"<i>{honor}</i>", styles['SubDetail']))
                else:
                    story.append(Paragraph(honor, styles['SubDetail']))

            if i < len(education_list) - 1: # Add smaller spacer between entries
                story.append(Spacer(1, 0.05*inch))
            else: # Slightly larger spacer after the last entry in the section
                story.append(Spacer(1, 0.05*inch))


    # --- Professional Experience Section ---
    experience_list = data.get("ProfessionalExperience", [])
    if experience_list:
        story.append(Paragraph("Professional Experience", styles['TemplateSectionTitle']))
        for i, job in enumerate(experience_list):
            left_col_text = f"{job.get('CompanyName', '')}"
            if job.get('Location'):
                 left_col_text += f", {job.get('Location', '')}"

            right_col_text = job.get("EmploymentDates", "")
            date_paragraph = Paragraph(right_col_text, styles['DateLocation']) if right_col_text and right_col_text.strip() and right_col_text.lower() != "dates not specified" else Paragraph("", styles['DateLocation'])

            header_table_data = [[Paragraph(left_col_text, styles['EntryHeader']), date_paragraph]]
            header_table = Table(header_table_data, colWidths=['75%', '25%'])
            header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
            story.append(header_table)

            story.append(Paragraph(job.get("JobTitle", ""), styles['EntrySubHeader']))

            responsibilities = job.get("ResponsibilitiesAndAchievements", [])
            for resp in responsibilities:
                story.append(Paragraph(resp, styles['TemplateBullet'], bulletText='•'))

            if i < len(experience_list) - 1:
                story.append(Spacer(1, 0.05*inch))
            else:
                story.append(Spacer(1, 0.05*inch))

    # --- Projects Section ---
    projects_list = data.get("Projects", [])
    if projects_list:
        story.append(Paragraph("Projects", styles['TemplateSectionTitle']))
        for i, proj in enumerate(projects_list):
            left_col_text = proj.get("ProjectName", "")
            right_col_text = proj.get("DatesOrDuration", "")
            date_paragraph = Paragraph(right_col_text, styles['DateLocation']) if right_col_text and right_col_text.strip() and right_col_text.lower() != "dates not specified" else Paragraph("", styles['DateLocation'])

            header_table_data = [[Paragraph(left_col_text, styles['EntryHeader']), date_paragraph]]
            header_table = Table(header_table_data, colWidths=['75%', '25%'])
            header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
            story.append(header_table)

            if proj.get("Description"):
                story.append(Paragraph(proj.get("Description"), styles['EntrySubHeader']))

            contributions = proj.get("KeyContributionsOrTechnologiesUsed", [])
            for contrib in contributions:
                story.append(Paragraph(contrib, styles['TemplateBullet'], bulletText='•'))

            if i < len(projects_list) - 1:
                story.append(Spacer(1, 0.05*inch))
            else:
                story.append(Spacer(1, 0.05*inch))

    # --- Skills Section ---
    skills_data = data.get("Skills", [])
    if skills_data:
        story.append(Paragraph("Skills", styles['TemplateSectionTitle']))
        for skill_item in skills_data:
            story.append(Paragraph(skill_item.get("SkillCategory", "Skills"), styles['SkillsCategory']))
            for skill_detail in skill_item.get("Skill", []):
                story.append(Paragraph(skill_detail, styles['TemplateBullet'], bulletText='•'))
        story.append(Spacer(1, 0.05*inch))

    # --- Certifications Section ---
    certifications_list = data.get("Certifications", [])
    if certifications_list:
        story.append(Paragraph("Certifications", styles['TemplateSectionTitle']))
        for cert in certifications_list:
            cert_text = f"{cert.get('CertificationName', '')}"
            if cert.get('IssuingOrganization'):
                cert_text += f" - {cert.get('IssuingOrganization', '')}"
            story.append(Paragraph(cert_text, styles['SubDetail']))
        story.append(Spacer(1, 0.05*inch))

    # --- Awards and Recognition Section ---
    awards_list = data.get("AwardsAndRecognition", [])
    if awards_list:
        story.append(Paragraph("Awards and Recognition", styles['TemplateSectionTitle']))
        for award in awards_list:
            award_text = f"{award.get('AwardName', '')}"
            if award.get('AwardingBody'):
                award_text += f" ({award.get('AwardingBody', '')})"
            story.append(Paragraph(award_text, styles['SubDetail']))
        story.append(Spacer(1, 0.05*inch))

    # --- Volunteer Experience Section ---
    volunteer_list = data.get("VolunteerExperience", [])
    if volunteer_list:
        story.append(Paragraph("Volunteer Experience", styles['TemplateSectionTitle']))
        for i, vol_entry in enumerate(volunteer_list):
            org_name = vol_entry.get("OrganizationName", "")
            dates = vol_entry.get("Dates", "")
            date_paragraph = Paragraph(dates, styles['DateLocation']) if dates and dates.strip() and dates.lower() != "dates not specified" else Paragraph("", styles['DateLocation'])

            header_table_data = [[Paragraph(org_name, styles['EntryHeader']), date_paragraph]]
            header_table = Table(header_table_data, colWidths=['75%', '25%'])
            header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
            story.append(header_table)

            if vol_entry.get("Role"):
                 story.append(Paragraph(vol_entry.get("Role"), styles['EntrySubHeader']))
            if vol_entry.get("Description") and vol_entry.get("Description").strip():
                 story.append(Paragraph(vol_entry.get("Description"), styles['SubDetail']))

            if i < len(volunteer_list) - 1:
                story.append(Spacer(1, 0.05*inch))
            else: # No spacer after the very last entry in the document perhaps, or a smaller one
                pass # story.append(Spacer(1, 0.05*inch))

    try:
        doc.build(story)
        print(f"CV generated successfully: {filename}")
    except Exception as e:
        print(f"Error building PDF: {e}")
        import traceback
        traceback.print_exc()

def generate_cv_pdf_from_json_string(cv_json_string: str):
    """
    Parses a JSON string containing CV data and generates a PDF CV.
    """
    print("Attempting to parse CV JSON string...")
    parsed_cv_data = parse_cv_json(cv_json_string)

    if parsed_cv_data:
        print("Successfully parsed CV data. Attempting to generate PDF...")
        create_cv_pdf(parsed_cv_data, filename_prefix="tailored_cv") # Using "tailored_cv" as prefix
    else:
        print("Could not parse CV data from string. PDF not generated.")

# --- Main Execution ---
if __name__ == "__main__":
    print("Please paste your JSON CV data below.")
    print("To finish input, press Ctrl+D (on Linux/macOS) or Ctrl+Z then Enter (on Windows).")
    print("------------------------------------------------------------------------------------")

    input_lines = []
    while True:
        try:
            line = input()
            input_lines.append(line)
        except EOFError:
            break

    cv_json_text_content = "\n".join(input_lines)

    if not cv_json_text_content.strip():
        print("No input received. Exiting.")
    else:
        # Call the new function to handle PDF generation
        generate_cv_pdf_from_json_string(cv_json_text_content)
