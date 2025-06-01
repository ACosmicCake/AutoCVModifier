from typing import List, Dict, Any
import re

# Assuming ai_core_data_structures.py is in the same directory or accessible in PYTHONPATH
from ai_core_data_structures import IdentifiedFormField, VisualLocation, PredictedFieldType, FormFieldOption

# --- Knowledge Base / Heuristics ---
# Maps variations of label text (lowercase) to standardized semantic meaning keys.
# Also includes some basic action mapping for buttons.
SEMANTIC_KNOWLEDGE_BASE: Dict[str, str] = {
    "first name": "user.firstName",
    "firstname": "user.firstName",
    "given name": "user.firstName",
    "forename": "user.firstName",
    "last name": "user.lastName",
    "lastname": "user.lastName",
    "surname": "user.lastName",
    "family name": "user.lastName",
    "email": "user.email.primary",  # Default, can be overridden by disambiguation
    "email address": "user.email.primary",
    "e-mail": "user.email.primary",
    "e-mail address": "user.email.primary",
    "work email": "user.email.work",
    "business email": "user.email.work",
    "professional email": "user.email.work",
    "personal email": "user.email.personal", # Added for disambiguation example
    "mobile phone": "user.phone.mobile",
    "cell phone": "user.phone.mobile",
    "mobile number": "user.phone.mobile",
    "phone number": "user.phone.primary", # Default phone
    "telephone number": "user.phone.primary",
    "zip code": "user.address.postalCode",
    "zip": "user.address.postalCode",
    "postal code": "user.address.postalCode",
    "postcode": "user.address.postalCode",
    "street address": "user.address.street",
    "address line 1": "user.address.street",
    "city": "user.address.city",
    "state": "user.address.region", # region/state/province
    "province": "user.address.region",
    "country": "user.address.country",
    "date of birth": "user.dateOfBirth",
    "dob": "user.dateOfBirth",
    "username": "user.credentials.username",
    "password": "user.credentials.password",

    # Common actions for buttons
    "submit": "action.submitForm",
    "submit application": "action.submitForm",
    "apply": "action.submitForm",
    "send": "action.submitForm",
    "next": "action.nextPage",
    "continue": "action.nextPage",
    "back": "action.previousPage",
    "previous": "action.previousPage",
    "cancel": "action.cancel",
    "login": "action.login",
    "log in": "action.login",
    "sign in": "action.login",
    "register": "action.register",
    "sign up": "action.register",

    # Common consent checkboxes (simplified matching on keywords)
    "i agree": "consent.termsAndConditions", # Simplified, real system needs more nuance
    "agree to terms": "consent.termsAndConditions",
    "accept terms": "consent.termsAndConditions",
    "privacy policy": "consent.privacyPolicy",
    "subscribe to newsletter": "consent.newsletterSubscription",
    "keep me updated": "consent.marketingOptIn",
}

# Keywords for more specific email types
WORK_EMAIL_KEYWORDS = ["work", "business", "professional", "company", "job"]
PERSONAL_EMAIL_KEYWORDS = ["personal", "home"]


