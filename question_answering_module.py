from typing import Dict, Any, List

# Assuming ai_core_data_structures.py is in the same directory or accessible in PYTHONPATH
from ai_core_data_structures import (
    IdentifiedFormField,
    QuestionAnsweringResult,
    VisualLocation, # For sample IdentifiedFormField
    PredictedFieldType # For sample IdentifiedFormField
)

def generate_answer_for_open_question(
    question_field: IdentifiedFormField,
    full_user_profile_data: Dict[str, Any],
    identified_question_text: str
) -> QuestionAnsweringResult:
    """
    Simulates generating a draft answer for an open-ended question using user profile data.
    """
    print(f"QuestionAnsweringModule: Attempting to generate answer for question: '{identified_question_text}'")
    print(f"QuestionAnsweringModule: Question field DOM path: {question_field.dom_path_primary}")

    sources_from_profile: List[str] = []
    draft_answer: str = ""
    question_lower = identified_question_text.lower()

    # 2. Identify Relevant Profile Sections (Heuristic)
    if "interest" in question_lower and ("role" in question_lower or "position" in question_lower or "company" in question_lower or "why apply" in question_lower):
        career_goals = full_user_profile_data.get("career_goals", "advancing in my field")
        sources_from_profile.append("career_goals")
        company_research = full_user_profile_data.get("company_research_notes", {}).get(question_field.metadata.get("company_name_guess", "this company"), "their impactful work in the industry") # metadata is not on IFF, conceptual
        if "company_research_notes" in full_user_profile_data: sources_from_profile.append("company_research_notes")

        draft_answer = f"I am highly interested in this role as it directly aligns with my career goals of {career_goals}. " \
                       f"I've also been following [Company Name]'s progress and am particularly impressed by {company_research}. " \
                       f"I believe my skills in [mention key skill, e.g., {full_user_profile_data.get('skills_summary','relevant areas')}] would be a strong asset."
        if "skills_summary" in full_user_profile_data: sources_from_profile.append("skills_summary")


    elif "challenging project" in question_lower or "difficult task" in question_lower:
        projects = full_user_profile_data.get("past_projects", [])
        if projects:
            # For simplicity, use the first project. A real system might pick the most relevant.
            project = projects[0]
            sources_from_profile.append("past_projects[0]")
            project_desc = project.get("description", "a significant project")
            challenge = project.get("challenge", "its complexity and the tight deadlines involved")
            solution = project.get("solution", "applying dedicated problem-solving skills and effective collaboration with my team members")
            outcome = project.get("outcome", "a successful resolution and valuable lessons learned")
            draft_answer = f"One of the most challenging projects I encountered involved {project_desc}. " \
                           f"The main challenge was {challenge}. " \
                           f"I (or we) addressed this by {solution}, which ultimately led to {outcome}."
        else:
            draft_answer = "I have faced several challenging projects. For instance, I often deal with [generic challenge e.g., complex technical problems under tight deadlines] and typically overcome them by [generic solution e.g., methodical problem-solving and teamwork]."
            sources_from_profile.append("general_experience_approach") # Placeholder source

    elif "skills" in question_lower or "strengths" in question_lower or "experience" in question_lower and not ("salary" in question_lower or "expectation" in question_lower) :
        skills_summary = full_user_profile_data.get("skills_summary", "my diverse skill set")
        sources_from_profile.append("skills_summary")
        experience_summary = full_user_profile_data.get("resume_summary", "my professional background")
        if "resume_summary" in full_user_profile_data: sources_from_profile.append("resume_summary")

        draft_answer = f"My key skills relevant to this include {skills_summary}. " \
                       f"My experience, such as {experience_summary}, has prepared me well for these types of challenges. " \
                       f"For example, in a previous role at [Previous Company, if available], I [specific achievement related to a skill]."
                       # This last part is harder to template without more context or LLM.

    elif "salary expectations" in question_lower or "compensation" in question_lower:
        salary_info = full_user_profile_data.get("salary_expectations", {})
        sources_from_profile.append("salary_expectations")
        desired = salary_info.get("desired_annual_salary", "a competitive salary for this role and location")
        negotiable_str = " and I am open to discussing this further" if salary_info.get("is_negotiable", True) else ""
        draft_answer = f"My salary expectations are around {desired}{negotiable_str}, commensurate with my experience and the responsibilities of this position."

    else: # Generic fallback
        relevant_info = []
        if "resume_summary" in full_user_profile_data:
            relevant_info.append(f"my resume summary: \"{str(full_user_profile_data['resume_summary'])[:50]}...\"")
            sources_from_profile.append("resume_summary")
        if "skills_summary" in full_user_profile_data:
            relevant_info.append(f"my skills: \"{str(full_user_profile_data['skills_summary'])[:50]}...\"")
            sources_from_profile.append("skills_summary")

        if relevant_info:
            draft_answer = f"Based on my profile, particularly {', and '.join(relevant_info)}, I believe I can provide a comprehensive answer. [Please elaborate or provide a more specific prompt if needed]."
        else:
            draft_answer = "[As an AI, I need more specific context from the user's profile to draft an answer to this question. Please review and complete.]"
        sources_from_profile.append("general_profile_overview")


    # Ensure sources are unique
    final_sources = sorted(list(set(sources_from_profile)))

    qa_result = QuestionAnsweringResult(
        question_text_identified=identified_question_text,
        dom_path_question=question_field.dom_path_primary,
        suggested_answer_draft=draft_answer.strip(),
        sources_from_profile=final_sources,
        requires_user_review=True # Always true for generated answers
    )

    print(f"  Drafted answer: {draft_answer[:100]}...")
    print(f"  Sources from profile: {final_sources}")
    return qa_result


