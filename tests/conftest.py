import os
import tempfile

import pytest

from app.database import init_db
from app.main import create_app

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope='session')
def app(tmp_path_factory):
    """Create and configure a new app instance for the test session.

    All output (database, uploads, generated files) goes to a temporary directory so
    tests never touch the real instance/ folder.
    """
    base = tmp_path_factory.mktemp("instance")
    flask_app = create_app({
        'TESTING': True,
        'DATABASE': str(base / 'session.db'),
        'UPLOAD_FOLDER': str(base / 'uploads'),
        'GENERATED_PDFS_FOLDER': str(base / 'pdfs'),
        'GENERATED_JSONS_FOLDER': str(base / 'jsons'),
        'BATCH_MAX_WORKERS': 1,  # deterministic ordering for mocked side effects
        'CV_FORMAT_FILE_PATH': os.path.join(PROJECT_ROOT, 'CV_format.json'),
        'AUTOAPPLY_PROFILE_DIR': str(base / 'browser_profile'),
        'AUTOAPPLY_UPLOADS_FOLDER': str(base / 'autoapply_uploads'),
        'AUTOAPPLY_SCREENSHOTS_FOLDER': str(base / 'autoapply_screens'),
        'AUTOAPPLY_HEADLESS': True,
    })
    yield flask_app
    flask_app.extensions['autoapply'].stop()


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture(scope='function')
def test_db(app, monkeypatch, request):
    """A fresh, empty database file for each test function."""
    db_fd, db_path = tempfile.mkstemp(suffix=f'_{request.node.name}.db')
    os.close(db_fd)
    monkeypatch.setattr('app.database.DATABASE_NAME', db_path)
    init_db()

    yield db_path

    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def mock_google_api_key(monkeypatch):
    """Pretends a Google API key is configured (no real API calls are made in tests)."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test_google_api_key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
