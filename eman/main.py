from asyncio import Lock
from pathlib import Path
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
# 注意：处理器必须注册在 Starlette 的 HTTPException 上——路由未匹配的 404 抛的是
# 这个父类，注册在 fastapi.HTTPException（子类）上不会命中它
from starlette.exceptions import HTTPException as StarletteHTTPException

from eman import __version__
from eman.db import connect
from eman.routes import experiments as experiments_routes
from eman.routes import runs as runs_routes
from eman.routes import tags as tags_routes
from eman.routes import groups as groups_routes
from eman.routes import attempts as attempts_routes
from eman.routes import attachments as attachments_routes


def create_app(db_path: str = "eman.db") -> FastAPI:
    app = FastAPI(title="eman", version=__version__)
    app.state.db = connect(db_path)
    # 单连接必须串行使用；浏览器会并发请求卡片数据和多张缩略图。
    app.state.db_lock = Lock()

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request, exc):
        detail = exc.detail
        if detail in (None, "Not Found"):
            detail = "路径或资源不存在"
        elif detail == "Method Not Allowed":
            detail = "不支持该请求方法"
        return JSONResponse(status_code=exc.status_code, content={"error": detail})

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request, exc):
        if exc.errors():
            first = exc.errors()[0]
            msg = str(first.get("msg", "")).removeprefix("Value error, ")
            loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
            error = f"输入无效：{loc}：{msg}" if loc else f"输入无效：{msg}"
        else:
            error = "输入无效"
        return JSONResponse(status_code=422, content={"error": error})

    # 路由在后续任务中逐个挂载到这里（保持在静态托管 mount 之前）
    app.include_router(experiments_routes.router, prefix="/api")
    app.include_router(runs_routes.router, prefix="/api")
    app.include_router(tags_routes.router, prefix="/api")
    app.include_router(groups_routes.router, prefix="/api")
    app.include_router(attempts_routes.router, prefix="/api")
    app.include_router(attachments_routes.router, prefix="/api")

    static_dir = Path(__file__).resolve().parent.parent / "static"
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