def match_semantic_meaning_for_fields(
    identified_fields: List[IdentifiedFormField],
    user_profile_keys_example: List[str] # For context, not directly used in this simplified simulation's logic
) -> List[IdentifiedFormField]:
    """
    Infers semantic meaning for identified form fields using a knowledge base and heuristics.
    """
    print(f"SemanticMatchingModule: Starting semantic matching for {len(identified_fields)} fields.")
    print(f"SemanticMatchingModule: Example user profile keys provided: {user_profile_keys_example}")

    updated_fields: List[IdentifiedFormField] = []
    field_labels_lower = [field.visual_label_text.lower() if field.visual_label_text else "" for field in identified_fields]

    # --- Pre-analysis for Disambiguation (e.g., multiple email fields) ---
    has_work_email_label = any(any(kw in label for kw in WORK_EMAIL_KEYWORDS) for label in field_labels_lower if label)
    has_personal_email_label = any(any(kw in label for kw in PERSONAL_EMAIL_KEYWORDS) for label in field_labels_lower if label)

    for field in identified_fields:
        updated_field = field
        label_text_lower = (field.visual_label_text or "").lower().strip()
        semantic_key_found = False

        if not label_text_lower:
            if field.field_type_predicted not in [PredictedFieldType.BUTTON, PredictedFieldType.CHECKBOX]: # Buttons/checkboxes might lack separate labels
                print(f"  Skipping semantic matching for field ID {field.id} due to missing visual label.")
                updated_fields.append(updated_field)
                continue

        print(f"\n  Processing field: '{field.visual_label_text}' (ID: {field.id}, Type: {field.field_type_predicted.name})")

        # 1. Direct match from knowledge base using label text
        if label_text_lower in SEMANTIC_KNOWLEDGE_BASE:
            potential_semantic_key = SEMANTIC_KNOWLEDGE_BASE[label_text_lower]

            # Basic Disambiguation for "email"
            if potential_semantic_key == "user.email.primary":
                is_work_email_by_keyword = any(kw in label_text_lower for kw in WORK_EMAIL_KEYWORDS)
                is_personal_email_by_keyword = any(kw in label_text_lower for kw in PERSONAL_EMAIL_KEYWORDS)

                if is_work_email_by_keyword:
                    updated_field.semantic_meaning_predicted = "user.email.work"
                elif is_personal_email_by_keyword:
                     updated_field.semantic_meaning_predicted = "user.email.personal"
                elif has_work_email_label and not has_personal_email_label: # Another field is work, this one is likely personal/primary
                    updated_field.semantic_meaning_predicted = "user.email.personal" # Or keep as primary
                # If only "email" is found across all fields, it defaults to user.email.primary via knowledge base
                else:
                    updated_field.semantic_meaning_predicted = potential_semantic_key
            else:
                 updated_field.semantic_meaning_predicted = potential_semantic_key

            updated_field.confidence_score = min(1.0, field.confidence_score + 0.1) # Boost confidence
            semantic_key_found = True
            print(f"    Direct KB match: '{label_text_lower}' -> '{updated_field.semantic_meaning_predicted}'")

        # 2. Handle Buttons/Actions specifically (if not caught by direct label match)
        if not semantic_key_found and field.field_type_predicted == PredictedFieldType.BUTTON:
            # Check common button texts if not an exact match in KB
            for keyword, semantic_action in SEMANTIC_KNOWLEDGE_BASE.items():
                if keyword in label_text_lower and semantic_action.startswith("action."):
                    updated_field.semantic_meaning_predicted = semantic_action
                    updated_field.confidence_score = min(1.0, field.confidence_score + 0.08)
                    semantic_key_found = True
                    print(f"    Button keyword match: '{label_text_lower}' (contains '{keyword}') -> '{semantic_action}'")
                    break

        # 3. Handle Checkboxes for Consent/Subscriptions (if not caught by direct label match)
        if not semantic_key_found and field.field_type_predicted == PredictedFieldType.CHECKBOX:
            # Check for consent-related keywords
            for keyword, semantic_consent in SEMANTIC_KNOWLEDGE_BASE.items():
                if keyword in label_text_lower and semantic_consent.startswith("consent."):
                    updated_field.semantic_meaning_predicted = semantic_consent
                    updated_field.confidence_score = min(1.0, field.confidence_score + 0.08)
                    semantic_key_found = True
                    print(f"    Checkbox keyword match: '{label_text_lower}' (contains '{keyword}') -> '{semantic_consent}'")
                    break

        # 4. Partial/Keyword based matching as a fallback (simplified)
        if not semantic_key_found:
            for kb_label, kb_semantic in SEMANTIC_KNOWLEDGE_BASE.items():
                # Avoid overly generic partial matches like "name" for "first name", "last name" etc.
                # This requires careful construction of KB or more advanced techniques.
                # For simulation, we can try if a multi-word KB entry's words are present.
                if len(kb_label.split()) > 1 and all(word in label_text_lower.split() for word in kb_label.split()):
                    # Basic disambiguation for "email" again if matched partially
                    if kb_semantic == "user.email.primary":
                        if has_work_email_label and not any(kw in label_text_lower for kw in WORK_EMAIL_KEYWORDS):
                             updated_field.semantic_meaning_predicted = "user.email.personal" # Or keep as primary
                        else:
                            updated_field.semantic_meaning_predicted = kb_semantic
                    else:
                        updated_field.semantic_meaning_predicted = kb_semantic

                    updated_field.confidence_score = min(1.0, field.confidence_score + 0.05) # Lower confidence for partial
                    semantic_key_found = True
                    print(f"    Partial KB match: '{label_text_lower}' (all words from '{kb_label}') -> '{updated_field.semantic_meaning_predicted}'")
                    break # Take first partial match

        if not semantic_key_found:
            print(f"    No semantic meaning matched for label: '{label_text_lower}'")
            updated_field.semantic_meaning_predicted = "" # Ensure it's empty if no match

        updated_fields.append(updated_field)

    print(f"\nSemanticMatchingModule: Matching process completed for {len(updated_fields)} fields.")
    return updated_fields


