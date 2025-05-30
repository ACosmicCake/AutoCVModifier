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
        # The root of the provided JSON is "CV", so we access its content.
        if "CV" in data:
            return data["CV"]
        else:
            # If the "CV" key is missing, but it's a valid JSON,
            # perhaps the user pasted only the content of "CV".
            # This is a fallback, ideally the input matches the full structure.
            print("Warning: 'CV' root key not found in JSON. Assuming pasted content is the CV data itself.")
            return data 
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return None

# --- PDF Generation Logic (Adapted for new JSON structure) ---
def create_cv_pdf(data, filename_prefix="cv"):
    if not data: # Check if data is None (e.g., due to JSON parsing error)
        print("No valid data to generate PDF. Exiting PDF creation.")
        return

    personal_info = data.get("PersonalInformation", {})
    applicant_name_data = personal_info.get("Name", "Applicant")
    safe_filename = "".join(c if c.isalnum() else "_" for c in applicant_name_data)
    filename = f"{filename_prefix}_{safe_filename}.pdf"

    doc = SimpleDocTemplate(filename, pagesize=(8.5 * inch, 11 * inch),
                            leftMargin=0.75*inch, rightMargin=0.75*inch,
                            topMargin=0.5*inch, bottomMargin=0.5*inch) 
    
    styles = getSampleStyleSheet()
    
    # --- Define Styles (can be reused/adapted from previous version) ---
    styles.add(ParagraphStyle(name='NameStyle', fontName=FONT_NAME_BOLD, fontSize=22, alignment=TA_CENTER, spaceAfter=0.05*inch, textColor=black, leading=26))
    styles.add(ParagraphStyle(name='ContactStyle', fontName=FONT_NAME, fontSize=10, alignment=TA_CENTER, spaceAfter=0.15*inch, textColor=black, leading=12))
    styles.add(ParagraphStyle(name='SummaryStyle', fontName=FONT_NAME, fontSize=10, textColor=black, leading=14, spaceBefore=0.1*inch, spaceAfter=0.15*inch, alignment=TA_JUSTIFY, firstLineIndent=0.25*inch))
    
    styles.add(ParagraphStyle(name='TemplateSectionTitle', fontName=FONT_NAME_BOLD, fontSize=11, textColor=black, spaceBefore=0.15*inch, spaceAfter=0.1*inch, alignment=TA_LEFT, keepWithNext=1))
    
    styles.add(ParagraphStyle(name='EntryHeader', fontName=FONT_NAME_BOLD, fontSize=10, textColor=black, spaceAfter=0.02*inch, alignment=TA_LEFT, leading=12))
    styles.add(ParagraphStyle(name='EntrySubHeader', fontName=FONT_NAME, fontSize=10, textColor=black, spaceAfter=0.02*inch, alignment=TA_LEFT, leading=12)) # For degree, job title etc.
    
    styles.add(ParagraphStyle(name='DateLocation', fontName=FONT_NAME, fontSize=10, textColor=gray, alignment=TA_RIGHT, leading=12)) # Matched template's grayed out dates
    
    styles.add(ParagraphStyle(name='SubDetail', fontName=FONT_NAME, fontSize=10, textColor=black, leading=12, spaceAfter=0.03*inch, leftIndent=0.05*inch)) # For honors, thesis, etc. slightly indented
    
    styles.add(ParagraphStyle(name='TemplateBullet', fontName=FONT_NAME, fontSize=10, textColor=black, leading=14, spaceBefore=0.02*inch, leftIndent=0.25*inch, bulletIndent=0.1*inch, firstLineIndent=0))

    styles.add(ParagraphStyle(name='SkillsCategory', fontName=FONT_NAME_BOLD, fontSize=10, textColor=black, leading=12, spaceBefore=0.05*inch, spaceAfter=0.02*inch))
    styles.add(ParagraphStyle(name='SkillsText', fontName=FONT_NAME, fontSize=10, textColor=black, leading=12, leftIndent=0.15*inch))


    story = []

    # --- Personal Information ---
    if personal_info:
        story.append(Paragraph(personal_info.get("Name", ""), styles['NameStyle']))
        contact_parts = [personal_info.get("PhoneNumber"), personal_info.get("EmailAddress"), personal_info.get("WebsiteOrLinkedInURL")]
        contact_info = " / ".join(filter(None, contact_parts))
        story.append(Paragraph(contact_info, styles['ContactStyle']))
        story.append(HRFlowable(width="100%", thickness=0.5, color=lightgrey, spaceBefore=0, spaceAfter=0.1*inch))

    # --- Summary/Objective ---
    summary_data = data.get("SummaryOrObjective", {})
    if summary_data.get("Statement"):
        story.append(Paragraph("Summary", styles['TemplateSectionTitle']))
        story.append(Paragraph(summary_data["Statement"], styles['SummaryStyle']))
        story.append(Spacer(1, 0.1*inch))

    # --- Education Section ---
    education_list = data.get("Education", [])
    if education_list:
        story.append(Paragraph("Education", styles['TemplateSectionTitle']))
        for entry in education_list:
            left_col_text = f"{entry.get('InstitutionName', '')}"
            if entry.get('Location'):
                left_col_text += f", {entry.get('Location', '')}"
            
            right_col_text = entry.get('GraduationDateOrExpected', '')
            
            header_table_data = [[Paragraph(left_col_text, styles['EntryHeader']), Paragraph(right_col_text, styles['DateLocation'])]]
            header_table = Table(header_table_data, colWidths=['75%', '25%'])
            header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
            story.append(header_table)

            degree_major = f"{entry.get('DegreeEarned', '')}"
            if entry.get('MajorOrFieldOfStudy'):
                 degree_major += f" - {entry.get('MajorOrFieldOfStudy', '')}"
            story.append(Paragraph(degree_major, styles['EntrySubHeader']))
            
            honors = entry.get("HonorsAndAwardsOrRelevantCoursework", [])
            for honor in honors:
                # Check if it's a thesis to style it slightly differently if needed
                if "Thesis:" in honor:
                    story.append(Paragraph(f"<i>{honor}</i>", styles['SubDetail'])) # Italicize thesis
                else:
                    story.append(Paragraph(honor, styles['SubDetail']))
            story.append(Spacer(1, 0.1*inch))

    # --- Professional Experience Section ---
    experience_list = data.get("ProfessionalExperience", [])
    if experience_list:
        story.append(Paragraph("Professional Experience", styles['TemplateSectionTitle']))
        for job in experience_list:
            left_col_text = f"{job.get('CompanyName', '')}"
            if job.get('Location'):
                 left_col_text += f", {job.get('Location', '')}"
            
            right_col_text = job.get("EmploymentDates", "")
            
            header_table_data = [[Paragraph(left_col_text, styles['EntryHeader']), Paragraph(right_col_text, styles['DateLocation'])]]
            header_table = Table(header_table_data, colWidths=['75%', '25%'])
            header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
            story.append(header_table)

            story.append(Paragraph(job.get("JobTitle", ""), styles['EntrySubHeader']))

            responsibilities = job.get("ResponsibilitiesAndAchievements", [])
            for resp in responsibilities:
                story.append(Paragraph(resp, styles['TemplateBullet'], bulletText='•'))
            story.append(Spacer(1, 0.1*inch))
            
    # --- Projects Section ---
    projects_list = data.get("Projects", [])
    if projects_list:
        story.append(Paragraph("Projects", styles['TemplateSectionTitle']))
        for proj in projects_list:
            left_col_text = proj.get("ProjectName", "")
            right_col_text = proj.get("DatesOrDuration", "")

            header_table_data = [[Paragraph(left_col_text, styles['EntryHeader']), Paragraph(right_col_text, styles['DateLocation'])]]
            header_table = Table(header_table_data, colWidths=['75%', '25%'])
            header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
            story.append(header_table)
            
            if proj.get("Description"):
                story.append(Paragraph(proj.get("Description"), styles['EntrySubHeader'])) # Using EntrySubHeader for project description

            contributions = proj.get("KeyContributionsOrTechnologiesUsed", [])
            for contrib in contributions:
                story.append(Paragraph(contrib, styles['TemplateBullet'], bulletText='•'))
            story.append(Spacer(1, 0.1*inch))

    # --- Skills Section ---
    skills_data = data.get("Skills", [])
    if skills_data:
        story.append(Paragraph("Skills", styles['TemplateSectionTitle']))
        for skill_item in skills_data:
            story.append(Paragraph(skill_item.get("SkillCategory", "Skills"), styles['SkillsCategory']))
            for skill_detail in skill_item.get("Skill", []):
                story.append(Paragraph(skill_detail, styles['TemplateBullet'], bulletText='•')) # Using bullets for individual skills
        story.append(Spacer(1, 0.1*inch))

    # --- Certifications Section ---
    certifications_list = data.get("Certifications", [])
    if certifications_list:
        story.append(Paragraph("Certifications", styles['TemplateSectionTitle']))
        for cert in certifications_list:
            cert_text = f"{cert.get('CertificationName', '')}"
            if cert.get('IssuingOrganization'):
                cert_text += f" - {cert.get('IssuingOrganization', '')}"
            # DateObtained is often null, so not explicitly adding it unless present
            story.append(Paragraph(cert_text, styles['SubDetail'])) # Reusing SubDetail style
        story.append(Spacer(1, 0.1*inch))

    # --- Awards and Recognition Section ---
    awards_list = data.get("AwardsAndRecognition", [])
    if awards_list:
        story.append(Paragraph("Awards and Recognition", styles['TemplateSectionTitle']))
        for award in awards_list:
            award_text = f"{award.get('AwardName', '')}"
            if award.get('AwardingBody'):
                award_text += f" ({award.get('AwardingBody', '')})"
            story.append(Paragraph(award_text, styles['SubDetail']))
        story.append(Spacer(1, 0.1*inch))

    # --- Volunteer Experience Section ---
    volunteer_list = data.get("VolunteerExperience", [])
    if volunteer_list:
        story.append(Paragraph("Volunteer Experience", styles['TemplateSectionTitle']))
        for vol_entry in volunteer_list:
            org_name = vol_entry.get("OrganizationName", "")
            dates = vol_entry.get("Dates", "")
            
            header_table_data = [[Paragraph(org_name, styles['EntryHeader']), Paragraph(dates, styles['DateLocation'])]]
            header_table = Table(header_table_data, colWidths=['75%', '25%'])
            header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
            story.append(header_table)

            if vol_entry.get("Role"):
                 story.append(Paragraph(vol_entry.get("Role"), styles['EntrySubHeader']))
            if vol_entry.get("Description"): # Though empty in example, good to handle
                 story.append(Paragraph(vol_entry.get("Description"), styles['SubDetail']))
            story.append(Spacer(1, 0.1*inch))
    
    try:
        doc.build(story)
        print(f"CV generated successfully: {filename}")
    except Exception as e:
        print(f"Error building PDF: {e}")
        import traceback
        traceback.print_exc() # For more detailed error during development

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
        # No need to strip '[ [' and ']' anymore as input is expected to be valid JSON
        parsed_cv_data = parse_cv_json(cv_json_text_content)
        
        if parsed_cv_data: # Proceed only if parsing was successful
            # For debugging the parser:
            # print("\n--- Parsed Data (for debugging) ---")
            # print(json.dumps(parsed_cv_data, indent=2, ensure_ascii=False)) # ensure_ascii=False for non-ASCII names
            # print("-----------------------------------\n")
            create_cv_pdf(parsed_cv_data)
        else:
            print("Could not parse CV data. PDF not generated.")

