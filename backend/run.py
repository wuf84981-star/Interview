"""启动入口。

    cd backend
    uvicorn run:app --reload --port 8000
"""

from app.main import create_app

app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
