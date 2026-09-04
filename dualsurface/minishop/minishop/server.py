from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Cookie, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from minishop.actions import IllegalAction, apply_action
from minishop.catalog import in_stock_sizes, load_catalog, load_tasks, product_by_id
from minishop.grader import grade
from minishop.state import Store
from minishop.surface import build_surface
from minishop.tools import tool_schemas

PACKAGE_DIR = Path(__file__).resolve().parent
catalog = load_catalog()
tasks = load_tasks()
store = Store(catalog)
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))

app = FastAPI(title="MiniShop")
app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")


class ActBody(BaseModel):
    session_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    enforce_surface: bool


def _task_by_id(task_id: str) -> dict[str, Any]:
    for task in tasks:
        if task["id"] == task_id:
            return task
    raise HTTPException(status_code=404, detail="unknown task")


def _session_or_404(session_id: str) -> dict[str, Any]:
    try:
        return store.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown session") from exc


def _resolve_session_id(request: Request, session_cookie: str | None) -> str:
    session_id = session_cookie or request.query_params.get("session_id")
    if session_id:
        try:
            store.get(session_id)
            return session_id
        except KeyError:
            pass
    return store.new_session()


def _ctx(request: Request, session_id: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    session = store.get(session_id)
    context = {
        "request": request,
        "session_id": session_id,
        "session": session,
        "catalog": catalog,
        "cart_count": len(session.get("cart") or []),
        "error": None,
        "illegal": False,
        "view": session.get("view"),
        "query": "",
        "active_filter": "",
    }
    if extra:
        context.update(extra)
    return context


def _render(
    request: Request,
    name: str,
    session_id: str,
    extra: dict[str, Any] | None = None,
    status_code: int = 200,
):
    response = templates.TemplateResponse(
        request, name, _ctx(request, session_id, extra), status_code=status_code
    )
    response.set_cookie("session_id", session_id)
    return response


@app.post("/agent/session")
def create_session() -> dict[str, str]:
    return {"session_id": store.new_session()}


@app.get("/agent/surface")
def agent_surface(session_id: str = Query(...)) -> dict[str, Any]:
    session = _session_or_404(session_id)
    return build_surface(session, catalog)


@app.get("/agent/tools")
def agent_tools() -> dict[str, Any]:
    return {"tools": tool_schemas()}


@app.post("/agent/act")
def agent_act(body: ActBody) -> JSONResponse:
    _session_or_404(body.session_id)
    try:
        result = apply_action(
            store,
            catalog,
            body.session_id,
            body.name,
            body.arguments,
            enforce_surface=body.enforce_surface,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown session") from exc
    except IllegalAction as exc:
        return JSONResponse(status_code=400, content={"illegal": True, "error": exc.message})
    return JSONResponse(result)


@app.get("/agent/state")
def agent_state(session_id: str = Query(...)) -> dict[str, Any]:
    _session_or_404(session_id)
    return store.snapshot(session_id)


@app.get("/agent/tasks")
def agent_tasks() -> dict[str, Any]:
    return {"tasks": tasks}


@app.get("/agent/grade")
def agent_grade(session_id: str = Query(...), task_id: str = Query(...)) -> dict[str, Any]:
    session = _session_or_404(session_id)
    return grade(session, _task_by_id(task_id))


@app.get("/", response_class=HTMLResponse)
def human_catalog(
    request: Request,
    session_id: str | None = Cookie(default=None),
    q: str | None = None,
    filter: str | None = None,
):
    sid = _resolve_session_id(request, session_id)
    session = store.get(sid)
    if session["view"] != "catalog":
        apply_action(store, catalog, sid, "go_catalog", {}, enforce_surface=False)
    _ = q, filter
    return _render(request, "catalog.html", sid, {"query": q or "", "active_filter": filter or ""})


@app.get("/product/{product_id}", response_class=HTMLResponse)
def human_product(
    request: Request,
    product_id: str,
    session_id: str | None = Cookie(default=None),
):
    product = product_by_id(catalog, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="unknown product")
    sid = _resolve_session_id(request, session_id)
    session = store.get(sid)
    if session["view"] != "product" or session.get("product_id") != product_id:
        apply_action(store, catalog, sid, "open_product", {"product_id": product_id}, enforce_surface=False)
    related = [item for item in catalog if item["id"] != product_id][:3]
    return _render(
        request,
        "product.html",
        sid,
        {"product": product, "available": in_stock_sizes(product), "related": related},
    )


@app.post("/product/{product_id}/size")
def human_set_size(
    request: Request,
    product_id: str,
    size: str = Form(...),
    session_id: str | None = Cookie(default=None),
):
    sid = _resolve_session_id(request, session_id)
    session = store.get(sid)
    if session.get("product_id") != product_id or session.get("view") != "product":
        apply_action(store, catalog, sid, "open_product", {"product_id": product_id}, enforce_surface=False)
    try:
        apply_action(store, catalog, sid, "set_size", {"size": size}, enforce_surface=False)
    except IllegalAction as exc:
        product = product_by_id(catalog, product_id)
        related = [item for item in catalog if item["id"] != product_id][:3]
        return _render(
            request,
            "product.html",
            sid,
            {
                "product": product,
                "available": in_stock_sizes(product) if product else [],
                "related": related,
                "error": exc.message,
                "illegal": True,
            },
            status_code=400,
        )
    response = RedirectResponse(url=f"/product/{product_id}", status_code=303)
    response.set_cookie("session_id", sid)
    return response


@app.post("/product/{product_id}/add", response_class=HTMLResponse)
def human_add_to_cart(
    request: Request,
    product_id: str,
    session_id: str | None = Cookie(default=None),
):
    sid = _resolve_session_id(request, session_id)
    session = store.get(sid)
    if session.get("product_id") != product_id or session.get("view") != "product":
        apply_action(store, catalog, sid, "open_product", {"product_id": product_id}, enforce_surface=False)
    error = None
    try:
        apply_action(store, catalog, sid, "add_to_cart", {}, enforce_surface=False)
    except IllegalAction as exc:
        error = exc.message
    product = product_by_id(catalog, product_id)
    related = [item for item in catalog if item["id"] != product_id][:3]
    return _render(
        request,
        "product.html",
        sid,
        {
            "product": product,
            "available": in_stock_sizes(product) if product else [],
            "related": related,
            "error": error,
            "illegal": bool(error),
        },
        status_code=400 if error else 200,
    )


@app.get("/checkout", response_class=HTMLResponse)
def human_checkout(request: Request, session_id: str | None = Cookie(default=None)):
    sid = _resolve_session_id(request, session_id)
    session = store.get(sid)
    if session["view"] not in {"checkout", "confirmation"}:
        apply_action(store, catalog, sid, "go_checkout", {}, enforce_surface=False)
        session = store.get(sid)
    template = "confirmation.html" if session["view"] == "confirmation" else "checkout.html"
    orders = session.get("orders") or []
    return _render(request, template, sid, {"order": orders[-1] if orders else None})


@app.post("/checkout/address")
def human_set_address(
    request: Request,
    address: str = Form(""),
    session_id: str | None = Cookie(default=None),
):
    sid = _resolve_session_id(request, session_id)
    session = store.get(sid)
    if session.get("view") != "checkout":
        apply_action(store, catalog, sid, "go_checkout", {}, enforce_surface=False)
    try:
        apply_action(store, catalog, sid, "set_address", {"address": address}, enforce_surface=False)
    except IllegalAction as exc:
        return _render(
            request,
            "checkout.html",
            sid,
            {"error": exc.message, "illegal": True, "order": None},
            status_code=400,
        )
    response = RedirectResponse(url="/checkout", status_code=303)
    response.set_cookie("session_id", sid)
    return response


@app.post("/checkout/pay", response_class=HTMLResponse)
def human_pay(request: Request, session_id: str | None = Cookie(default=None)):
    sid = _resolve_session_id(request, session_id)
    session = store.get(sid)
    if session.get("view") != "checkout":
        apply_action(store, catalog, sid, "go_checkout", {}, enforce_surface=False)
    error = None
    try:
        apply_action(store, catalog, sid, "pay", {}, enforce_surface=False)
    except IllegalAction as exc:
        error = exc.message
    session = store.get(sid)
    if error:
        return _render(
            request,
            "checkout.html",
            sid,
            {"error": error, "illegal": True, "order": None},
            status_code=400,
        )
    orders = session.get("orders") or []
    return _render(request, "confirmation.html", sid, {"order": orders[-1] if orders else None})


@app.get("/help/{slug}", response_class=HTMLResponse)
def human_help(request: Request, slug: str, session_id: str | None = Cookie(default=None)):
    sid = _resolve_session_id(request, session_id)
    titles = {
        "shipping": "Shipping & returns",
        "gift-cards": "Gift cards",
        "lookbook": "Lookbook",
        "stores": "Store locator",
        "size-guide": "Size guide",
        "care": "Fabric care",
    }
    return _render(request, "help.html", sid, {"help_title": titles.get(slug, "Help"), "slug": slug})
