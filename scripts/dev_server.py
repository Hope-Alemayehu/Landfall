"""Local dev server: the website and its API on one origin, like the Vercel deployment.

Usage: python scripts/dev_server.py         then open http://127.0.0.1:8000
   or: uvicorn scripts.dev_server:app --reload

On Vercel, public/ is served by the CDN and api/index.py handles /api/*; here one
uvicorn process does both.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fastapi.staticfiles import StaticFiles

from api.index import app

# Mounted after the API routes, so /api/* still reaches them.
app.mount("/", StaticFiles(directory=os.path.join(ROOT, "public"), html=True), name="public")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
