#!/bin/bash
echo "Starting test script..."

# Ensure all dependencies are installed
echo "Installing dependencies..."
pip install -r requirements.txt
pip install -r computer_use_demo/requirements.txt

# Set environment variables (these will be passed directly to the python command)
echo "Setting environment variables for Flask app..."
export ANTHROPIC_API_KEY="TEST_ANTHROPIC_KEY_12345"
export GOOGLE_API_KEY="TEST_GOOGLE_KEY_12345"
export WIDTH="1920"
export HEIGHT="1080"
echo "ANTHROPIC_API_KEY: $ANTHROPIC_API_KEY"
echo "GOOGLE_API_KEY: $GOOGLE_API_KEY"
echo "WIDTH: $WIDTH"
echo "HEIGHT: $HEIGHT"

# Kill any existing Flask app to ensure a fresh start
echo "Attempting to stop any existing Flask app..."
pkill -f "python run.py" || echo "No existing Flask app to kill."
sleep 2 # Give it a moment to shut down if it was running

# Start the Flask app in the background, ensuring it inherits the environment variables
echo "Starting Flask app..."
WIDTH="1920" HEIGHT="1080" ANTHROPIC_API_KEY="TEST_ANTHROPIC_KEY_12345" GOOGLE_API_KEY="TEST_GOOGLE_KEY_12345" python run.py &
FLASK_PID=$!
echo "Flask app started with PID $FLASK_PID"

# Wait for the server to start
echo "Waiting for server to initialize..."
sleep 10

# Run the curl command
echo "Sending request to /api/auto-apply..."
curl -i -X POST http://127.0.0.1:5001/api/auto-apply \
-H "Content-Type: application/json" \
-d '{
  "job_url": "https://example.com/test-job-posting",
  "cv_pdf_path": "test_cv.pdf",
  "profile_json_path": "test_profile.json"
}'

# Clean up: Kill the Flask app process
echo "Stopping Flask app with PID $FLASK_PID..."
kill $FLASK_PID
wait $FLASK_PID 2>/dev/null # Wait for the process to actually terminate, suppress errors if already gone
echo "Test script finished."
