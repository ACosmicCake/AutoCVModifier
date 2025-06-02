# ai_service_app.py
import os
import sys
import json
import asyncio
import tempfile
from pathlib import Path

from flask import Flask, request, jsonify

# Assuming this app runs from within computer_use_demo/computer_use_demo/
# Adjust path for imports if necessary, or ensure PYTHONPATH is set when running.
# For simplicity here, assuming direct imports from sibling modules work.
# If this script is in computer_use_demo/computer_use_demo/, then .loop and .tools are correct.
try:
    from .loop import sampling_loop
    from .tools import ToolVersion # This is a Literal type hint
    from .tools.computer import ComputerTool20250124
    # APIProvider was refactored to use string literals directly in loop.py
    print("Successfully imported .loop and .tools components.")
except ImportError as e:
    print(f"Error importing .loop or .tools: {e!r}")
    print(f"Current sys.path: {sys.path}")
    print(f"Current working directory: {os.getcwd()}")
    # Add parent directory to sys.path if running this script directly for testing
    # and it's not part of a larger package structure being handled by a runner.
    if Path(__file__).resolve().parent.name == "computer_use_demo" and \
       Path(__file__).resolve().parent.parent.name == "computer-use-demo":
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        print(f"Attempting to re-import after path adjustment. New sys.path: {sys.path}")
        from computer_use_demo.loop import sampling_loop
        from computer_use_demo.tools import ToolVersion
        from computer_use_demo.tools.computer import ComputerTool20250124
        print("Successfully re-imported after path adjustment.")
    else: # If path adjustment didn't help or structure is different.
        sampling_loop = None
        ToolVersion = None
        ComputerTool20250124 = None


app = Flask(__name__)

# --- Helper: Stub Callbacks (can be made more sophisticated later) ---
def output_callback_stub(content_block):
    block_type = content_block.get('type', 'unknown') if isinstance(content_block, dict) else 'unknown'
    print(f"[AI_SVC_Callback] AI Output Block Type: {block_type}"); sys.stdout.flush()
    if block_type == 'text':
        print(f"[AI_SVC_Callback] AI Text: {content_block.get('text')}"); sys.stdout.flush()
    elif block_type == 'tool_use':
        print(f"[AI_SVC_Callback] AI Tool Use: Name='{content_block.get('name')}', Input='{content_block.get('input')}'"); sys.stdout.flush()
    else:
        print(f"[AI_SVC_Callback] AI Output (Full): {content_block}"); sys.stdout.flush()

def tool_output_callback_stub(tool_result, tool_id):
    print(f"[AI_SVC_Callback] Tool Output for ID {tool_id}:"); sys.stdout.flush()
    if tool_result.output:
        print(f"  Output: {tool_result.output[:200]}{'...' if tool_result.output and len(tool_result.output) > 200 else ''}"); sys.stdout.flush()
    if tool_result.error:
        print(f"  Error: {tool_result.error}"); sys.stdout.flush()
    if tool_result.base64_image:
        print(f"  Image: (base64_image present, length {len(tool_result.base64_image)})"); sys.stdout.flush()
    if tool_result.system:
            print(f"  System Message: {tool_result.system}"); sys.stdout.flush()
    if not (tool_result.output or tool_result.error or tool_result.base64_image or tool_result.system):
        print(f"  (No direct output, error, image or system message in ToolResult object for {tool_id})"); sys.stdout.flush()

def api_response_callback_stub(req, resp, exc):
    print("[AI_SVC_Callback] API Interaction:"); sys.stdout.flush()
    if req:
        print(f"  Request: Method={req.method}, URL={req.url}"); sys.stdout.flush()
    if resp:
        print(f"  Response: Status={resp.status_code if hasattr(resp, 'status_code') else 'N/A'}"); sys.stdout.flush()
    if exc:
        print(f"  Exception: Type={type(exc).__name__}, Message='{str(exc)}'"); sys.stdout.flush()