if __name__ == "__main__":
    print("--- Running Semantic Matching Module Demo ---")

    sample_user_profile_keys = [
        "user.firstName", "user.lastName", "user.email.primary", "user.email.work", "user.email.personal",
        "user.phone.mobile", "user.address.postalCode", "consent.termsAndConditions",
        "action.submitForm", "action.nextPage"
    ]

    # Sample IdentifiedFormField objects (as if from Visual Grounding Module)
    fields_to_match: List[IdentifiedFormField] = [
        IdentifiedFormField(
            id="field_1", visual_label_text="First Name",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), field_type_predicted=PredictedFieldType.TEXT_INPUT,
            confidence_score=0.9, dom_path_primary="//input[@id='fname']", dom_path_label="//label[@for='fname']",
            semantic_meaning_predicted=""
        ),
        IdentifiedFormField(
            id="field_2", visual_label_text="Your E-mail Address",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), field_type_predicted=PredictedFieldType.TEXT_INPUT,
            confidence_score=0.88, dom_path_primary="//input[@name='email']", dom_path_label="//label[contains(.,'E-mail')]",
            semantic_meaning_predicted=""
        ),
        IdentifiedFormField(
            id="field_3", visual_label_text="Work Email",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), field_type_predicted=PredictedFieldType.TEXT_INPUT,
            confidence_score=0.87, dom_path_primary="//input[@name='work_email']",
            semantic_meaning_predicted=""
        ),
        IdentifiedFormField( # A button
            id="btn_1", visual_label_text="Submit Application",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), field_type_predicted=PredictedFieldType.BUTTON,
            confidence_score=0.92, dom_path_primary="//button[contains(.,'Submit')]",
            semantic_meaning_predicted=""
        ),
        IdentifiedFormField( # A checkbox
            id="chk_1", visual_label_text="I agree to the terms and conditions",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), field_type_predicted=PredictedFieldType.CHECKBOX,
            confidence_score=0.8, dom_path_primary="//input[@id='terms']",
            semantic_meaning_predicted=""
        ),
        IdentifiedFormField( # No direct label, but maybe DOM name implies something (not used in this version)
            id="field_orphan", visual_label_text=None, # No visual label
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), field_type_predicted=PredictedFieldType.TEXT_INPUT,
            confidence_score=0.7, dom_path_primary="//input[@name='user_zip_code']", # name attribute might be useful
            semantic_meaning_predicted=""
        ),
        IdentifiedFormField( # Another button with a common synonym
            id="btn_2", visual_label_text="Continue to next step",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), field_type_predicted=PredictedFieldType.BUTTON,
            confidence_score=0.90, dom_path_primary="//button[contains(.,'Continue')]",
            semantic_meaning_predicted=""
        ),
    ]

    print(f"\nInitial fields (before semantic matching):")
    for field in fields_to_match:
        print(f"  ID: {field.id}, Label: '{field.visual_label_text}', Type: {field.field_type_predicted.name}, Semantic: '{field.semantic_meaning_predicted}', Confidence: {field.confidence_score:.2f}")

    matched_fields = match_semantic_meaning_for_fields(
        identified_fields=fields_to_match,
        user_profile_keys_example=sample_user_profile_keys
    )

    print(f"\nFields after semantic matching:")
    for field in matched_fields:
        print(f"  ID: {field.id}, Label: '{field.visual_label_text}', Type: {field.field_type_predicted.name}, Semantic: '{field.semantic_meaning_predicted}', Confidence: {field.confidence_score:.2f}")

    print("\n--- Semantic Matching Module Demo Finished ---")
