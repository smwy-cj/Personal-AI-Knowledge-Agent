"""Serve a FastEmbed model through a minimal OpenAI-compatible local endpoint."""

from __future__ import annotations

import argparse
import json
import math
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 11435
DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_CACHE = "evaluations/private/embedding-models"
MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_INPUTS = 128
MAX_TOTAL_CHARACTERS = 1_000_000


class EmbeddingRequestError(ValueError):
    """A safe validation error that never contains request text."""


class EmbeddingService:
    def __init__(self, model: Any, model_name: str, dimension: int) -> None:
        if not model_name.strip():
            raise ValueError("model_name must be non-empty")
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self.model = model
        self.model_name = model_name
        self.dimension = dimension
        self._lock = threading.Lock()

    def health(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "model": self.model_name,
            "dimension": self.dimension,
        }

    def create_embeddings(self, document: Any) -> Dict[str, Any]:
        if not isinstance(document, dict):
            raise EmbeddingRequestError("request body must be a JSON object")
        if document.get("model") != self.model_name:
            raise EmbeddingRequestError("requested model is not available")
        texts = _normalize_inputs(document.get("input"))
        try:
            with self._lock:
                vectors = list(self.model.embed(texts))
        except Exception as exc:
            raise RuntimeError("embedding generation failed") from exc
        if len(vectors) != len(texts):
            raise RuntimeError("embedding model returned an invalid vector count")

        data = []
        for index, vector in enumerate(vectors):
            values = [float(value) for value in vector]
            if len(values) != self.dimension or not all(
                math.isfinite(value) for value in values
            ):
                raise RuntimeError("embedding model returned an invalid vector")
            data.append(
                {
                    "object": "embedding",
                    "index": index,
                    "embedding": values,
                }
            )
        return {"object": "list", "data": data, "model": self.model_name}


def _normalize_inputs(value: Any) -> List[str]:
    if isinstance(value, str):
        inputs = [value]
    elif isinstance(value, list):
        inputs = value
    else:
        raise EmbeddingRequestError("input must be a string or an array of strings")
    if not inputs or len(inputs) > MAX_INPUTS:
        raise EmbeddingRequestError("input count is outside the supported range")
    if any(not isinstance(item, str) or not item.strip() for item in inputs):
        raise EmbeddingRequestError("every input must be a non-empty string")
    if sum(len(item) for item in inputs) > MAX_TOTAL_CHARACTERS:
        raise EmbeddingRequestError("input text exceeds the supported size")
    return inputs


class LocalEmbeddingHandler(BaseHTTPRequestHandler):
    server_version = "PersonalAIEmbedding/1.0"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        if self.path != "/health":
            self._send_json(404, _error_document("endpoint not found", "not_found"))
            return
        self._send_json(200, self._service.health())

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        if self.path != "/v1/embeddings":
            self._send_json(404, _error_document("endpoint not found", "not_found"))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length <= 0:
            self._send_json(
                400, _error_document("request body is required", "invalid_request_error")
            )
            return
        if length > MAX_REQUEST_BYTES:
            self._send_json(
                413, _error_document("request body is too large", "invalid_request_error")
            )
            return
        try:
            document = json.loads(self.rfile.read(length).decode("utf-8"))
            response = self._service.create_embeddings(document)
        except (UnicodeError, json.JSONDecodeError):
            self._send_json(
                400, _error_document("request body must be valid JSON", "invalid_request_error")
            )
            return
        except EmbeddingRequestError as exc:
            self._send_json(400, _error_document(str(exc), "invalid_request_error"))
            return
        except Exception:
            self._send_json(
                500, _error_document("embedding generation failed", "server_error")
            )
            return
        self._send_json(200, response)

    @property
    def _service(self) -> EmbeddingService:
        return self.server.embedding_service  # type: ignore[attr-defined]

    def _send_json(self, status: int, document: Dict[str, Any]) -> None:
        payload = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        # BaseHTTPRequestHandler logs only method/path/status; request bodies are
        # never included. Keep that behavior but use a stable local prefix.
        super().log_message("local-embedding " + format, *args)


def _error_document(message: str, error_type: str) -> Dict[str, Any]:
    return {"error": {"message": message, "type": error_type}}


def _load_fastembed_model(
    model_name: str, cache_dir: str, threads: int
) -> Tuple[Any, int]:
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:
        raise RuntimeError(
            "fastembed is not installed; install requirements-local-embedding.txt"
        ) from exc
    supported = {
        item["model"]: item for item in TextEmbedding.list_supported_models()
    }
    if model_name not in supported:
        raise RuntimeError("requested FastEmbed model is not supported")
    dimension = int(supported[model_name]["dim"])
    model = TextEmbedding(
        model_name=model_name,
        cache_dir=str(Path(cache_dir).resolve()),
        threads=threads,
    )
    return model, dimension


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a private OpenAI-compatible FastEmbed endpoint"
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Allow binding beyond loopback; disabled by default for privacy",
    )
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    if arguments.port <= 0 or arguments.port > 65535:
        raise SystemExit("port must be between 1 and 65535")
    if arguments.threads <= 0:
        raise SystemExit("threads must be positive")
    if (
        arguments.host not in {"127.0.0.1", "localhost", "::1"}
        and not arguments.allow_remote
    ):
        raise SystemExit("non-loopback binding requires --allow-remote")

    model, dimension = _load_fastembed_model(
        arguments.model, arguments.cache_dir, arguments.threads
    )
    service = EmbeddingService(model, arguments.model, dimension)
    server = ThreadingHTTPServer((arguments.host, arguments.port), LocalEmbeddingHandler)
    server.embedding_service = service  # type: ignore[attr-defined]
    print(
        "local embedding endpoint ready at http://%s:%s/v1 (model=%s, dimension=%s)"
        % (arguments.host, arguments.port, arguments.model, dimension),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
