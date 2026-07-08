"""FeedbackExpert route registration.

The privacy-sensitive implementation is split by workflow. Keep this module as
the stable import path used by server registration and older tests.
"""
from fastapi import APIRouter

from .feedback_library import router as _library_router
from .feedback_manual import router as _manual_router
from .feedback_push import _push_payload, router as _push_router
from .feedback_run import router as _run_router

router = APIRouter(prefix="/api/feedback", tags=["feedback"])
router.include_router(_manual_router)
router.include_router(_library_router)
router.include_router(_run_router)
router.include_router(_push_router)

__all__ = ["router", "_push_payload"]
