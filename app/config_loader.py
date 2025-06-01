# app/config_loader.py
import os
import json

# --- Global Variables ---
# SITE_SELECTORS stores configurations for website-specific element locators,
# loaded from `site_selectors.json` at application startup.
SITE_SELECTORS = {}

# --- Load Site Selector Configuration ---
def load_selector_config():
    global SITE_SELECTORS
    # os.path.dirname(__file__) gives the directory of the current file (app)
    # os.path.abspath() ensures it's an absolute path before going up.
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'site_selectors.json')

    default_selectors = {
        "name": { "type": "id", "value": "full_name" },
        "email": { "type": "id", "value": "email" },
        "phone": { "type": "id", "value": "phone" },
        "cv_upload": { "type": "css", "value": "input[type='file']" },
        "submit_button": { "type": "id", "value": "submit_application" },
        "login_username": { "type": "css", "value": "input[name="username"]" },
        "login_password": { "type": "css", "value": "input[name="password"]" },
        "login_button": { "type": "css", "value": "button[type="submit"]" }
    }

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            SITE_SELECTORS = json.load(f)
            if "default" not in SITE_SELECTORS: # Ensure default is present
                SITE_SELECTORS["default"] = default_selectors
                print("Warning: 'default' selectors not found in site_selectors.json, using hardcoded defaults.")
            print(f"Successfully loaded site selectors from {config_path}")
    except FileNotFoundError:
        print(f"Error: site_selectors.json not found at {config_path}. Using default selectors only.")
        SITE_SELECTORS = {"default": default_selectors}
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from site_selectors.json at {config_path}. Using default selectors only.")
        SITE_SELECTORS = {"default": default_selectors}
    except Exception as e:
        print(f"An unexpected error occurred while loading site_selectors.json: {e}. Using default selectors only.")
        SITE_SELECTORS = {"default": default_selectors}

load_selector_config() # Load configuration when module is loaded
