import helix_orchestration


def test_public_api_has_release_version() -> None:
    assert helix_orchestration.__version__ == "0.1.0"
