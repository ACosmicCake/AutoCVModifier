import pytest
import os
import tempfile
from app.main import create_app
from app.database import init_db, get_db_connection, DATABASE_NAME as ACTUAL_DATABASE_NAME

# Store the original DATABASE_NAME to revert after tests if necessary, though monkeypatch should handle it per test.
ORIGINAL_DATABASE_NAME = ACTUAL_DATABASE_NAME

@pytest.fixture(scope='session')
def app():
    """Create and configure a new app instance for each test session."""

    # Create a temporary file for the SQLite database for the test session
    # Using a temporary file db is often more robust for testing than pure in-memory
    # especially if the app or underlying libraries behave differently with ':memory:'.
    db_fd, db_path = tempfile.mkstemp(suffix='.db')

    # Create a minimal .env file for tests or rely on environment variables
    # For this example, we'll assume critical env vars like GOOGLE_API_KEY might be
    # set in the test environment, or tests needing them will mock them out.
    # If not, you could create a temporary .env here:
    # temp_env_path = os.path.join(os.path.dirname(db_path), ".env.test")
    # with open(temp_env_path, "w") as f:
    #     f.write("SECRET_KEY=test_secret_key\n")
        # f.write("GOOGLE_API_KEY=test_api_key_if_not_mocked\n") # Add other needed vars

    flask_app = create_app({
        'TESTING': True,
        # Override the DATABASE_NAME normally used by app.database
        # This ensures that init_db and get_db_connection use the test database.
        # Note: This direct override might not work if app.database imports DATABASE_NAME directly
        # and uses it at module load time. A monkeypatch in test_db fixture is more robust.
        # 'DATABASE_NAME': db_path, # This is illustrative; monkeypatch is preferred.
        'CV_FORMAT_FILE_PATH': os.path.join(os.path.dirname(__file__), '..', 'CV_format.json') # Point to actual file
    })

    # Ensure the instance path exists for flask_app context
    try:
        os.makedirs(flask_app.instance_path, exist_ok=True)
    except OSError:
        pass # Should already exist or be creatable

    yield flask_app

    # Clean up: close and remove the temporary database file
    os.close(db_fd)
    os.unlink(db_path)
    # if os.path.exists(temp_env_path):
    #    os.unlink(temp_env_path)


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """A test runner for CLI commands."""
    return app.test_cli_runner()


@pytest.fixture(scope='function') # Use 'function' scope for a fresh DB per test
def test_db(app, monkeypatch):
    """Fixture to set up and tear down the database for each test function."""

    # Generate a unique database name for each test function to ensure isolation
    # Using in-memory for speed, but can be a temp file if needed for specific tests
    # For in-memory, each connection is distinct, so ensure app uses the same 'connection' or re-init for each test.
    # A common pattern is to patch the DATABASE_NAME to ':memory:' for the duration of the test.

    # Using a temporary file for the database for this specific test function
    db_fd, db_path = tempfile.mkstemp(suffix=f'_{pytest.current_test.name}.db')

    # Monkeypatch the DATABASE_NAME in app.database module
    # This ensures that any part of the app calling get_db_connection() or init_db()
    # within app.database will use this patched name.
    monkeypatch.setattr('app.database.DATABASE_NAME', db_path)

    # Initialize the database schema
    # init_db uses the (now patched) DATABASE_NAME
    with app.app_context():
        init_db() # This will create tables in the db_path

    yield db_path # Provide the path to the test database, can be used for direct connection if needed

    # Teardown: Close and remove the temporary database file
    os.close(db_fd)
    os.unlink(db_path)

    # Restore the original DATABASE_NAME if it was changed globally by monkeypatch,
    # though monkeypatch usually handles cleanup of its changes.
    # monkeypatch.setattr('app.database.DATABASE_NAME', ORIGINAL_DATABASE_NAME) # If needed

@pytest.fixture
def mock_google_api_key(monkeypatch):
    """Mocks the Google API key for tests that don't need real API calls."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test_google_api_key")
    # Also patch it in app.config if it's already loaded there
    # This depends on when create_app() is called relative to this fixture.
    # If app fixture is used, app.config is already set.
    # from flask import current_app
    # if current_app:
    #     monkeypatch.setitem(current_app.config, 'GOOGLE_API_KEY', 'test_google_api_key_config')


# Example of how to get a direct DB connection within a test, using the test_db fixture
# def test_example_direct_db_access(test_db):
#     conn = sqlite3.connect(test_db) # test_db is the path to the temp db file
#     # ... perform direct db operations ...
#     conn.close()

# Note: If your app.database.get_db_connection uses Flask's g object,
# ensure you are within an app_context for it to work, or mock/adapt accordingly.
# The current get_db_connection in the provided code is straightforward and doesn't use g.
# It directly uses the DATABASE_NAME module variable, which monkeypatch handles well.
