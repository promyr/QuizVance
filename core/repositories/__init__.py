# -*- coding: utf-8 -*-
"""Repositories de acesso a dados (Prompt 4/5)."""

from .flashcard_repository import FlashcardRepository
from .question_progress_repository import QuestionProgressRepository
from .review_session_repository import ReviewSessionRepository

__all__ = [
    "FlashcardRepository",
    "QuestionProgressRepository",
    "ReviewSessionRepository",
]

