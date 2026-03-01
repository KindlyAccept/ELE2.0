# main.py
"""
Emotion Robot main program - Voice + Vision interaction version.

Features:
1. Voice input (microphone -> ASR)
2. Speech emotion recognition (SER)
3. Visual emotion recognition (camera -> Face -> FER)
4. Multimodal emotion fusion (Fusion)
5. Dialogue generation (LLM)
6. Voice output (TTS)

Run: python main.py
"""
from __future__ import annotations

import os
import sys
import time
import threading
import cv2
import yaml
from pathlib import Path

# Import cognitive modules
from cognitive.llm_engine import LLMEngine
from cognitive.dialogue_manager import DialogueManager
from cognitive.retriever import KnowledgeRetriever
from action.tts_engine import TTSEngine

# Import perception modules
from io_devices.audio_service import AudioService
from io_devices.camera_service import CameraService
from perception.asr import ASREngine
from perception.ser import SEREngine
from perception.face_detection import FaceDetector
from perception.fer import FEREngine, FERSmoother

# 导入融合模块
from fusion.emotion_fusion import EmotionFusion
from utils.message_types import VisionFERMsg, now_ts
from utils.config import load_config
from perception.streaming import StreamingVoiceInteraction
from utils.http_reporter import HttpReporter


class VisionThread(threading.Thread):
    """
    Vision processing background thread.
    Continuously runs: camera -> face detection -> expression recognition -> emotion fusion.
    """
    def __init__(
        self, 
        camera: CameraService, 
        face_detector: FaceDetector, 
        fer_engine: FEREngine, 
        fer_smoother: FERSmoother, 
        emotion_fusion: EmotionFusion,
        reporter: HttpReporter | None = None,
    ):
        super().__init__()
        self.camera = camera
        self.face_detector = face_detector
        self.fer_engine = fer_engine
        self.fer_smoother = fer_smoother
        self.emotion_fusion = emotion_fusion
        self.reporter = reporter
        
        self.running = True
        self.daemon = True  # Set as daemon thread
        
        # Status statistics
        self.fps = 0.0
        self.face_detected = False
        self.current_emotion = "None"
        self._last_status_ts = 0.0

    def run(self):
        print("[Vision] Thread started...")
        frame_count = 0
        start_time = time.time()
        
        # Web reporting rate limit
        last_web_frame_time = 0.0
        web_frame_interval = 1.0 / self.reporter.frame_fps if (self.reporter and self.reporter.frame_fps > 0) else 0.1
        
        while self.running:
            try:
                # 1. Get image frame
                frame = self.camera.capture_frame()
                if frame is None:
                    time.sleep(0.01)
                    continue
                frame_count += 1

                # 2. Face detection
                faces = self.face_detector.detect_faces(frame)
                
                # Frame copy for drawing
                display_frame = frame.copy()
                emotion_label = "No Face"
                
                if not faces:
                    self.face_detected = False
                    self.current_emotion = "None"
                    # Clean up stale smoothing state
                    self.fer_smoother.cleanup_stale_faces(max_age=1.0)
                else:
                    self.face_detected = True
                    
                    # 3. Process largest face (assume primary interaction target)
                    main_face = max(faces, key=lambda f: f[2] * f[3])
                    x, y, w, h = main_face

                    # IoU tracking: assign stable face_id to current box
                    face_id = self.fer_smoother.get_face_id_by_iou((x, y, w, h), iou_threshold=0.5)
                    # EMA smoothing of detection box to reduce jitter
                    x_s, y_s, w_s, h_s = self.fer_smoother.smooth_bbox((x, y, w, h), face_id)

                    # Crop face region (use smoothed box with boundary clipping)
                    margin = int(0.1 * min(max(w_s, 1), max(h_s, 1)))
                    x1 = max(0, x_s - margin)
                    y1 = max(0, y_s - margin)
                    x2 = min(frame.shape[1], x_s + w_s + margin)
                    y2 = min(frame.shape[0], y_s + h_s + margin)
                    face_roi = frame[y1:y2, x1:x2]

                    # 4. 表情识别
                    raw_result = self.fer_engine.recognize(face_roi)

                    # 5. Temporal smoothing
                    smoothed_result, is_confirmed = self.fer_smoother.smooth_with_confirm(
                        raw_result, face_id=face_id
                    )

                    if is_confirmed:
                        self.current_emotion = smoothed_result.expression_name
                        emotion_label = smoothed_result.expression_name

                        # 6. Build and send message to fusion module (use smoothed bbox)
                        msg = VisionFERMsg(
                            timestamp=now_ts(),
                            face_id=face_id,
                            bbox=(x_s, y_s, w_s, h_s),
                            emotion=smoothed_result.emotion_scores
                        )
                        self.emotion_fusion.update_fer(msg, expression_name=smoothed_result.expression_name)
                        if self.reporter is not None:
                            self.reporter.report_fer(msg)
                            self.reporter.report_fusion(
                                self.emotion_fusion.get_emotion_state(),
                                label=smoothed_result.expression_name.lower(),
                            )
                    else:
                        emotion_label = "Detecting..."
                    
                    # Draw face box and label on frame (use smoothed box)
                    cv2.rectangle(display_frame, (x_s, y_s), (x_s + w_s, y_s + h_s), (0, 255, 0), 2)
                    label_size = cv2.getTextSize(emotion_label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
                    cv2.rectangle(display_frame, (x_s, y_s - label_size[1] - 10),
                                  (x_s + label_size[0] + 10, y_s), (0, 255, 0), -1)
                    cv2.putText(display_frame, emotion_label, (x_s + 5, y_s - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

                # Push annotated video frame to WebRTC backend (rate limited)
                if self.reporter is not None:
                    current_time = time.time()
                    if current_time - last_web_frame_time >= web_frame_interval:
                        ok, jpeg = cv2.imencode(
                            ".jpg",
                            display_frame,
                            [int(cv2.IMWRITE_JPEG_QUALITY), self.reporter.jpeg_quality],
                        )
                        if ok:
                            self.reporter.submit_frame(
                                jpeg.tobytes(),
                                timestamp=now_ts(),
                                width=display_frame.shape[1],
                                height=display_frame.shape[0],
                            )
                        last_web_frame_time = current_time

                # FPS calculation: count each processed frame, update FPS with sliding window
                if frame_count % 30 == 0 and frame_count > 0:
                    elapsed = time.time() - start_time
                    self.fps = frame_count / elapsed if elapsed > 0 else 0
                    if frame_count > 1000:
                        frame_count = 0
                        start_time = time.time()

                # Limit frame rate to save CPU (~50 FPS cap, affected by capture+detection time)
                time.sleep(0.02)

                if self.reporter is not None:
                    if time.time() - self._last_status_ts > 1.0:
                        self.reporter.report_status(
                            {
                                "timestamp": now_ts(),
                                "vision_fps": round(self.fps, 2),
                                "face_detected": self.face_detected,
                                "vision_emotion": self.current_emotion,
                            }
                        )
                        self._last_status_ts = time.time()
                
            except Exception as e:
                print(f"[Vision] Error: {e}")
                time.sleep(0.1)

    def stop(self):
        self.running = False


def print_banner():
    """Print welcome banner."""
    print("=" * 60)
    print("🤖  Emotion Robot - Multimodal Interaction Mode")
    print("    Child Social Emotion Robot - Voice + Vision Fusion")
    print("=" * 60)
    print()


def check_models(cfg):
    """Check required model files (LLM provided via hailo-ollama API, no file check needed)."""
    required_models = [
        ("Whisper", Path(cfg["models"]["whisper"])),
        ("HuBERT", Path(cfg["models"]["hubert"])),
        ("FER", Path(cfg["models"]["fer"])),
    ]

    for name, path in required_models:
        if not path.exists():
            return False, f"{name} model not found: {path}"

    return True, ""


def cleanup_resources(
    vision_thread: VisionThread | None,
    camera: CameraService | None,
    audio_service: AudioService | None,
    tts_engine: TTSEngine | None,
    streaming_worker: StreamingVoiceInteraction | None,
    reporter: HttpReporter | None,
    llm_engine=None,
):
    """Clean up all resources. Each step uses try-except independently so one component
    failure does not block other cleanup. Uses BaseException to catch KeyboardInterrupt during cleanup.
    """
    if streaming_worker is not None:
        try:
            streaming_worker.stop()
        except BaseException as e:
            print(f"[Cleanup] Error stopping streaming worker: {e}")
    if vision_thread is not None:
        try:
            vision_thread.stop()
            vision_thread.join(timeout=1.0)
        except BaseException as e:
            print(f"[Cleanup] Error stopping vision thread: {e}")
    if camera is not None:
        try:
            camera.cleanup()
        except BaseException as e:
            print(f"[Cleanup] Error cleaning up camera: {e}")
    if audio_service is not None:
        try:
            audio_service.close()
        except BaseException as e:
            print(f"[Cleanup] Error closing audio service: {e}")
    if tts_engine is not None:
        try:
            tts_engine.shutdown()
        except BaseException as e:
            print(f"[Cleanup] Error shutting down TTS engine: {e}")
    if reporter is not None:
        try:
            reporter.stop()
        except BaseException as e:
            print(f"[Cleanup] Error stopping HTTP reporter: {e}")
    if llm_engine is not None:
        try:
            llm_engine.close()
        except BaseException as e:
            print(f"[Cleanup] Error closing LLM engine: {e}")


def main():
    """Main program entry point."""
    cfg = load_config(os.environ.get("EMOTION_ROBOT_CONFIG"))

    print_banner()
    
    # Check models
    print("[Step 1/6] Checking models...")
    passed, error = check_models(cfg)
    if not passed:
        print(f"❌ Error: {error}")
        print("\n💡 Please download the required models first.")
        sys.exit(1)
    print("✓ Model check passed\n")
    
    # ===== Initialize all components =====
    print("[Step 2/6] Initializing components...")
    print("-" * 60)
    
    vision_thread = None
    camera = None
    audio_service = None
    tts_engine = None
    streaming_worker = None
    reporter = None
    llm_engine = None

    try:
        # 1. Web reporter
        web_cfg = cfg.get("web", {})
        if web_cfg.get("enabled", False):
            reporter = HttpReporter(
                base_url=os.environ.get("WEB_MONITOR_URL", web_cfg.get("base_url", "http://127.0.0.1:8000")),
                timeout=float(web_cfg.get("timeout_s", 0.8)),
                frame_fps=int(web_cfg.get("frame_fps", cfg["vision"]["framerate"])),
                jpeg_quality=int(web_cfg.get("jpeg_quality", 80)),
            )

        # 2. LLM engine
        print("\n[1/7] Loading LLM...")
        model_name = os.environ.get("LLM_MODEL_PATH", cfg["models"]["llm"])
        llm_api_url = os.environ.get("LLM_API_URL", cfg["models"].get("llm_api_url", "http://localhost:8000"))
        llm_engine = LLMEngine(
            model_path=model_name,
            max_tokens=cfg["llm"]["max_tokens"],
            temperature=cfg["llm"]["temperature"],
            top_p=cfg["llm"]["top_p"],
            top_k=cfg["llm"].get("top_k", 20),
            repeat_penalty=cfg["llm"]["repeat_penalty"],
            prompt_config=cfg["llm"].get("prompt", {}),
            api_url=llm_api_url,
        )
        
        # 2. TTS engine
        print("\n[2/7] Loading TTS...")
        tts_engine = TTSEngine(voice_name=cfg["tts"]["voice_name"])
        
        # 3. Audio service
        print("\n[3/7] Initializing audio service...")
        audio_service = AudioService(
            device=cfg["audio"]["device"],
            rate=cfg["audio"]["rate"],
            channels=cfg["audio"]["channels"],
        )
        audio_service.set_vad_threshold(cfg["audio"]["vad_threshold"])
        audio_service.silence_duration = cfg["audio"]["silence_duration"]
        
        # 4. ASR engine
        print("\n[4/7] Loading ASR (Whisper)...")
        asr_engine = ASREngine(
            model_path=cfg["models"]["whisper"],
            compute_type=cfg["asr"]["compute_type"],
            language=cfg["asr"]["language"],
            beam_size=cfg["asr"]["beam_size"],
            vad_filter=cfg["asr"]["vad_filter"],
        )
        
        # 5. SER engine
        print("\n[5/7] Loading SER (HuBERT)...")
        ser_engine = SEREngine(
            model_path=cfg["models"]["hubert"],
            sample_rate=cfg["ser"]["sample_rate"],
        )
        
        # 6. Vision components (Camera, Face, FER)
        print("\n[6/7] Initializing Vision System...")
        camera = CameraService(
            width=cfg["vision"]["width"],
            height=cfg["vision"]["height"],
            framerate=cfg["vision"]["framerate"],
        )
        camera.start()  # Start camera read thread
        
        face_detector = FaceDetector(
            confidence_threshold=cfg["vision"]["face"]["confidence_threshold"],
            nms_threshold=cfg["vision"]["face"].get("nms_threshold", 0.4),
        )
        fer_engine = FEREngine(model_path=cfg["models"]["fer"])
        fer_smoother = FERSmoother(
            ema_alpha=cfg["vision"]["fer"]["ema_alpha"],
            confirm_frames=cfg["vision"]["fer"]["confirm_frames"],
            switch_threshold=cfg["vision"]["fer"].get("switch_threshold", 0.15),
            min_confidence=cfg["vision"]["fer"].get("min_confidence", 0.4),
        )
        print(f"  ✓ Vision system ready (Face: {face_detector.backend})")
        
        # 7. Emotion fusion and dialogue management
        print("\n[7/7] Initializing fusion & dialogue...")
        emotion_fusion = EmotionFusion(
            ser_weight=cfg["fusion"]["ser_weight"],
            fer_weight=cfg["fusion"]["fer_weight"],
            ser_max_age_s=cfg["fusion"]["ser_max_age_s"],
            fer_max_age_s=cfg["fusion"]["fer_max_age_s"],
        )
        project_root = Path(__file__).resolve().parent
        knowledge_root = project_root / "knowledge"
        embedding_model_path = cfg.get("models", {}).get("embedding", "")
        retriever = None
        if (knowledge_root / "meta.json").exists():
            retriever = KnowledgeRetriever(
                knowledge_root,
                embedding_model_path=embedding_model_path if embedding_model_path else None,
            )
            if retriever:
                mode = "embedding+keyword" if retriever._embedding_ready else "keyword-only"
                print(f"  ✓ Knowledge base loaded ({len(retriever.entries)} entries, {mode})")
        dlg = DialogueManager(llm_engine, tts_engine, emotion_fusion, reporter=reporter, retriever=retriever)
        
        # Config reload variables
        config_path = Path(os.environ.get("EMOTION_ROBOT_CONFIG", "config.yaml"))
        if not config_path.is_absolute():
            project_root = Path(__file__).resolve().parent
            config_path = project_root / config_path
        last_config_mtime = config_path.stat().st_mtime if config_path.exists() else 0
        
        def reload_llm_config_if_changed():
            """Check if config file was modified, reload LLM config if so."""
            nonlocal last_config_mtime
            try:
                if config_path.exists():
                    current_mtime = config_path.stat().st_mtime
                    if current_mtime > last_config_mtime:
                        print("\n[Config] Config file updated, reloading LLM config...")
                        # Reload config (only read llm section from config.yaml, no defaults)
                        with config_path.open("r", encoding="utf-8") as f:
                            user_cfg = yaml.safe_load(f) or {}
                        
                        llm_cfg = user_cfg.get("llm", {})
                        if llm_cfg:
                            # Update LLM engine config
                            llm_engine.update_config(
                                max_tokens=llm_cfg.get("max_tokens"),
                                temperature=llm_cfg.get("temperature"),
                                top_p=llm_cfg.get("top_p"),
                                top_k=llm_cfg.get("top_k"),
                                repeat_penalty=llm_cfg.get("repeat_penalty"),
                                prompt_config=llm_cfg.get("prompt"),
                            )
                            print("[Config] LLM config updated")
                        last_config_mtime = current_mtime
            except Exception as e:
                print(f"[Config] Error reloading config: {e}")

        if cfg["streaming"]["enabled"]:
            streaming_worker = StreamingVoiceInteraction(
                audio_service=audio_service,
                asr_engine=asr_engine,
                ser_engine=ser_engine,
                emotion_fusion=emotion_fusion,
                dialog_manager=dlg,
                tts_engine=tts_engine,
                reporter=reporter,
                vad_threshold=cfg["audio"]["vad_threshold"],
                pre_speech_ms=cfg["streaming"]["pre_speech_ms"],
                start_speech_ms=cfg["streaming"]["start_speech_ms"],
                end_silence_ms=cfg["streaming"]["end_silence_ms"],
                min_speech_ms=cfg["streaming"]["min_speech_ms"],
                max_utterance_s=cfg["streaming"]["max_utterance_s"],
            )
            streaming_worker.start()
        
        # Start vision processing thread
        vision_thread = VisionThread(
            camera, face_detector, fer_engine, fer_smoother, emotion_fusion, reporter=reporter
        )
        vision_thread.start()
        
        print("\n" + "-" * 60)
        print("✓ All components initialized successfully!")
        
    except Exception as e:
        print(f"\n❌ Initialization failed: {e}")
        cleanup_resources(
            vision_thread, camera, audio_service, tts_engine, streaming_worker, reporter,
            llm_engine=llm_engine,
        )
        sys.exit(1)
    
    # ===== Interaction loop =====
    print("\n" + "=" * 60)
    print("🎤  Ready for Multimodal Interaction!")
    print("=" * 60)
    print()
    
    try:
        if not sys.stdin.isatty():
            print("🔧 Non-interactive mode detected. Running without text input.")
            while True:
                reload_llm_config_if_changed()
                time.sleep(1.0)
        else:
            while True:
                # Check config updates
                reload_llm_config_if_changed()
                
                # Display current vision status
                vision_status = f"Vision: {vision_thread.current_emotion}" if vision_thread.face_detected else "Vision: No Face"
                prompt_text = f"[{vision_status}] 🎙️  Type to chat (streaming voice is ON): "

                try:
                    user_input = input(prompt_text).strip()
                except EOFError:
                    print("\n👋 Input closed, exiting.")
                    break

                if user_input.lower() in ("exit", "quit"):
                    print("\n👋 Goodbye!")
                    break

                # Text mode
                if user_input:
                    print(f"You (text): {user_input}")
                    reply = dlg.process_user_text(user_input)
                    print(f"🤖 Robot: {reply}\n")
                else:
                    print("⚠️  Empty input ignored. Streaming voice is active.\n")

    except KeyboardInterrupt:
        print("\n\n👋 Interrupted.")
    finally:
        print("Cleaning up...")
        cleanup_resources(
            vision_thread, camera, audio_service, tts_engine, streaming_worker, reporter,
            llm_engine=llm_engine,
        )
        print("Done.")

if __name__ == "__main__":
    main()
