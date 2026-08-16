from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
# 注意：处理器必须注册在 Starlette 的 HTTPException 上——路由未匹配的 404 抛的是
# 这个父类，注册在 fastapi.HTTPException（子类）上不会命中它
from starlette.exceptions import HTTPException as StarletteHTTPException

from eman.db import connect


def create_app(db_path: str = "eman.db") -> FastAPI:
    app = FastAPI(title="eman")
    app.state.db = connect(db_path)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request, exc):
        msg = exc.errors()[0].get("msg", "输入无效") if exc.errors() else "输入无效"
        return JSONResponse(status_code=422, content={"error": msg})

    # 路由在后续任务中逐个挂载到这里（保持在静态托管 mount 之前）

    return app
