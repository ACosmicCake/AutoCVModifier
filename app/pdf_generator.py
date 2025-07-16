# cv_tailor_project/app/pdf_generator.py
import json
import os
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black, navy, darkslategray, gray, lightgrey
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import traceback

# --- Font Setup ---
FONT_NAME = 'Helvetica'
FONT_NAME_BOLD = 'Helvetica-Bold'
FONT_NAME_ITALIC = 'Helvetica-Oblique'
FONT_NAME_BOLD_ITALIC = 'Helvetica-BoldOblique'

try:
    pass # Keeping Helvetica as default
except Exception as e:
    print(f"Font loading warning (using Helvetica): {e}")

def parse_cv_json(json_text_block: str) -> dict | None:
    """
    Parses the JSON text block of CV data into a Python dictionary.
    """
    try:
        data = json.loads(json_text_block)
        if isinstance(data, dict) and "CV" in data and isinstance(data["CV"], dict):
            return data["CV"]
        elif isinstance(data, dict) :
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

    # --- Define Styles (with compactness adjustments for skills) ---
    styles.add(ParagraphStyle(name='NameStyle', fontName=FONT_NAME_BOLD, fontSize=20, alignment=TA_CENTER, spaceAfter=0.03*inch, textColor=black, leading=24))
    styles.add(ParagraphStyle(name='ContactStyle', fontName=FONT_NAME, fontSize=9.5, alignment=TA_CENTER, spaceAfter=0.1*inch, textColor=black, leading=11))
    styles.add(ParagraphStyle(name='SummaryStyle', fontName=FONT_NAME, fontSize=9.5, textColor=black, leading=12, spaceBefore=0.05*inch, spaceAfter=0.1*inch, alignment=TA_JUSTIFY, firstLineIndent=0.2*inch))
    styles.add(ParagraphStyle(name='TemplateSectionTitle', fontName=FONT_NAME_BOLD, fontSize=10.5, textColor=black, spaceBefore=0.1*inch, spaceAfter=0.05*inch, alignment=TA_LEFT, keepWithNext=1))
    styles.add(ParagraphStyle(name='EntryHeader', fontName=FONT_NAME_BOLD, fontSize=9.5, textColor=black, spaceAfter=0.01*inch, alignment=TA_LEFT, leading=11))
    styles.add(ParagraphStyle(name='EntrySubHeader', fontName=FONT_NAME, fontSize=9.5, textColor=black, spaceAfter=0.01*inch, alignment=TA_LEFT, leading=11))
    styles.add(ParagraphStyle(name='DateLocation', fontName=FONT_NAME_ITALIC, fontSize=9.5, textColor=gray, alignment=TA_RIGHT, leading=11))
    styles.add(ParagraphStyle(name='SubDetail', fontName=FONT_NAME, fontSize=9.5, textColor=black, leading=11, spaceAfter=0.02*inch, leftIndent=0.05*inch))
    styles.add(ParagraphStyle(name='TemplateBullet', fontName=FONT_NAME, fontSize=9.5, textColor=black, leading=12, spaceBefore=0.01*inch, leftIndent=0.2*inch, bulletIndent=0.08*inch, firstLineIndent=0))
    # SkillsCategory style made more compact
    styles.add(ParagraphStyle(name='SkillsCategory', fontName=FONT_NAME_BOLD, fontSize=9.5, textColor=black, leading=11, spaceBefore=0.02*inch, spaceAfter=0.005*inch, keepWithNext=1))
    styles.add(ParagraphStyle(name='SkillInTableStyle', fontName=FONT_NAME, fontSize=9.5, textColor=black, leading=11, alignment=TA_LEFT))

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
        # Wrap summary and its title together
        summary_block = [
            Paragraph("Summary", styles['TemplateSectionTitle']),
            Paragraph(summary_data["Statement"], styles['SummaryStyle'])
        ]
        story.append(KeepTogether(summary_block))


    # --- Generic Section Renderer ---
    def render_section(title, items_data, render_item_func, section_key):
        if isinstance(items_data, list) and items_data:
            for i, item in enumerate(items_data):
                if isinstance(item, dict):
                     # Pass the title only to the first item's render function
                     section_title = title if i == 0 else None
                     render_item_func(item, section_title=section_title)
                     if i < len(items_data) - 1: story.append(Spacer(1, 0.05*inch))
                else:
                    print(f"Warning: Item in section '{section_key}' is not a dictionary: {item}")
            story.append(Spacer(1, 0.05*inch))

    def render_education_item(entry, section_title=None):
        entry_flowables = []
        if section_title:
            entry_flowables.append(Paragraph(section_title, styles['TemplateSectionTitle']))

        left_col_text = f"{entry.get('InstitutionName', 'N/A')}"
        if entry.get('Location'): left_col_text += f", {entry.get('Location', '')}"
        right_col_text = entry.get('GraduationDateOrExpected', '')
        date_p = Paragraph(right_col_text, styles['DateLocation']) if right_col_text and str(right_col_text).strip().lower() not in ["", "dates not specified"] else Paragraph("", styles['DateLocation'])
        header_table = Table([[Paragraph(left_col_text, styles['EntryHeader']), date_p]], colWidths=['75%', '25%'], style=[('VALIGN', (0,0), (-1,-1), 'TOP')])
        entry_flowables.append(header_table)
        degree_major = f"{entry.get('DegreeEarned', 'N/A')}"
        if entry.get('MajorOrFieldOfStudy'): degree_major += f" - {entry.get('MajorOrFieldOfStudy', '')}"
        entry_flowables.append(Paragraph(degree_major, styles['EntrySubHeader']))
        
        # MODIFIED PART FOR EDUCATION ACHIEVEMENTS
        honors = entry.get("HonorsAndAwardsOrRelevantCoursework", [])
        if honors:
            honors_text = ", ".join(honors)
            entry_flowables.append(Paragraph(f"<i>{honors_text}</i>" if "thesis:" in honors_text.lower() else honors_text, styles['SubDetail']))
        
        story.append(KeepTogether(entry_flowables))

    def render_experience_item(job, section_title=None):
        job_flowables = []
        if section_title:
            job_flowables.append(Paragraph(section_title, styles['TemplateSectionTitle']))

        left_col_text = f"{job.get('CompanyName', 'N/A')}"
        if job.get('Location'): left_col_text += f", {job.get('Location', '')}"
        right_col_text = job.get("EmploymentDates", "")
        date_p = Paragraph(right_col_text, styles['DateLocation']) if right_col_text and str(right_col_text).strip().lower() not in ["", "dates not specified"] else Paragraph("", styles['DateLocation'])
        header_table = Table([[Paragraph(left_col_text, styles['EntryHeader']), date_p]], colWidths=['75%', '25%'], style=[('VALIGN', (0,0), (-1,-1), 'TOP')])
        job_flowables.append(header_table)
        job_flowables.append(Paragraph(job.get("JobTitle", "N/A"), styles['EntrySubHeader']))
        for resp in job.get("ResponsibilitiesAndAchievements", []):
            job_flowables.append(Paragraph(str(resp), styles['TemplateBullet'], bulletText='•'))
        story.append(KeepTogether(job_flowables))

    def render_project_item(proj, section_title=None):
        project_flowables = []
        if section_title:
            project_flowables.append(Paragraph(section_title, styles['TemplateSectionTitle']))

        left_col_text = proj.get("ProjectName", "N/A")
        right_col_text = proj.get("DatesOrDuration", "")
        date_p = Paragraph(right_col_text, styles['DateLocation']) if right_col_text and str(right_col_text).strip().lower() not in ["", "dates not specified"] else Paragraph("", styles['DateLocation'])
        header_table = Table([[Paragraph(left_col_text, styles['EntryHeader']), date_p]], colWidths=['75%', '25%'], style=[('VALIGN', (0,0), (-1,-1), 'TOP')])
        project_flowables.append(header_table)
        if proj.get("Description"): project_flowables.append(Paragraph(proj.get("Description"), styles['EntrySubHeader']))
        for contrib in proj.get("KeyContributionsOrTechnologiesUsed", []):
            project_flowables.append(Paragraph(str(contrib), styles['TemplateBullet'], bulletText='•'))
        story.append(KeepTogether(project_flowables))

    def render_volunteer_item(vol_entry, section_title=None):
        volunteer_flowables = []
        if section_title:
            volunteer_flowables.append(Paragraph(section_title, styles['TemplateSectionTitle']))
            
        org_name = vol_entry.get("OrganizationName", "N/A")
        dates = vol_entry.get("Dates", "")
        date_p = Paragraph(dates, styles['DateLocation']) if dates and str(dates).strip().lower() not in ["", "dates not specified"] else Paragraph("", styles['DateLocation'])
        header_table = Table([[Paragraph(org_name, styles['EntryHeader']), date_p]], colWidths=['75%', '25%'], style=[('VALIGN', (0,0), (-1,-1), 'TOP')])
        volunteer_flowables.append(header_table)
        if vol_entry.get("Role"): volunteer_flowables.append(Paragraph(vol_entry.get("Role"), styles['EntrySubHeader']))
        if vol_entry.get("Description"): volunteer_flowables.append(Paragraph(vol_entry.get("Description"), styles['SubDetail']))
        story.append(KeepTogether(volunteer_flowables))

    # --- Render Sections ---
    render_section("Education", data.get("Education", []), render_education_item, "Education")
    render_section("Professional Experience", data.get("ProfessionalExperience", []), render_experience_item, "ProfessionalExperience")
    render_section("Projects", data.get("Projects", []), render_project_item, "Projects")

    # --- Skills Section (5 column layout) ---
    skills_data = data.get("Skills", [])
    if isinstance(skills_data, list) and skills_data:
        skills_block = [Paragraph("Skills", styles['TemplateSectionTitle'])]
        for skill_item in skills_data:
            if isinstance(skill_item, dict):
                skills_block.append(Paragraph(skill_item.get("SkillCategory", "General Skills"), styles['SkillsCategory']))
                
                skills_list = skill_item.get("Skill", [])
                if isinstance(skills_list, list) and skills_list:
                    # Use 5 columns for skills
                    num_cols = 5
                    col_widths = ['20%', '20%', '20%', '20%', '20%']

                    skill_cell_paragraphs = [Paragraph(str(skill_detail), styles['SkillInTableStyle']) for skill_detail in skills_list]

                    table_data = []
                    for i in range(0, len(skill_cell_paragraphs), num_cols):
                        row = skill_cell_paragraphs[i:i+num_cols]
                        while len(row) < num_cols:
                            row.append(Paragraph("", styles['SkillInTableStyle'])) 
                        table_data.append(row)

                    if table_data:
                        skill_table = Table(table_data, colWidths=col_widths, repeatRows=0)
                        
                        # TableStyle with compact padding
                        skills_table_style = TableStyle([
                            ('VALIGN', (0,0), (-1,-1), 'TOP'),
                            ('LEFTPADDING', (0,0), (-1,-1), 1),
                            ('RIGHTPADDING', (0,0), (-1,-1), 3),
                            ('BOTTOMPADDING', (0,0), (-1,-1), 1),
                            ('TOPPADDING', (0,0), (-1,-1), 1),
                        ])
                        skill_table.setStyle(skills_table_style)
                        skills_block.append(skill_table)
                        skills_block.append(Spacer(1, 0.02*inch))
                else:
                    print(f"Warning: 'Skill' field in Skills section is not a list or is empty for category '{skill_item.get('SkillCategory', 'Unknown')}': {skills_list}")
            else:
                print(f"Warning: Item in Skills section is not a dictionary: {skill_item}")
        
        story.append(KeepTogether(skills_block))
        story.append(Spacer(1, 0.05*inch)) 

    # --- Certifications & Awards ---
    def render_simple_list_section(title, items_data, fields, section_key):
        if isinstance(items_data, list) and items_data:
            section_block = [Paragraph(title, styles['TemplateSectionTitle'])]
            for item in items_data:
                 if isinstance(item, dict):
                    text_parts = [str(item.get(f)) for f in fields if item.get(f)]
                    item_paragraph = Paragraph(" - ".join(text_parts), styles['SubDetail'])
                    section_block.append(item_paragraph)
                 else:
                    print(f"Warning: Item in section '{section_key}' is not a dictionary: {item}")
            story.append(KeepTogether(section_block))
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
    Parses a JSON string containing CV data and generates a PDF CV.
    """
    if not cv_json_string:
        print("Error: Empty CV JSON string provided.")
        return False
    if not output_filepath:
        print("Error: No output filepath provided.")
        return False

    parsed_cv_data = parse_cv_json(cv_json_string)

    if parsed_cv_data:
        return create_cv_pdf(parsed_cv_data, output_filepath)
    else:
        print(f"Could not parse CV data. PDF not generated for {output_filepath}.")
        return False

def generate_cover_letter_pdf(cover_letter_text: str, output_filepath: str) -> bool:
    """
    Generates a PDF from a cover letter text string.
    """
    if not cover_letter_text:
        print("Error: Empty cover letter text provided.")
        return False
    if not output_filepath:
        print("Error: No output filepath provided.")
        return False

    try:
        doc = SimpleDocTemplate(output_filepath, pagesize=(8.5 * inch, 11 * inch),
                                leftMargin=1*inch, rightMargin=1*inch,
                                topMargin=1*inch, bottomMargin=1*inch)
        styles = getSampleStyleSheet()
        try:
            styles.add(ParagraphStyle(name='BodyText', fontName=FONT_NAME, fontSize=11, leading=14, spaceAfter=12, alignment=TA_JUSTIFY))
        except KeyError:
            # Style already exists
            pass
        story = [Paragraph(p.strip(), styles['BodyText']) for p in cover_letter_text.split('\n') if p.strip()]
        doc.build(story)
        print(f"Cover letter generated successfully: {output_filepath}")
        return True
    except Exception as e:
        print(f"Error building cover letter PDF at {output_filepath}: {e}")
        print(traceback.format_exc())
        return False

# --- Main Execution (for testing this module directly) ---
if __name__ == "__main__":
    print("Testing pdf_generator.py with variable columns for skills...")
    
    example_cv_json_str = """
    {
      "CV": {
        "PersonalInformation": { 
            "Name": "Johnathan M. Doe", 
            "PhoneNumber": "(555) 123-4567", 
            "EmailAddress": "john.doe@email.com", 
            "WebsiteOrLinkedInURL": "linkedin.com/in/johndoe" 
        },
        "SummaryOrObjective": { 
            "Statement": "Highly motivated and results-oriented Test Engineer with 5+ years of experience in software testing and quality assurance. Proven ability to design, develop, and execute comprehensive test plans and test cases. Adept at identifying, isolating, and tracking bugs to ensure software quality." 
        },
        "Education": [ 
            { 
                "InstitutionName": "State University", "Location": "Anytown, USA",
                "DegreeEarned": "Bachelor of Science", "MajorOrFieldOfStudy": "Computer Science",
                "GraduationDateOrExpected": "May 2018",
                "HonorsAndAwardsOrRelevantCoursework": ["Dean's List (4 semesters)", "Thesis: Advanced Algorithms"]
            }
        ],
        "ProfessionalExperience": [ 
            { 
                "CompanyName": "Tech Solutions Inc.", "Location": "Innovate City, USA",
                "JobTitle": "Senior Test Engineer", "EmploymentDates": "June 2020 - Present",
                "ResponsibilitiesAndAchievements": [
                    "Led a team of 3 QA testers.",
                    "Developed automated test scripts using Selenium and Python, reducing manual testing time by 40%."
                ]
            }
        ],
        "Projects": [
            {
                "ProjectName": "Automated Test Framework", "DatesOrDuration": "2022",
                "Description": "Designed an internal automated testing framework.",
                "KeyContributionsOrTechnologiesUsed": ["Python, PyTest, Selenium WebDriver"]
            },
            {
                "ProjectName": "E-commerce Platform Testing", "DatesOrDuration": "2021",
                "Description": "Lead QA for a new e-commerce platform launch.",
                "KeyContributionsOrTechnologiesUsed": ["JIRA, Selenium, Postman API Testing"]
            }
        ],
        "Skills": [ 
            { 
                "SkillCategory": "Programming Languages", 
                "Skill": ["Python", "Java", "JavaScript", "C#", "SQL", "HTML5", "CSS3"] 
            },
            { 
                "SkillCategory": "Testing Tools & Frameworks", 
                "Skill": ["Selenium WebDriver", "JUnit", "TestNG", "PyTest", "JIRA", "Postman", "Appium", "Cucumber", "Playwright"] 
            },
            {
                "SkillCategory": "Methodologies",
                "Skill": ["Agile", "Scrum", "Waterfall", "DevOps", "Kanban"]
            },
            {
                "SkillCategory": "Databases",
                "Skill": ["MySQL", "PostgreSQL", "MongoDB"]
            },
            {
                "SkillCategory": "Short List Skills",
                "Skill": ["Skill A", "Skill B"]
            },
            {
                "SkillCategory": "Very Long List Skills",
                "Skill": ["Item1", "Item2", "Item3", "Item4", "Item5", "Item6", "Item7", "Item8", "Item9", "Item10", "Item11", "Item12", "Item13"]
            }
        ],
        "Certifications": [{"CertificationName": "ISTQB Certified Tester", "IssuingOrganization": "ISTQB"}],
        "AwardsAndRecognition": [{"AwardName": "Tester of the Year", "AwardingBody": "Tech Solutions Inc."}]
      }
    }
    """
    test_output_dir = "instance/generated_pdfs_test"
    if not os.path.exists(test_output_dir):
        os.makedirs(test_output_dir)
    test_output_filepath = os.path.join(test_output_dir, "test_generated_cv_variable_skills_compact.pdf")

    print(f"Generating test PDF at: {test_output_filepath}")
    success = generate_cv_pdf_from_json_string(example_cv_json_str, test_output_filepath)

    if success:
        print(f"Test PDF generated successfully: {test_output_filepath}")
    else:
        print("Test PDF generation failed.")