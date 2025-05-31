# cv_tailor_project/app/pdf_generator.py
import json
import os
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black, navy, darkslategray, gray, lightgrey
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import traceback

# --- Font Setup ---
# Attempt to register Calibri, fall back to Helvetica if not found (common in server environments)
FONT_NAME = 'Helvetica'
FONT_NAME_BOLD = 'Helvetica-Bold'
FONT_NAME_ITALIC = 'Helvetica-Oblique'
FONT_NAME_BOLD_ITALIC = 'Helvetica-BoldOblique' # Added for completeness

try:
    # In a server environment, these paths are unlikely to exist.
    # Consider bundling fonts or using ReportLab's standard fonts.
    # For now, we'll keep the try-except but default to Helvetica which is standard.
    # If Calibri is essential, it would need to be bundled with the application.
    # Example of trying to load Calibri (adjust paths if fonts are bundled):
    # pdfmetrics.registerFont(TTFont('Calibri', 'fonts/calibri.ttf'))
    # pdfmetrics.registerFont(TTFont('Calibri-Bold', 'fonts/calibrib.ttf'))
    # pdfmetrics.registerFont(TTFont('Calibri-Italic', 'fonts/calibrii.ttf'))
    # pdfmetrics.registerFont(TTFont('Calibri-BoldItalic', 'fonts/calibriz.ttf'))
    # FONT_NAME = 'Calibri'
    # FONT_NAME_BOLD = 'Calibri-Bold'
    # FONT_NAME_ITALIC = 'Calibri-Italic'
    # FONT_NAME_BOLD_ITALIC = 'Calibri-BoldItalic'
    pass # Keeping Helvetica as default for wider compatibility
except Exception as e:
    print(f"Font loading warning (using Helvetica): {e}")
    # Fallback to Helvetica is already set, so no action needed here.

def parse_cv_json(json_text_block: str) -> dict | None:
    """
    Parses the JSON text block of CV data into a Python dictionary.
    Expects the main CV data to be under a "CV" key, but falls back to using the whole object.
    """
    try:
        data = json.loads(json_text_block)
        if isinstance(data, dict) and "CV" in data and isinstance(data["CV"], dict):
            return data["CV"]
        elif isinstance(data, dict) : # If "CV" key is missing, but it's a dict
            print("Warning: 'CV' root key not found in JSON. Assuming the entire JSON object is the CV data.")
            return data
        else:
            print("Error: Parsed JSON is not a dictionary or 'CV' key does not contain a dictionary.")
            return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON in parse_cv_json: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error in parse_cv_json: {e}")
        return None

