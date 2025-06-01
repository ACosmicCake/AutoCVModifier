from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union
from enum import Enum

# --- Input Data Structures ---

class ImageEncoding(Enum):
    BASE64 = "base64"
    FILE_PATH = "file_path"

@dataclass
class PageScreenshot:
    type: str  # e.g., "image/png", "image/jpeg"
    description: str
    encoding: ImageEncoding
    data: str  # Base64 string or path to the image file

@dataclass
class DOMStructure:
    type: str  # "html_string" or "json_object"
    data: Union[str, Dict[str, Any]] # Full HTML or JSON representation of DOM

@dataclass
class AccessibilityTree:
    type: str  # "json_object"
    data: Dict[str, Any] # JSON representation of the accessibility tree

@dataclass
class UserProfileSummary:
    preferred_language: Optional[str] = None
    target_role_type: Optional[str] = None
    # Add other relevant high-level summary fields as needed
    # For example:
    # years_of_experience: Optional[int] = None
    # current_location: Optional[str] = None

@dataclass
class Metadata:
    url: str
    timestamp: str  # ISO 8601 datetime string
    user_profile_summary: Optional[UserProfileSummary] = None

class PreviousActionStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"

@dataclass
class PreviousAction:
    action_type: str  # Non-default
    status: PreviousActionStatus  # Non-default - Moved up
    field_label_guessed: Optional[str] = None  # Default
    value_used: Optional[Any] = None  # Default
    description: Optional[str] = None  # Default

@dataclass
class AICoreInput:
    page_screenshot: PageScreenshot  # Non-default
    dom_structure: DOMStructure      # Non-default
    metadata: Metadata               # Non-default - Moved up
    accessibility_tree: Optional[AccessibilityTree] = None  # Default
    previous_actions_summary: List[PreviousAction] = field(default_factory=list)  # Default

# --- Output Data Structures ---

class PredictedFieldType(Enum):
    TEXT_INPUT = "text_input"
    DROPDOWN = "dropdown"
    CHECKBOX = "checkbox"
    RADIO_BUTTON = "radio_button"
    DATE_PICKER = "date_picker"
    FILE_UPLOAD = "file_upload"
    TEXTAREA = "textarea"
    BUTTON = "button" # For buttons not part of navigation/submission
    # Add more types as identified

@dataclass
class VisualLocation:
    x: int
    y: int
    width: int
    height: int

@dataclass
class FormFieldOption:
    value: str
    label_text: Optional[str] = None

@dataclass
class IdentifiedFormField:
    # Non-default fields first
    id: str
    visual_location: VisualLocation
    dom_path_primary: str
    field_type_predicted: PredictedFieldType
    semantic_meaning_predicted: str
    confidence_score: float
    # Default fields follow
    visual_label_text: Optional[str] = None
    dom_path_label: Optional[str] = None
    options: List[FormFieldOption] = field(default_factory=list)
    is_required_predicted: bool = False
    current_value: Optional[Any] = None

class NavigationActionType(Enum):
    SUBMIT_FORM = "submit_form"
    NEXT_PAGE = "next_page"
    PREVIOUS_PAGE = "previous_page"
    CANCEL = "cancel"
    OTHER = "other" # For navigation-like elements not fitting above categories

@dataclass
class NavigationElement:
    # Non-default fields first
    id: str
    visual_location: VisualLocation
    dom_path: str
    action_type_predicted: NavigationActionType
    confidence_score: float
    # Default fields follow
    visual_label_text: Optional[str] = None

@dataclass
class FormUnderstandingResult:
    type: str = "form_understanding_result"
    fields: List[IdentifiedFormField] = field(default_factory=list)
    navigation_elements: List[NavigationElement] = field(default_factory=list)
    page_summary: Optional[str] = None # e.g., "Contact Information Page"

@dataclass
class QuestionAnsweringResult:
    # Non-default fields first
    question_text_identified: str
    dom_path_question: str
    suggested_answer_draft: str
    sources_from_profile: List[str]
    # Default fields follow
    type: str = "question_answering_result"
    requires_user_review: bool = True

    def to_dict(self) -> Dict[str, Any]: # Method remains the same
        return {
            "type": self.type,
            "question_text_identified": self.question_text_identified,
            "dom_path_question": self.dom_path_question,
            "suggested_answer_draft": self.suggested_answer_draft,
            "sources_from_profile": self.sources_from_profile,
            "requires_user_review": self.requires_user_review
        }

class ActionSequenceActionType(Enum):
    FILL_TEXT = "fill_text"
    SELECT_DROPDOWN_OPTION = "select_dropdown_option"
    CLICK_ELEMENT = "click_element"
    UPLOAD_FILE = "upload_file"
    SCROLL = "scroll"
    NAVIGATE_URL = "navigate_url"
    # Add more specific actions as needed

