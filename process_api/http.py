# -*- coding: utf-8 -*-
"""FastAPI /api/v2 适配层（ADR-013，可选依赖、只读端点）。

- 复用 :mod:`process_api` facade 的序列化形状——JSON 键名与冻结契约一致，
  React 客户端可在未来直接切换到 v2。
- 与既有 WebUI（`/api`，冻结不动）并行；默认不随主程序启动，独立运行：
  ``uvicorn process_api.http:app`` 或 ``create_app()`` 自行挂载。
- FastAPI/uvicorn 为可选依赖；未安装时导入本模块抛出明确的 ImportError。
- Facade 非线程安全：适配层按单会话单 worker 运行（uvicorn workers=1）。
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, Response

from .errors import ProcessCadError
from .facade import ProcessCadFacade
from .schemas import to_json

_STATUS_BY_CODE = {
    "unknown_demo": 404,
    "unknown_step": 404,
    "invalid_snapshot": 409,
    "unknown_material_mesh": 404,
    "stale_revision": 409,
    "no_recipe": 400,
    "empty_recipe": 400,
    "unknown_parameter": 400,
    "invalid_parameter": 400,
    "invalid_recipe": 400,
    "invalid_step": 400,
    "step_failed": 500,
}


def create_app(
    *,
    demo: str = "Basic Trench",
    grid: int = 64,
    title: str = "TCAD Process API (v2)",
) -> FastAPI:
    app = FastAPI(title=title, version="2", docs_url="/api/v2/docs")

    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    state: Dict[str, Any] = {"facade": None, "demo": None}

    def facade(demo_name: str | None = None) -> ProcessCadFacade:
        wanted = demo_name or demo
        if state["facade"] is None or state["demo"] != wanted:
            instance = ProcessCadFacade(grid=grid)
            instance.load_demo(wanted)
            state["facade"] = instance
            state["demo"] = wanted
        return state["facade"]

    def error_response(error: ProcessCadError) -> JSONResponse:
        return JSONResponse(
            status_code=_STATUS_BY_CODE.get(error.code, 500),
            content=error.to_json(),
        )

    @app.get("/api/v2/health")
    def health() -> Dict[str, Any]:
        return {"ok": True, "service": "process_api", "version": 2}

    @app.get("/api/v2/init")
    def init(demo: str | None = Query(default=None)) -> Dict[str, Any]:
        try:
            return to_json(facade(demo).init())
        except ProcessCadError as error:
            return error_response(error)  # type: ignore[return-value]

    @app.get("/api/v2/preview/manifest")
    def preview_manifest(
        mode: str = Query(default="solid"),
        face_limit: int = Query(default=40000, ge=1),
    ) -> Dict[str, Any]:
        try:
            return to_json(facade().preview_manifest(mode=mode, face_limit=face_limit))
        except ProcessCadError as error:
            return error_response(error)  # type: ignore[return-value]

    @app.get("/api/v2/preview/stl")
    def preview_stl(
        material_id: int = Query(alias="materialId"),
        revision: int = Query(ge=0),
        mode: str = Query(default="solid"),
    ) -> Response:
        try:
            data = facade().material_stl(material_id, revision, mode=mode)
        except ProcessCadError as error:
            return error_response(error)  # type: ignore[return-value]
        return Response(content=data, media_type="application/octet-stream")

    @app.post("/api/v2/recipe/parse")
    def parse_recipe(request: Dict[str, Any]) -> Dict[str, Any]:
        """M16：自然语言 → 结构化候选 Recipe + 校验结果。"""
        from recipe_planner import RecipeValidator, parse_natural_language

        text = str(request.get("text", "")).strip()
        if not text:
            return {"ok": False, "error": "text is required"}
        try:
            draft = parse_natural_language(text)
            validation = RecipeValidator().validate(draft)
            return {"ok": True, "draft": draft.to_dict(), "validation": validation}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    return app


app = create_app()