def create_cv_pdf(data: dict, output_filepath: str) -> bool:
    """
    Generates a PDF CV from the provided data dictionary and saves it to output_filepath.
    Returns True on success, False on failure.
    """
    if not data:
        print("No valid data provided to create_cv_pdf. PDF not generated.")
        return False
    if not isinstance(data, dict):
        print("Error: Data for create_cv_pdf must be a dictionary.")
        return False

    doc = SimpleDocTemplate(output_filepath, pagesize=(8.5 * inch, 11 * inch),
                            leftMargin=0.6*inch, rightMargin=0.6*inch,
                            topMargin=0.4*inch, bottomMargin=0.4*inch)
    styles = getSampleStyleSheet()

    # --- Define Styles ---
    styles.add(ParagraphStyle(name='NameStyle', fontName=FONT_NAME_BOLD, fontSize=20, alignment=TA_CENTER, spaceAfter=0.03*inch, textColor=black, leading=24))
    styles.add(ParagraphStyle(name='ContactStyle', fontName=FONT_NAME, fontSize=9.5, alignment=TA_CENTER, spaceAfter=0.1*inch, textColor=black, leading=11))
    styles.add(ParagraphStyle(name='SummaryStyle', fontName=FONT_NAME, fontSize=9.5, textColor=black, leading=12, spaceBefore=0.05*inch, spaceAfter=0.1*inch, alignment=TA_JUSTIFY, firstLineIndent=0.2*inch))
    styles.add(ParagraphStyle(name='TemplateSectionTitle', fontName=FONT_NAME_BOLD, fontSize=10.5, textColor=black, spaceBefore=0.1*inch, spaceAfter=0.05*inch, alignment=TA_LEFT, keepWithNext=1))
    styles.add(ParagraphStyle(name='EntryHeader', fontName=FONT_NAME_BOLD, fontSize=9.5, textColor=black, spaceAfter=0.01*inch, alignment=TA_LEFT, leading=11))
    styles.add(ParagraphStyle(name='EntrySubHeader', fontName=FONT_NAME, fontSize=9.5, textColor=black, spaceAfter=0.01*inch, alignment=TA_LEFT, leading=11))
    styles.add(ParagraphStyle(name='DateLocation', fontName=FONT_NAME_ITALIC, fontSize=9.5, textColor=gray, alignment=TA_RIGHT, leading=11)) # Changed to italic
    styles.add(ParagraphStyle(name='SubDetail', fontName=FONT_NAME, fontSize=9.5, textColor=black, leading=11, spaceAfter=0.02*inch, leftIndent=0.05*inch))
    styles.add(ParagraphStyle(name='TemplateBullet', fontName=FONT_NAME, fontSize=9.5, textColor=black, leading=12, spaceBefore=0.01*inch, leftIndent=0.2*inch, bulletIndent=0.08*inch, firstLineIndent=0))
    styles.add(ParagraphStyle(name='SkillsCategory', fontName=FONT_NAME_BOLD, fontSize=9.5, textColor=black, leading=11, spaceBefore=0.03*inch, spaceAfter=0.01*inch))
    styles.add(ParagraphStyle(name='SkillsText', fontName=FONT_NAME, fontSize=9.5, textColor=black, leading=11, leftIndent=0.15*inch)) # This style seems unused in original, kept for now

    story = []

    # --- Personal Information ---
    personal_info = data.get("PersonalInformation", {})
    if isinstance(personal_info, dict):
        story.append(Paragraph(personal_info.get("Name", "N/A"), styles['NameStyle']))
        contact_parts = [personal_info.get("PhoneNumber"), personal_info.get("EmailAddress"), personal_info.get("WebsiteOrLinkedInURL")]
        contact_info = " / ".join(filter(None, contact_parts))
        if not contact_info: contact_info = "Contact information not provided"
        story.append(Paragraph(contact_info, styles['ContactStyle']))
        story.append(HRFlowable(width="100%", thickness=0.5, color=lightgrey, spaceBefore=0, spaceAfter=0.08*inch))

    # --- Summary/Objective ---
    summary_data = data.get("SummaryOrObjective", {})
    if isinstance(summary_data, dict) and summary_data.get("Statement"):
        story.append(Paragraph("Summary", styles['TemplateSectionTitle']))
        story.append(Paragraph(summary_data["Statement"], styles['SummaryStyle']))

    # --- Generic Section Renderer ---
    def render_section(title, items_data, render_item_func, section_key):
        if isinstance(items_data, list) and items_data:
            story.append(Paragraph(title, styles['TemplateSectionTitle']))
            for i, item in enumerate(items_data):
                if isinstance(item, dict): # Ensure item is a dict before processing
                     render_item_func(item)
                     if i < len(items_data) - 1: story.append(Spacer(1, 0.05*inch))
                else:
                    print(f"Warning: Item in section '{section_key}' is not a dictionary: {item}")
            story.append(Spacer(1, 0.05*inch)) # Spacer after the whole section

    def render_education_item(entry):
        left_col_text = f"{entry.get('InstitutionName', 'N/A')}"
        if entry.get('Location'): left_col_text += f", {entry.get('Location', '')}"
        right_col_text = entry.get('GraduationDateOrExpected', '')
        date_p = Paragraph(right_col_text, styles['DateLocation']) if right_col_text and str(right_col_text).strip().lower() not in ["", "dates not specified"] else Paragraph("", styles['DateLocation'])
        header_table = Table([[Paragraph(left_col_text, styles['EntryHeader']), date_p]], colWidths=['75%', '25%'], style=[('VALIGN', (0,0), (-1,-1), 'TOP')])
        story.append(header_table)
        degree_major = f"{entry.get('DegreeEarned', 'N/A')}"
        if entry.get('MajorOrFieldOfStudy'): degree_major += f" - {entry.get('MajorOrFieldOfStudy', '')}"
        story.append(Paragraph(degree_major, styles['EntrySubHeader']))
        for honor in entry.get("HonorsAndAwardsOrRelevantCoursework", []):
            story.append(Paragraph(f"<i>{honor}</i>" if "thesis:" in str(honor).lower() else str(honor), styles['SubDetail']))

    def render_experience_item(job):
        left_col_text = f"{job.get('CompanyName', 'N/A')}"
        if job.get('Location'): left_col_text += f", {job.get('Location', '')}"
        right_col_text = job.get("EmploymentDates", "")
        date_p = Paragraph(right_col_text, styles['DateLocation']) if right_col_text and str(right_col_text).strip().lower() not in ["", "dates not specified"] else Paragraph("", styles['DateLocation'])
        header_table = Table([[Paragraph(left_col_text, styles['EntryHeader']), date_p]], colWidths=['75%', '25%'], style=[('VALIGN', (0,0), (-1,-1), 'TOP')])
        story.append(header_table)
        story.append(Paragraph(job.get("JobTitle", "N/A"), styles['EntrySubHeader']))
        for resp in job.get("ResponsibilitiesAndAchievements", []):
            story.append(Paragraph(str(resp), styles['TemplateBullet'], bulletText='•'))

    def render_project_item(proj):
        left_col_text = proj.get("ProjectName", "N/A")
        right_col_text = proj.get("DatesOrDuration", "")
        date_p = Paragraph(right_col_text, styles['DateLocation']) if right_col_text and str(right_col_text).strip().lower() not in ["", "dates not specified"] else Paragraph("", styles['DateLocation'])
        header_table = Table([[Paragraph(left_col_text, styles['EntryHeader']), date_p]], colWidths=['75%', '25%'], style=[('VALIGN', (0,0), (-1,-1), 'TOP')])
        story.append(header_table)
        if proj.get("Description"): story.append(Paragraph(proj.get("Description"), styles['EntrySubHeader']))
        for contrib in proj.get("KeyContributionsOrTechnologiesUsed", []):
            story.append(Paragraph(str(contrib), styles['TemplateBullet'], bulletText='•'))

    def render_volunteer_item(vol_entry):
        org_name = vol_entry.get("OrganizationName", "N/A")
        dates = vol_entry.get("Dates", "")
        date_p = Paragraph(dates, styles['DateLocation']) if dates and str(dates).strip().lower() not in ["", "dates not specified"] else Paragraph("", styles['DateLocation'])
        header_table = Table([[Paragraph(org_name, styles['EntryHeader']), date_p]], colWidths=['75%', '25%'], style=[('VALIGN', (0,0), (-1,-1), 'TOP')])
        story.append(header_table)
        if vol_entry.get("Role"): story.append(Paragraph(vol_entry.get("Role"), styles['EntrySubHeader']))
        if vol_entry.get("Description"): story.append(Paragraph(vol_entry.get("Description"), styles['SubDetail']))

    # --- Render Sections ---
    render_section("Education", data.get("Education", []), render_education_item, "Education")
    render_section("Professional Experience", data.get("ProfessionalExperience", []), render_experience_item, "ProfessionalExperience")
    render_section("Projects", data.get("Projects", []), render_project_item, "Projects")

    # --- Skills Section ---
    skills_data = data.get("Skills", [])
    if isinstance(skills_data, list) and skills_data:
        story.append(Paragraph("Skills", styles['TemplateSectionTitle']))
        for skill_item in skills_data:
            if isinstance(skill_item, dict): # Ensure skill_item is a dict
                story.append(Paragraph(skill_item.get("SkillCategory", "General Skills"), styles['SkillsCategory']))
                skills_list = skill_item.get("Skill", [])
                if isinstance(skills_list, list):
                    for skill_detail in skills_list:
                        story.append(Paragraph(str(skill_detail), styles['TemplateBullet'], bulletText='•'))
                else:
                    print(f"Warning: 'Skill' field in Skills section is not a list: {skills_list}")
            else:
                print(f"Warning: Item in Skills section is not a dictionary: {skill_item}")
        story.append(Spacer(1, 0.05*inch))

    # --- Certifications & Awards (simplified rendering) ---
    def render_simple_list_section(title, items_data, fields, section_key):
        if isinstance(items_data, list) and items_data:
            story.append(Paragraph(title, styles['TemplateSectionTitle']))
            for item in items_data:
                 if isinstance(item, dict): # Ensure item is a dict
                    text_parts = [str(item.get(f)) for f in fields if item.get(f)]
                    story.append(Paragraph(" - ".join(text_parts), styles['SubDetail']))
                 else:
                    print(f"Warning: Item in section '{section_key}' is not a dictionary: {item}")
            story.append(Spacer(1, 0.05*inch))

    render_simple_list_section("Certifications", data.get("Certifications", []), ["CertificationName", "IssuingOrganization"], "Certifications")
    render_simple_list_section("Awards and Recognition", data.get("AwardsAndRecognition", []), ["AwardName", "AwardingBody"], "AwardsAndRecognition")
    render_section("Volunteer Experience", data.get("VolunteerExperience", []), render_volunteer_item, "VolunteerExperience")

    try:
        doc.build(story)
        print(f"CV generated successfully: {output_filepath}")
        return True
    except Exception as e:
        print(f"Error building PDF at {output_filepath}: {e}")
        print(traceback.format_exc())
        return False

