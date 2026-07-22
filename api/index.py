"""Vercel Serverless Function entrypoint for Orchestra FastAPI backend."""
import sys
from pathlib import Path

# Add backend directory to Python path
backend_dir = str(Path(__file__).resolve().parent.parent / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from orchestra.api import app

# Export ASGI app for Vercel
__all__ = ["app"]