@dataclass
class ActionDetail:
    action_type: ActionSequenceActionType
    dom_path_target: str
    value_to_fill: Optional[str] = None # for "fill_text"
    option_to_select: Optional[str] = None # for "select_dropdown_option" (value or visible text)
    file_path_to_upload: Optional[str] = None # for "upload_file"
    url_to_navigate: Optional[str] = None # for "navigate_url"
    scroll_direction: Optional[str] = None # for "scroll", e.g., "down", "up", "to_element"
    scroll_amount: Optional[str] = None # for "scroll", e.g., "page", "half_page", or pixels
    visual_confirmation_cue: Optional[str] = None # description of what to expect visually

@dataclass
class ActionSequenceRecommendation:
    type: str = "action_sequence_recommendation"
    actions: List[ActionDetail] = field(default_factory=list)
    expected_next_page_type: Optional[str] = None # e.g., "confirmation_page", "next_form_step"

@dataclass
class ClarificationRequest:
    # Non-default fields first
    question_for_user: str
    # Default fields follow
    type: str = "clarification_request"
    ambiguous_element_id: Optional[str] = None
    options_for_user: List[str] = field(default_factory=list)
    context_image_required: bool = False

# Union type for all possible AI Core outputs
AICoreOutput = Union[
    FormUnderstandingResult,
    QuestionAnsweringResult,
    ActionSequenceRecommendation,
    ClarificationRequest
]

if __name__ == '__main__':
    # Example Usage (for testing the structures)

    # Input Example
    sample_screenshot = PageScreenshot(
        type="image/png",
        description="Screenshot of the login page.",
        encoding=ImageEncoding.BASE64,
        data="SGVsbG8gd29ybGQh" # Dummy base64 data
    )

    sample_dom = DOMStructure(
        type="html_string",
        data="<html><body><h1>Login</h1>...</body></html>"
    )

    sample_metadata = Metadata(
        url="https://example.com/login",
        timestamp="2023-10-27T10:00:00Z",
        user_profile_summary=UserProfileSummary(
            preferred_language="en-US",
            target_role_type="Software Engineer"
        )
    )

    sample_previous_action = PreviousAction(
        action_type="fill_field",
        field_label_guessed="Username",
        value_used="testuser",
        status=PreviousActionStatus.SUCCESS
    )

    ai_input = AICoreInput(
        page_screenshot=sample_screenshot,
        dom_structure=sample_dom,
        metadata=sample_metadata,
        previous_actions_summary=[sample_previous_action]
    )
    print(f"Sample AI Input: {ai_input}\n")

    # Output Example: FormUnderstandingResult
    form_result = FormUnderstandingResult(
        fields=[
            IdentifiedFormField(
                id="field_1",
                visual_label_text="Email Address",
                visual_location=VisualLocation(x=10, y=20, width=100, height=30),
                dom_path_primary="//input[@id='email']",
                field_type_predicted=PredictedFieldType.TEXT_INPUT,
                semantic_meaning_predicted="user.email.primary",
                confidence_score=0.95,
                is_required_predicted=True
            )
        ],
        navigation_elements=[
            NavigationElement(
                id="nav_1",
                visual_label_text="Next",
                visual_location=VisualLocation(x=50, y=100, width=80, height=40),
                dom_path="//button[@id='next_button']",
                action_type_predicted=NavigationActionType.NEXT_PAGE,
                confidence_score=0.99
            )
        ],
        page_summary="User login page for accessing account."
    )
    print(f"Sample AI Output (FormUnderstandingResult): {form_result}\n")

    # Output Example: ClarificationRequest
    clarification_req = ClarificationRequest(
        question_for_user="Which email address should be used as primary?",
        options_for_user=["personal@example.com", "work@example.com"],
        ambiguous_element_id="field_1"
    )
    print(f"Sample AI Output (ClarificationRequest): {clarification_req}\n")

    # Output Example: ActionSequenceRecommendation
    action_seq = ActionSequenceRecommendation(
        actions=[
            ActionDetail(
                action_type=ActionSequenceActionType.FILL_TEXT,
                dom_path_target="//input[@id='username']",
                value_to_fill="myusername"
            ),
            ActionDetail(
                action_type=ActionSequenceActionType.CLICK_ELEMENT,
                dom_path_target="//button[@id='submit_login']",
                visual_confirmation_cue="Redirected to dashboard page"
            )
        ],
        expected_next_page_type="dashboard"
    )
    print(f"Sample AI Output (ActionSequenceRecommendation): {action_seq}\n")

    # Output Example: QuestionAnsweringResult
    qa_result = QuestionAnsweringResult(
        question_text_identified="Describe your experience with Python.",
        dom_path_question="//textarea[@id='experience_python']",
        suggested_answer_draft="I have 5 years of experience with Python, primarily in web development...",
        sources_from_profile=["resume.experience.project_alpha.description", "skills.python"],
        requires_user_review=True
    )
    print(f"Sample AI Output (QuestionAnsweringResult): {qa_result}\n")
