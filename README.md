# Emotion Robot

A child social robot system based on multimodal emotion recognition, supporting voice interaction, emotion perception, and intelligent dialogue.

## Features

- **Voice Interaction**: Whisper ASR + Piper TTS, with VAD-based proactive interruption
- **Emotion Recognition**: Speech emotion (HuBERT) + facial expression (EfficientNet ONNX)
- **Intelligent Dialogue**: LLM-driven with RAG knowledge base retrieval
- **Web Monitor**: Real-time video stream, emotion curves, dialogue history

## Quick Start

### 1. Install Dependencies

```bash
./install.sh
# Or: pip install -r requirements.txt
```

### 2. Configuration

```bash
cp config.example.yaml config.yaml
# Edit model paths in config.yaml
```

### 3. Download Models

Place the following models in `Data/Models/`:

| Module | Model | Source |
|--------|-------|--------|
| ASR | faster-whisper-base | HuggingFace `guillaumekln/faster-whisper-base` |
| SER | HuBERT Emotion | HuggingFace `superb/hubert-base-superb-er` |
| LLM | Qwen / hailo-ollama | Requires hailo-ollama service (port 11434) |
| FER | EfficientNet ONNX | `enet_b0_8_va_mtl.onnx` → `Data/Models/enet/` |
| TTS | Piper EN_GB | `Data/Models/piper_semaine/` |

### 4. Run

```bash
# Robot only
python main.py

# Full stack (robot + Web monitor)
./run_all.sh
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- Web default account: admin / admin (set `JWT_SECRET_KEY` and `ADMIN_PASSWORD` for production)

## Project Structure

```
emotion_robot/
├── main.py              # Main program
├── config.example.yaml  # Configuration example
├── io_devices/          # Audio, camera
├── perception/          # ASR, SER, FER, face detection
├── fusion/              # Emotion fusion
├── cognitive/           # LLM, dialogue management, RAG
├── action/              # TTS
├── knowledge/           # RAG knowledge base
└── web_monitor/         # Web monitor (FastAPI + Vue)
```

## Hardware Requirements

- **Recommended**: Raspberry Pi 5 + Hailo AI Kit (NPU)
- **Compatible**: Raspberry Pi 4B (voice mode only)

## Environment Variables

| Variable | Description |
|----------|-------------|
| `EMOTION_ROBOT_CONFIG` | Config file path |
| `LLM_MODEL_PATH` | LLM model path |
| `LLM_API_URL` | hailo-ollama API URL |
| `JWT_SECRET_KEY` | Web auth secret key (required for production) |
| `ADMIN_PASSWORD` | Web default admin password |

## License

For learning and research use only.