if __name__ == "__main__":
    print("--- Running Question Answering Module Demo ---")

    sample_profile_data = {
        "user.firstName": "Sam",
        "user.lastName": "Automaton",
        "career_goals": "contribute to innovative AI-driven solutions and grow as a lead engineer",
        "company_research_notes": {
            "Innovatech Solutions": "their pioneering work in NLP and commitment to open source.",
            "General Corp": "their large market share and stability."
        },
        "past_projects": [
            {
                "title": "AutoForm Filler Bot",
                "description": "developing an automated form filling system using AI",
                "challenge": "handling diverse and dynamic form structures across various websites",
                "solution": "creating a modular AI pipeline with visual perception, DOM grounding, semantic matching, and interaction logic, along with a user-friendly review interface",
                "outcome": "a significant reduction in manual data entry time and improved accuracy for job applications",
                "skills_used": ["Python", "AI/ML", "DOM manipulation", "System Design"]
            },
            {
                "title": "E-commerce Recommendation Engine",
                "description": "building a personalized product recommendation system",
                "challenge": "scaling the system for millions of users and products while maintaining real-time performance",
                "solution": "utilizing collaborative filtering and content-based filtering techniques, deployed on a distributed cloud architecture",
                "outcome": "increased user engagement and a 15% uplift in sales",
                "skills_used": ["Machine Learning", "Big Data", "Scalability", "Python", "AWS"]
            }
        ],
        "skills_summary": "Python, machine learning, natural language processing, system design, and cloud computing (AWS)",
        "strengths": ["problem-solving", "quick learning", "collaboration"],
        "resume_summary": "Experienced software engineer with a passion for AI and automation, skilled in developing complex systems and leading technical projects.",
        "salary_expectations": {
            "desired_annual_salary": "$120,000",
            "currency": "USD",
            "is_negotiable": True
        }
    }

    # Question 1: Interest in role
    question_field_1 = IdentifiedFormField(
        id="qf1",
        visual_label_text="Why are you interested in this role at Innovatech Solutions?", # This will be our identified_question_text
        visual_location=VisualLocation(x=10,y=10,w=300,h=100),
        dom_path_primary="//textarea[@id='interest_role_text']",
        field_type_predicted=PredictedFieldType.TEXTAREA,
        semantic_meaning_predicted="application.interestInRole", # Semantic meaning for the field itself
        confidence_score=0.9,
        # Conceptual: metadata might be enriched earlier to include company name if identifiable
        metadata={"company_name_guess": "Innovatech Solutions"}
    )
    # For the demo, we'll pass the visual_label_text as the identified_question_text directly
    answer_result_1 = generate_answer_for_open_question(
        question_field=question_field_1,
        full_user_profile_data=sample_profile_data,
        identified_question_text=question_field_1.visual_label_text
    )
    print("\nResult for Question 1 ('Interest in Role'):")
    print(f"  Question: {answer_result_1.question_text_identified}")
    print(f"  Draft Answer: {answer_result_1.suggested_answer_draft}")
    print(f"  Sources: {answer_result_1.sources_from_profile}")
    print(f"  Requires Review: {answer_result_1.requires_user_review}")

    # Question 2: Challenging project
    question_field_2 = IdentifiedFormField(
        id="qf2",
        visual_label_text="Describe a challenging project you worked on and how you overcame the obstacles.",
        visual_location=VisualLocation(x=10,y=120,w=300,h=100),
        dom_path_primary="//textarea[@id='challenging_project_desc']",
        field_type_predicted=PredictedFieldType.TEXTAREA,
        semantic_meaning_predicted="application.challengingProjectDescription",
        confidence_score=0.9,
        metadata={}
    )
    answer_result_2 = generate_answer_for_open_question(
        question_field=question_field_2,
        full_user_profile_data=sample_profile_data,
        identified_question_text=question_field_2.visual_label_text
    )
    print("\nResult for Question 2 ('Challenging Project'):")
    print(f"  Question: {answer_result_2.question_text_identified}")
    print(f"  Draft Answer: {answer_result_2.suggested_answer_draft}")
    print(f"  Sources: {answer_result_2.sources_from_profile}")
    print(f"  Requires Review: {answer_result_2.requires_user_review}")

    # Question 3: Salary expectations
    question_field_3 = IdentifiedFormField(
        id="qf3",
        visual_label_text="What are your salary expectations for this position?",
        visual_location=VisualLocation(x=10,y=230,w=300,h=50),
        dom_path_primary="//input[@id='salary_expectations_text']",
        field_type_predicted=PredictedFieldType.TEXT_INPUT, # Could be text input
        semantic_meaning_predicted="application.salaryExpectations",
        confidence_score=0.9,
        metadata={}
    )
    answer_result_3 = generate_answer_for_open_question(
        question_field=question_field_3,
        full_user_profile_data=sample_profile_data,
        identified_question_text=question_field_3.visual_label_text
    )
    print("\nResult for Question 3 ('Salary Expectations'):")
    print(f"  Question: {answer_result_3.question_text_identified}")
    print(f"  Draft Answer: {answer_result_3.suggested_answer_draft}")
    print(f"  Sources: {answer_result_3.sources_from_profile}")
    print(f"  Requires Review: {answer_result_3.requires_user_review}")

    # Question 4: Generic question with less direct profile mapping
    question_field_4 = IdentifiedFormField(
        id="qf4",
        visual_label_text="What are your long-term aspirations?",
        visual_location=VisualLocation(x=10,y=230,w=300,h=50),
        dom_path_primary="//textarea[@id='long_term_aspirations']",
        field_type_predicted=PredictedFieldType.TEXTAREA,
        semantic_meaning_predicted="application.longTermAspirations",
        confidence_score=0.9,
        metadata={}
    )
    answer_result_4 = generate_answer_for_open_question(
        question_field=question_field_4,
        full_user_profile_data=sample_profile_data,
        identified_question_text=question_field_4.visual_label_text
    )
    print("\nResult for Question 4 ('Long-term aspirations' - generic fallback):")
    print(f"  Question: {answer_result_4.question_text_identified}")
    print(f"  Draft Answer: {answer_result_4.suggested_answer_draft}")
    print(f"  Sources: {answer_result_4.sources_from_profile}")
    print(f"  Requires Review: {answer_result_4.requires_user_review}")


    print("\n--- Question Answering Module Demo Finished ---")
