import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import mcp
from app.db import get_db

router = APIRouter()
logger = logging.getLogger("paypilot.mcp")

ERR_INTERNAL = -32603  # JSON-RPC 2.0 reserved: "Internal error"


@router.post("/mcp")
async def mcp_endpoint(request: Request, db: Session = Depends(get_db)):
    """JSON-RPC 2.0 endpoint. Envelope: {"jsonrpc": "2.0", "id": ..., "method": ..., "params": ...}."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - malformed JSON is a protocol-level parse error
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error: invalid JSON"}},
            status_code=200,  # JSON-RPC errors are carried in the body, not the HTTP status
        )

    request_id = body.get("id")
    method = body.get("method")
    params = body.get("params")

    if not method:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32600, "message": "missing method"}}

    try:
        result = mcp.dispatch(db, method, params)
    except mcp.RpcError as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": exc.code, "message": exc.message}}
    except Exception:  # noqa: BLE001 - keep the JSON-RPC contract, never a raw 500
        logger.exception("unhandled error dispatching MCP method %s", method)
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": ERR_INTERNAL, "message": "internal error"}}

    return {"jsonrpc": "2.0", "id": request_id, "result": result}
