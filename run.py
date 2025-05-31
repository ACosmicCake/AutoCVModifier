# cv_tailor_project/run.py
import os
from app.main import create_app

# Create an instance of the app using the factory function
app = create_app()

if __name__ == '__main__':
    # Determine host and port.
    # Default to 0.0.0.0 to be accessible externally if needed (e.g., in a container).
    # Use a different port as suggested in the issue, e.g., 5001.
    host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_RUN_PORT', 5001))
    debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() in ['true', '1', 't']

    print(f"Starting Flask app on {host}:{port} (Debug: {debug_mode})")
    app.run(host=host, port=port, debug=debug_mode)
