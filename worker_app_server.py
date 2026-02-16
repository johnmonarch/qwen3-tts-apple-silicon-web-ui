from __future__ import annotations

import os

import uvicorn


if __name__ == "__main__":
    host = os.getenv("WORKER_HOST", "127.0.0.1")
    port = int(os.getenv("WORKER_PORT", "7861"))
    uvicorn.run("worker_app.main:app", host=host, port=port, reload=False)
