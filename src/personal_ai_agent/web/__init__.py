"""Flask application factory for the course WebUI."""

import os
import secrets
from hmac import compare_digest
from typing import Mapping, Optional
from uuid import uuid4

from flask import (
    Flask,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.exceptions import HTTPException

from .ports import ApplicationServiceWebAdapter, WebApplicationPort


def create_app(
    application_port: Optional[WebApplicationPort] = None,
    config_path: Optional[str] = None,
    test_config: Optional[Mapping[str, object]] = None,
) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        DEMO_MODE=_environment_flag("PERSONAL_AGENT_DEMO_MODE"),
        DEMO_DATA_ROOT=os.environ.get("PERSONAL_AGENT_DEMO_DATA_ROOT"),
        SECRET_KEY=os.environ.get("PERSONAL_AGENT_WEB_SECRET") or secrets.token_hex(32),
        CSRF_ENABLED=True,
        MAX_CONTENT_LENGTH=64 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_environment_flag("PERSONAL_AGENT_HTTPS"),
        PROPAGATE_EXCEPTIONS=False,
    )
    if test_config:
        app.config.update(test_config)

    if application_port is None:
        resolved_config = config_path or os.environ.get(
            "PERSONAL_AGENT_CONFIG", "agent.config.json"
        )
        application_port = ApplicationServiceWebAdapter.from_file(
            resolved_config,
            bool(app.config["DEMO_MODE"]),
            app.config.get("DEMO_DATA_ROOT"),
        )
    app.extensions["personal_ai_agent_port"] = application_port

    @app.context_processor
    def security_context():
        return {"csrf_token": _csrf_token}

    @app.before_request
    def verify_csrf():
        if not app.config["CSRF_ENABLED"] or request.method not in {
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        }:
            return None
        expected = session.get("_csrf_token")
        supplied = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")
        if not (
            isinstance(expected, str)
            and isinstance(supplied, str)
            and compare_digest(expected, supplied)
        ):
            return render_template(
                "error.html", status=400, message="请求验证失败，请刷新页面后重试"
            ), 400
        return None

    @app.after_request
    def apply_security_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; img-src 'self' data:; "
            "font-src 'self'; object-src 'none'; base-uri 'self'; "
            "form-action 'self'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        if request.is_secure or bool(app.config["SESSION_COOKIE_SECURE"]):
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    @app.get("/")
    def index():
        status = _port().knowledge_status()
        return render_template(
            "index.html", status=status, demo_mode=bool(app.config["DEMO_MODE"])
        )

    @app.get("/health")
    def health():
        return jsonify(_port().health())

    @app.get("/search")
    def search_page():
        attempted = "q" in request.args
        query = request.args.get("q", "")
        path_prefix = request.args.get("path_prefix", "").strip() or None
        tags = [item.strip() for item in request.args.getlist("tag") if item.strip()]
        raw_limit = request.args.get("limit", "10")
        results = None
        error = None
        limit = 10
        if attempted:
            query = query.strip()
            if not query:
                error = "请输入搜索内容。"
            elif len(query) > 500:
                error = "搜索内容不能超过 500 个字符。"
            try:
                limit = int(raw_limit)
                if limit < 1 or limit > 50:
                    raise ValueError
            except (TypeError, ValueError):
                error = error or "结果数量必须是 1 到 50 之间的整数。"
            if error is None:
                try:
                    results = _port().search(
                        query, limit, path_prefix, tags
                    )
                except ValueError:
                    error = "搜索条件无效，请检查后重试。"
        return (
            render_template(
                "search.html",
                query=query,
                limit=raw_limit,
                path_prefix=path_prefix or "",
                tags=tags,
                results=results,
                error=error,
                demo_mode=bool(app.config["DEMO_MODE"]),
            ),
            400 if error else 200,
        )

    @app.route("/research", methods=["GET", "POST"])
    def research_page():
        values = {
            "goal": request.form.get("goal", "") if request.method == "POST" else "",
            "thread_id": request.form.get("thread_id", "web") if request.method == "POST" else "web",
            "model_provider": request.form.get("model_provider", "") if request.method == "POST" else "",
            "embedding_provider": request.form.get("embedding_provider", "") if request.method == "POST" else "",
            "limit": request.form.get("limit", "8") if request.method == "POST" else "8",
            "language": request.form.get("language", "zh-CN") if request.method == "POST" else "zh-CN",
        }
        error = None
        if request.method == "POST":
            goal = values["goal"].strip()
            thread_id = values["thread_id"].strip()
            if not goal:
                error = "请输入研究目标。"
            elif len(goal) > 2000:
                error = "研究目标不能超过 2000 个字符。"
            elif not thread_id or len(thread_id) > 100:
                error = "Thread ID 必须是 1 到 100 个字符。"
            try:
                limit = int(values["limit"])
                if limit < 1 or limit > 20:
                    raise ValueError
            except (TypeError, ValueError):
                error = error or "检索数量必须是 1 到 20 之间的整数。"
            if error is None:
                result = _port().run_research(
                    goal,
                    thread_id,
                    model_provider_id=values["model_provider"].strip() or None,
                    embedding_provider_id=values["embedding_provider"].strip() or None,
                    limit=limit,
                    language=values["language"].strip() or "zh-CN",
                )
                task_id = _task_state(result)["task_id"]
                return redirect(url_for("task_page", task_id=task_id), code=303)
        return (
            render_template(
                "research.html",
                values=values,
                error=error,
                demo_mode=bool(app.config["DEMO_MODE"]),
            ),
            400 if error else 200,
        )

    @app.get("/tasks/<task_id>")
    def task_page(task_id):
        try:
            document = _port().show_task(task_id)
        except KeyError:
            return render_template(
                "error.html", status=404, message="任务不存在"
            ), 404
        state = _task_state(document)
        summary = _research_summary(state)
        return render_template(
            "task.html",
            state=state,
            summary=summary,
            demo_mode=bool(app.config["DEMO_MODE"]),
        )

    @app.post("/tasks/<task_id>/cancel")
    def task_cancel(task_id):
        try:
            _port().cancel_task(task_id)
        except KeyError:
            return render_template(
                "error.html", status=404, message="任务不存在"
            ), 404
        return redirect(url_for("task_page", task_id=task_id), code=303)

    @app.route("/tasks/<task_id>/memory", methods=["GET", "POST"])
    def memory_review(task_id):
        try:
            state = _task_state(_port().show_task(task_id))
        except KeyError:
            return render_template(
                "error.html", status=404, message="任务不存在"
            ), 404
        if state.get("status") != "WAITING_USER" or not state.get(
            "awaiting_user_approval"
        ):
            return render_template(
                "error.html", status=409, message="任务当前不等待记忆审批"
            ), 409
        candidates = _port().pending_memory_candidates(task_id)
        error = None
        if request.method == "POST":
            decisions = {
                item["candidate_id"]: request.form.get(
                    "decision_%s" % item["candidate_id"]
                )
                for item in candidates
            }
            if not candidates or any(
                decision not in {"approve", "reject"}
                for decision in decisions.values()
            ):
                error = "每个记忆候选都必须明确选择批准或拒绝。"
            else:
                approved = [key for key, value in decisions.items() if value == "approve"]
                rejected = [key for key, value in decisions.items() if value == "reject"]
                _port().resolve_memory(task_id, approved, rejected)
                return redirect(url_for("task_page", task_id=task_id), code=303)
        return (
            render_template(
                "memory_review.html",
                state=state,
                candidates=candidates,
                error=error,
                demo_mode=bool(app.config["DEMO_MODE"]),
            ),
            400 if error else 200,
        )

    @app.errorhandler(404)
    def not_found(error):
        if _wants_json():
            return jsonify({"error": "not_found"}), 404
        return render_template("error.html", status=404, message="页面不存在"), 404

    @app.errorhandler(413)
    def request_too_large(error):
        if _wants_json():
            return jsonify({"error": "request_too_large"}), 413
        return render_template(
            "error.html", status=413, message="请求内容过大"
        ), 413

    @app.errorhandler(Exception)
    def internal_error(error):
        if isinstance(error, HTTPException):
            return error
        correlation_id = uuid4().hex
        if request.path == "/health" or _wants_json():
            return (
                jsonify(
                    {
                        "error": "internal_error",
                        "correlation_id": correlation_id,
                    }
                ),
                500,
            )
        return (
            render_template(
                "error.html",
                status=500,
                message="服务暂时不可用",
                correlation_id=correlation_id,
            ),
            500,
        )

    return app


def _port() -> WebApplicationPort:
    return current_app.extensions["personal_ai_agent_port"]


def _csrf_token() -> str:
    token = session.get("_csrf_token")
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def _wants_json() -> bool:
    return request.accept_mimetypes.best == "application/json"


def _task_state(document):
    if not isinstance(document, dict) or not isinstance(document.get("state"), dict):
        raise ValueError("task response is invalid")
    return document["state"]


def _research_summary(state):
    for artifact in state.get("artifacts", []):
        if artifact.get("artifact_type") == "research_summary":
            return artifact.get("content")
    return None


def _environment_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


__all__ = ["create_app", "ApplicationServiceWebAdapter", "WebApplicationPort"]
