import os
import sys
import tempfile
from pathlib import Path

import pytest

# Point the module-level app at a throwaway DB so importing app.py never touches real data.
os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "import.db")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as app_module  # noqa: E402


class FakeModel:
    """Stands in for the LLM: records prompts and returns canned replies."""

    def __init__(self):
        self.calls = []
        self.reply = "What do you already know about this?"
        self.review = '{"understanding": 0.8, "summary": "Chain rule", "strengths": "Set up u", "gaps": "Forgot the inner derivative"}'
        self.fail = False

    def __call__(self, messages, temperature=0.2, json_mode=False):
        self.calls.append({"messages": messages, "json_mode": json_mode, "temperature": temperature})
        if self.fail:
            raise RuntimeError("model offline")
        return self.review if json_mode else self.reply


@pytest.fixture
def model(monkeypatch):
    fake = FakeModel()
    monkeypatch.setattr(app_module, "ask_model", fake)
    return fake


@pytest.fixture
def client(tmp_path, model):
    flask_app = app_module.create_app(tmp_path / "test.db", demo_account=False)
    flask_app.config["TESTING"] = True
    return flask_app.test_client()
