"""Vercel Serverless Function entrypoint for Orchestra FastAPI backend."""
import sys
from pathlib import Path

try:
    # Add backend directory to Python path
    backend_dir = str(Path(__file__).resolve().parent.parent / "backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    from orchestra.api import app
except Exception as e:
    import traceback
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI()

    @app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
    async def fallback_error_handler(path_name: str):
        return JSONResponse(
            status_code=500,
            content={
                "status": "import_error",
                "error": str(e),
                "traceback": traceback.format_exc(),
                "sys_path": sys.path,
                "current_dir": str(Path.cwd()),
                "file_path": __file__,
            }
        )

# Export ASGI app for Vercel
__all__ = ["app"]
