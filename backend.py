"""Compatibility export for GitHub-only storage. The app does not import this file."""
from classroom.github_connection import connect_github

__all__ = ["connect_github"]
