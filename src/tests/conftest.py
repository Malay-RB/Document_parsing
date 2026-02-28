import pytest
from loaders.model_loader import ModelLoader

@pytest.fixture(scope="session")
def shared_models():
    """Loads models once per test session. All tests share this instance."""
    print("\n🚀 Loading Real AI Models for Testing...")
    return ModelLoader().load()