from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional
from datetime import timedelta

import yaml
from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.db import DialogueDB
from app.schemas import ASREvent, DialogueEvent, EmotionEvent, FusionEvent, Offer
from app.state import AppState, EventBus, LatestFrameStore
from app.sse import event_stream
from app.webrtc import handle_offer
from app.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Auth-related models
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@app.on_event("startup")
async def on_startup() -> None:
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    db_path = os.path.join(data_dir, "dialogue.db")
    db = DialogueDB(db_path)
    db.init()
    session_id = db.create_session()

    app.state.ctx = AppState(
        frame_store=LatestFrameStore(),
        event_bus=EventBus(),
        db=db,
        session_id=session_id,
        pcs=set(),
        latest_status={},
    )
    
    # Initialize volume setting (default 50%)
    app.state.ctx.audio_volume = 50


@app.on_event("shutdown")
async def on_shutdown() -> None:
    pcs = app.state.ctx.pcs
    for pc in list(pcs):
        await pc.close()
        pcs.discard(pc)


@app.get("/api/stream")
async def stream(request: Request, token: Optional[str] = None) -> StreamingResponse:
    # Verify token (if provided)
    if token:
        try:
            from app.auth import verify_token
            verify_token(token)
        except HTTPException:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
    
    queue = app.state.ctx.event_bus.subscribe()

    async def _disconnect_checker() -> bool:
        return await request.is_disconnected()

    async def generator():
        try:
            async for message in event_stream(queue, _disconnect_checker):
                yield message
        finally:
            app.state.ctx.event_bus.unsubscribe(queue)

    return StreamingResponse(generator(), media_type="text/event-stream")


