"""Vercel Serverless Function entrypoint for Orchestra FastAPI backend."""
import sys
from pathlib import Path

import traceback

async def app(scope, receive, send):
    try:
        # Resolve backend path and import real app at runtime
        backend_dir = str(Path(__file__).resolve().parent.parent / "backend")
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

        from orchestra.api import app as real_app
        await real_app(scope, receive, send)
    except Exception as e:
        tb = traceback.format_exc()
        if scope["type"] == "http":
            error_data = (
                f'{{"status": "import_error", "error": "{str(e)}", '
                f'"traceback": "{tb.replace(chr(10), "\\n").replace(chr(34), "\\\"")}"}}'
            ).encode("utf-8")
            
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(error_data)).encode("utf-8"))
                ]
            })
            await send({
                "type": "http.response.body",
                "body": error_data,
                "more_body": False
            })
        else:
            raise

# Export ASGI app for Vercel
__all__ = ["app"]