@app.route('/execute-auto-apply', methods=['POST'])
async def execute_auto_apply():
    print("AI Service: Received request for /execute-auto-apply"); sys.stdout.flush()
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No JSON payload received"}), 400

    job_url = data.get('job_url')
    cv_json_content = data.get('cv_json_content')
    cv_pdf_filename = data.get('cv_pdf_filename') # This is just the filename
    profile_json_content = data.get('profile_json_content')
    anthropic_api_key = data.get('anthropic_api_key')

    required_params = {
        "job_url": job_url, "cv_json_content": cv_json_content,
        "cv_pdf_filename": cv_pdf_filename, "profile_json_content": profile_json_content,
        "anthropic_api_key": anthropic_api_key
    }
    missing_params = [k for k, v in required_params.items() if v is None]
    if missing_params:
        return jsonify({"status": "error", "message": f"Missing required parameters: {', '.join(missing_params)}"}), 400

    if sampling_loop is None or ComputerTool20250124 is None:
        return jsonify({"status": "error", "message": "AI service components (sampling_loop or ComputerTool) not loaded."}), 500

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        
        # Save CV JSON content to a temporary file
        cv_json_container_path_obj = temp_dir_path / "temp_cv.json"
        with open(cv_json_container_path_obj, 'w', encoding='utf-8') as f:
            f.write(cv_json_content)
        cv_json_container_path = str(cv_json_container_path_obj.resolve())

        # Save Profile JSON content to a temporary file
        profile_json_container_path_obj = temp_dir_path / "temp_profile.json"
        with open(profile_json_container_path_obj, 'w', encoding='utf-8') as f:
            f.write(profile_json_content)
        profile_json_container_path = str(profile_json_container_path_obj.resolve())

        # This path assumes a volume mount like /mnt/shared_pdfs (host) -> /mnt/shared_pdfs (container)
        # The main app (cv_tailor_project) would place the PDF in its 'instance/generated_pdfs' which needs to be mounted.
        # For now, this is a placeholder path. The AI will be told to use this path for upload.
        cv_pdf_container_path = f"/mnt/shared_pdfs/{cv_pdf_filename}" 
        print(f"AI Service: Temp CV JSON at {cv_json_container_path}"); sys.stdout.flush()
        print(f"AI Service: Temp Profile JSON at {profile_json_container_path}"); sys.stdout.flush()
        print(f"AI Service: Expecting CV PDF for upload at {cv_pdf_container_path}"); sys.stdout.flush()


        # Set ANTHROPIC_API_KEY for sampling_loop.
        # WIDTH, HEIGHT, and DISPLAY_NUM (or DISPLAY) are expected to be set by
        # the computer-use-demo Docker container's environment itself.
        # ComputerTool will pick these up automatically.
        os.environ['ANTHROPIC_API_KEY'] = anthropic_api_key
        print(f"AI Service: ANTHROPIC_API_KEY set for this request."); sys.stdout.flush()
        print(f"AI Service: ComputerTool will use existing env vars for WIDTH, HEIGHT, DISPLAY_NUM (e.g., WIDTH={os.getenv('WIDTH')}, DISPLAY={os.getenv('DISPLAY')})"); sys.stdout.flush()


        system_prompt_suffix = """
Your primary goal is to automatically apply for a job on behalf of the user.
You will be provided with a job URL, paths to a tailored CV (JSON), a CV (PDF for upload), and a user profile (JSON).
Your main tasks are to navigate to the job URL, locate the application form, accurately fill it using the data from the JSON files, upload the CV PDF when required, and submit the application.
Remember to use your computer interaction tools (mouse clicks, keyboard typing, scrolling, screenshotting) to perform these tasks.
The file paths provided are accessible from your environment.
""" # Simplified for this service, main instructions are in computer_use_demo.loop.SYSTEM_PROMPT

        initial_messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Your task is to automatically apply for the job at the following URL: {job_url}. "
                                f"Use information from these files: "
                                f"Tailored CV (JSON format): '{cv_json_container_path}', "
                                f"Tailored CV (PDF format for upload): '{cv_pdf_container_path}', "
                                f"User Profile (JSON format): '{profile_json_container_path}'. "
                                f"Please begin the application process. Follow strategies from the system prompt. Report issues like mandatory account creation or CAPTCHAs."
                    }
                ]
            }
        ]

        model_name = "claude-3-5-sonnet-20240620"
        provider_str = "anthropic" # Use string literal as APIProvider enum was refactored
        tool_version_str = "computer_use_20250124" # As defined in computer_use_demo.tools.groups

        print(f"AI Service: Attempting to call sampling_loop with model: {model_name}, provider: {provider_str}, tool_version: {tool_version_str}"); sys.stdout.flush()
        
        loop_result_messages = []
        try:
            loop_result_messages = await sampling_loop(
                model=model_name,
                provider=provider_str,
                system_prompt_suffix=system_prompt_suffix, # Appended to the main system prompt in loop.py
                messages=initial_messages,
                output_callback=output_callback_stub,
                tool_output_callback=tool_output_callback_stub,
                api_response_callback=api_response_callback_stub,
                api_key=anthropic_api_key, # sampling_loop expects this directly
                tool_version=tool_version_str,
            )
            print(f"AI Service: sampling_loop call completed. Result messages count: {len(loop_result_messages) if loop_result_messages else 'None'}"); sys.stdout.flush()
            return jsonify({"status": "success", "message": "AI processing completed.", "output_messages": loop_result_messages}), 200
        except Exception as e:
            print(f"AI Service: Error during sampling_loop invocation: {e!r}"); sys.stdout.flush()
            import traceback
            traceback.print_exc() # Print full traceback to service logs
            return jsonify({"status": "error", "message": "Error during AI processing.", "details": str(e)}), 500

if __name__ == '__main__':
    # When running this AI service, ensure computer_use_demo package is in PYTHONPATH
    # e.g., by running from parent of computer_use_demo directory:
    # PYTHONPATH=$PYTHONPATH:$(pwd)/computer-use-demo python computer-use-demo/computer_use_demo/ai_service_app.py
    # Or, if Dockerizing, ensure the workdir and PYTHONPATH are set up correctly.
    
    # Flask's default dev server supports async from version 2.0.
    # For production, an ASGI server like Hypercorn or Uvicorn is recommended.
    # Example: hypercorn computer_use_demo.ai_service_app:app --bind 0.0.0.0:8081
    app.run(host='0.0.0.0', port=8081, debug=True)

```
