# cv_tailor_project/run.py
import os
from app.main import create_app

# Create an instance of the app using the factory function
app = create_app()

if __name__ == '__main__':
    # Default to localhost only. The Werkzeug debugger allows arbitrary code execution, so never
    # combine FLASK_DEBUG=true with FLASK_RUN_HOST=0.0.0.0 on a network you don't trust.
    host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_RUN_PORT', 5001))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1', 't']

    print(f"Starting Flask app on http://{host}:{port} (Debug: {debug_mode})")
    app.run(host=host, port=port, debug=debug_mode, threaded=True)
