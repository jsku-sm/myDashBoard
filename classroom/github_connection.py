"""GitHub-only backend factory. No external database client is imported.

This module is package-local and never imports a legacy root backend.py.
No implicit local storage, database setup, or existing-data migration takes place.
"""
from __future__ import annotations
from cryptography.fernet import Fernet
from .storage import AppError, EncryptedStore, GitHubBackend
from .service import Classroom


def connect_github(*, repo: str, token: str, encryption_key: str,
                   branch: str = "main", teacher_id: str = "teacher",
                   initial_password: str = "", api_key: str = "", model: str = "") -> Classroom:
    """Open an encrypted GitHub store and create the first teacher only if empty.

    The token must be restricted to the private DATA repository. Never commit
    the token, encryption key, or plaintext passwords in the CODE repository.
    Missing credentials, public repositories, and failed writes are rejected.
    """
    repo, token, encryption_key = repo.strip(), token.strip(), encryption_key.strip()
    branch, teacher_id = branch.strip() or "main", teacher_id.strip() or "teacher"
    missing = [name for name, value in (
        ("GITHUB_REPO", repo), ("GITHUB_TOKEN", token), ("ENCRYPTION_KEY", encryption_key)
    ) if not value]
    if missing:
        raise AppError("Streamlit Secrets에 다음 값을 입력하세요: " + ", ".join(missing))
    # Validate locally before any network request or teacher creation.
    try:
        Fernet(encryption_key.encode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise AppError("ENCRYPTION_KEY 형식을 확인하세요. 첫 설정 화면에서 생성한 키를 사용하세요.") from exc
    backend = GitHubBackend(token, repo, branch)
    store = EncryptedStore(backend, encryption_key)
    service = Classroom(store, api_key=api_key, model=model)
    service.auth.bootstrap(teacher_id, initial_password)
    return service