@app.post("/api/webrtc/offer")
async def webrtc_offer(offer: Offer) -> dict:
    try:
        return await handle_offer(
            offer.dict(),
            frame_store=app.state.ctx.frame_store,
            pcs=app.state.ctx.pcs,
            fps=30,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error handling WebRTC offer: {str(e)}")


@app.post("/api/vision/frame")
async def vision_frame(
    request: Request,
    timestamp: float,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> dict:
    # Limit JPEG file size (max 10MB)
    MAX_FRAME_SIZE = 10 * 1024 * 1024  # 10MB
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_FRAME_SIZE:
        raise HTTPException(status_code=413, detail="Frame size exceeds maximum allowed size (10MB)")
    
    jpeg_bytes = await request.body()
    
    # 验证实际接收的数据大小
    if len(jpeg_bytes) > MAX_FRAME_SIZE:
        raise HTTPException(status_code=413, detail="Frame size exceeds maximum allowed size (10MB)")
    
    # Validate timestamp is valid number
    if not isinstance(timestamp, (int, float)) or timestamp < 0:
        raise HTTPException(status_code=400, detail="Invalid timestamp")
    
    # Validate width and height (if provided)
    if width is not None and (not isinstance(width, int) or width <= 0 or width > 10000):
        raise HTTPException(status_code=400, detail="Invalid width")
    if height is not None and (not isinstance(height, int) or height <= 0 or height > 10000):
        raise HTTPException(status_code=400, detail="Invalid height")
    
    try:
        ok = app.state.ctx.frame_store.update_from_jpeg(
            jpeg_bytes, timestamp=timestamp, width=width, height=height
        )
        if not ok:
            raise HTTPException(status_code=400, detail="Failed to decode JPEG frame")
        return {"ok": ok}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing frame: {str(e)}")


@app.post("/api/events/ser")
async def event_ser(event: EmotionEvent) -> dict:
    payload = {"type": "emotion_ser", **event.dict()}
    await app.state.ctx.event_bus.publish(payload)
    app.state.ctx.latest_status["ser"] = payload
    return {"ok": True}


@app.post("/api/events/fer")
async def event_fer(event: EmotionEvent) -> dict:
    payload = {"type": "emotion_fer", **event.dict()}
    await app.state.ctx.event_bus.publish(payload)
    app.state.ctx.latest_status["fer"] = payload
    return {"ok": True}


@app.post("/api/events/fusion")
async def event_fusion(event: FusionEvent) -> dict:
    payload = {"type": "emotion_fusion", **event.dict()}
    await app.state.ctx.event_bus.publish(payload)
    app.state.ctx.latest_status["fusion"] = payload
    return {"ok": True}


@app.post("/api/events/asr")
async def event_asr(event: ASREvent) -> dict:
    payload = {"type": "asr_event", **event.dict()}
    await app.state.ctx.event_bus.publish(payload)
    return {"ok": True}


@app.post("/api/events/dialogue")
async def event_dialogue(event: DialogueEvent) -> dict:
    try:
        payload = {"type": "dialogue_event", **event.dict()}
        await app.state.ctx.event_bus.publish(payload)
        app.state.ctx.db.insert_dialogue(
            session_id=app.state.ctx.session_id,
            role=event.role,
            content=event.content,
            timestamp=event.timestamp,
            emotion_label=event.emotion_label,
            valence=event.valence,
            arousal=event.arousal,
            dominance=event.dominance,
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing dialogue event: {str(e)}")


@app.post("/api/status")
async def status_update(payload: dict) -> dict:
    # Validate payload is dict type
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be a dictionary")
    
    # Limit payload size (max 1MB)
    import json
    payload_size = len(json.dumps(payload))
    if payload_size > 1024 * 1024:  # 1MB
        raise HTTPException(status_code=413, detail="Payload size exceeds maximum allowed size (1MB)")
    
    try:
        payload["type"] = "status_event"
        await app.state.ctx.event_bus.publish(payload)
        app.state.ctx.latest_status["status"] = payload
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating status: {str(e)}")


@app.get("/api/status")
async def status_get() -> dict:
    return {
        "session_id": app.state.ctx.session_id,
        "latest": app.state.ctx.latest_status,
    }


@app.get("/api/dialogue/history")
async def dialogue_history() -> dict:
    return {"items": app.state.ctx.db.list_dialogue(app.state.ctx.session_id)}


@app.post("/api/dialogue/clear")
async def dialogue_clear() -> dict:
    app.state.ctx.db.clear_dialogue(app.state.ctx.session_id)
    await app.state.ctx.event_bus.publish({"type": "dialogue_cleared"})
    return {"ok": True}


@app.get("/api/dialogue/export")
async def dialogue_export(format: str = "json") -> Response:
    # 验证format参数
    if format not in ("json", "csv"):
        raise HTTPException(status_code=400, detail="format must be 'json' or 'csv'")
    
    try:
        mime, content = app.state.ctx.db.export_dialogue(
            app.state.ctx.session_id, format
        )
        filename = f"dialogue_{int(time.time())}.{format}"
        return Response(
            content=content,
            media_type=mime,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error exporting dialogue: {str(e)}")


@app.post("/api/audio/volume")
async def audio_volume(volume_data: dict) -> dict:
    """
    Set audio volume.
    
    Args:
        volume_data: Dict with volume (0-100)
    """
    if not isinstance(volume_data, dict):
        raise HTTPException(status_code=400, detail="volume_data must be a dictionary")
    
    volume = volume_data.get("volume", 50)
    
    # Validate volume type and range
    if not isinstance(volume, (int, float)):
        raise HTTPException(status_code=400, detail="volume must be a number")
    
    # 限制音量范围在 0-100
    volume = max(0, min(100, int(volume)))
    
    try:
        # Save to app state
        app.state.ctx.audio_volume = volume
        
        # Write volume to file for main process to read
        data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        os.makedirs(data_dir, exist_ok=True)
        volume_file = os.path.join(data_dir, "audio_volume.txt")
        with open(volume_file, "w") as f:
            f.write(str(volume))
        
        # Publish volume update via event bus
        await app.state.ctx.event_bus.publish({
            "type": "audio_volume_update",
            "volume": volume,
        })
        
        return {"ok": True, "volume": volume}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating volume: {str(e)}")


@app.get("/api/audio/volume")
async def audio_volume_get() -> dict:
    """Get current audio volume."""
    volume = getattr(app.state.ctx, "audio_volume", 50)
    return {"volume": volume}


def _get_project_root() -> Path:
    """Get project root directory."""
    # From web_monitor/backend/app/main.py to project root
    current_file = Path(__file__).resolve()
    # web_monitor/backend/app/main.py -> web_monitor/backend/app -> web_monitor/backend -> web_monitor -> project_root
    return current_file.parent.parent.parent.parent


def _get_default_llm_config() -> dict:
    """Get default LLM config."""
    import sys
    project_root = _get_project_root()
    # Add project root to Python path
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from utils.config import load_config
    # Load default config (no config.yaml, use defaults only)
    cfg = load_config()
    return {
        "n_ctx": cfg["llm"]["n_ctx"],
        "n_threads": cfg["llm"]["n_threads"],
        "max_tokens": cfg["llm"]["max_tokens"],
        "temperature": cfg["llm"]["temperature"],
        "top_p": cfg["llm"]["top_p"],
        "repeat_penalty": cfg["llm"]["repeat_penalty"],
        "prompt": cfg["llm"].get("prompt", {}),
    }


@app.get("/api/health")
async def health_check() -> dict:
    """健康检查端点"""
    return {"status": "ok", "message": "Server is running"}


@app.post("/api/auth/login")
async def login(login_data: LoginRequest) -> TokenResponse:
    """User login"""
    user = authenticate_user(login_data.username, login_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )
    return TokenResponse(access_token=access_token, token_type="bearer")


@app.get("/api/auth/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)) -> dict:
    """获取当前用户信息"""
    return {"username": current_user["username"]}


@app.get("/api/llm/config")
async def llm_config_get() -> dict:
    """获取LLM配置（返回默认配置）"""
    return {"config": _get_default_llm_config()}


@app.post("/api/llm/config")
async def llm_config_update(config_data: dict) -> dict:
    """
    更新LLM配置
    
    配置会立即生效（主程序会自动检测配置文件变化并重新加载）
    下次启动主程序时会恢复为默认配置
    """
    # 验证输入
    if not isinstance(config_data, dict):
        raise HTTPException(status_code=400, detail="config_data must be a dictionary")
    
    llm_config = config_data.get("config", {})
    if not isinstance(llm_config, dict):
        raise HTTPException(status_code=400, detail="config must be a dictionary")
    
    # Validate parameter ranges
    if "n_ctx" in llm_config:
        n_ctx = llm_config["n_ctx"]
        if not isinstance(n_ctx, int) or n_ctx < 512 or n_ctx > 8192:
            raise HTTPException(status_code=400, detail="n_ctx must be between 512 and 8192")
    
    if "n_threads" in llm_config:
        n_threads = llm_config["n_threads"]
        if not isinstance(n_threads, int) or n_threads < 1 or n_threads > 32:
            raise HTTPException(status_code=400, detail="n_threads must be between 1 and 32")
    
    if "max_tokens" in llm_config:
        max_tokens = llm_config["max_tokens"]
        if not isinstance(max_tokens, int) or max_tokens < 1 or max_tokens > 2000:
            raise HTTPException(status_code=400, detail="max_tokens must be between 1 and 2000")
    
    if "temperature" in llm_config:
        temperature = llm_config["temperature"]
        if not isinstance(temperature, (int, float)) or temperature < 0 or temperature > 2:
            raise HTTPException(status_code=400, detail="temperature must be between 0 and 2")
    
    if "top_p" in llm_config:
        top_p = llm_config["top_p"]
        if not isinstance(top_p, (int, float)) or top_p < 0 or top_p > 1:
            raise HTTPException(status_code=400, detail="top_p must be between 0 and 1")
    
    if "repeat_penalty" in llm_config:
        repeat_penalty = llm_config["repeat_penalty"]
        if not isinstance(repeat_penalty, (int, float)) or repeat_penalty < 0.5 or repeat_penalty > 2:
            raise HTTPException(status_code=400, detail="repeat_penalty must be between 0.5 and 2")
    
    # 验证prompt配置字符串长度
    if "prompt" in llm_config:
        prompt_config = llm_config["prompt"]
        if not isinstance(prompt_config, dict):
            raise HTTPException(status_code=400, detail="prompt must be a dictionary")
        
        max_prompt_length = 10000  # 最大10KB
        for key, value in prompt_config.items():
            if isinstance(value, str) and len(value) > max_prompt_length:
                raise HTTPException(status_code=400, detail=f"prompt.{key} exceeds maximum length ({max_prompt_length} characters)")
    
    try:
        project_root = _get_project_root()
        config_path = project_root / "config.yaml"
        
        # Read existing config
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as f:
                full_config = yaml.safe_load(f) or {}
        else:
            full_config = {}
        
        # Update LLM config
        if "llm" not in full_config:
            full_config["llm"] = {}
        
        # Update basic params
        if "n_ctx" in llm_config:
            full_config["llm"]["n_ctx"] = llm_config["n_ctx"]
        if "n_threads" in llm_config:
            full_config["llm"]["n_threads"] = llm_config["n_threads"]
        if "max_tokens" in llm_config:
            full_config["llm"]["max_tokens"] = llm_config["max_tokens"]
        if "temperature" in llm_config:
            full_config["llm"]["temperature"] = llm_config["temperature"]
        if "top_p" in llm_config:
            full_config["llm"]["top_p"] = llm_config["top_p"]
        if "repeat_penalty" in llm_config:
            full_config["llm"]["repeat_penalty"] = llm_config["repeat_penalty"]
        
        # Update prompt config
        if "prompt" in llm_config:
            if "prompt" not in full_config["llm"]:
                full_config["llm"]["prompt"] = {}
            prompt_config = llm_config["prompt"]
            if "system_part" in prompt_config:
                full_config["llm"]["prompt"]["system_part"] = prompt_config["system_part"]
            if "emotion_prefix" in prompt_config:
                full_config["llm"]["prompt"]["emotion_prefix"] = prompt_config["emotion_prefix"]
            if "history_format" in prompt_config:
                full_config["llm"]["prompt"]["history_format"] = prompt_config["history_format"]
            if "user_prefix" in prompt_config:
                full_config["llm"]["prompt"]["user_prefix"] = prompt_config["user_prefix"]
            if "assistant_prefix" in prompt_config:
                full_config["llm"]["prompt"]["assistant_prefix"] = prompt_config["assistant_prefix"]
        
        # Write config file
        with config_path.open("w", encoding="utf-8") as f:
            yaml.dump(full_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        return {"ok": True, "message": "Configuration updated and effective. Will revert to default on next main process start."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating LLM config: {str(e)}")