def generate_cv_pdf_from_json_string(cv_json_string: str, output_filepath: str) -> bool:
    """
    Parses a JSON string containing CV data and generates a PDF CV, saving it to output_filepath.
    Returns True on success, False on failure.
    """
    if not cv_json_string:
        print("Error: Empty CV JSON string provided to generate_cv_pdf_from_json_string.")
        return False
    if not output_filepath:
        print("Error: No output filepath provided to generate_cv_pdf_from_json_string.")
        return False

    print(f"Attempting to parse CV JSON string for PDF generation at {output_filepath}...")
    parsed_cv_data = parse_cv_json(cv_json_string)

    if parsed_cv_data:
        print(f"Successfully parsed CV data. Attempting to generate PDF: {output_filepath}")
        return create_cv_pdf(parsed_cv_data, output_filepath)
    else:
        print(f"Could not parse CV data from string. PDF not generated for {output_filepath}.")
        return False

# --- Main Execution (for testing this module directly) ---
# This part is for testing and won't be used by the Flask app.
if __name__ == "__main__":
    print("Testing pdf_generator.py...")
    # Create a dummy CV_format.json for testing if it's not present
    # This should ideally use the actual CV_format.json from the project root for consistency.
    # For module testing, it's better to have a dedicated test_cv_data.json

    # Example test JSON data string (ensure this matches your CV_format.json structure)
    example_cv_json_str = """
    {
      "CV": {
        "PersonalInformation": { "Name": "Test User", "EmailAddress": "test@example.com" },
        "SummaryOrObjective": { "Statement": "This is a test summary." },
        "Education": [ { "InstitutionName": "Test University", "DegreeEarned": "BS CS" } ],
        "ProfessionalExperience": [ { "CompanyName": "TestCo", "JobTitle": "Tester" } ],
        "Skills": [ { "SkillCategory": "Programming", "Skill": ["Python", "ReportLab"] } ]
      }
    }
    """
    test_output_dir = "instance/generated_pdfs_test"
    if not os.path.exists(test_output_dir):
        os.makedirs(test_output_dir)
    test_output_filepath = os.path.join(test_output_dir, "test_generated_cv.pdf")

    print(f"Generating test PDF at: {test_output_filepath}")
    success = generate_cv_pdf_from_json_string(example_cv_json_str, test_output_filepath)

    if success:
        print(f"Test PDF generated successfully: {test_output_filepath}")
    else:
        print("Test PDF generation failed.")
