#!/usr/bin/env python3
"""
HTTPS server startup script.
Starts FastAPI app with SSL certificate.
"""
import os
import sys
from pathlib import Path

# Add project path
sys.path.insert(0, str(Path(__file__).parent))

from app.https_config import get_uvicorn_ssl_config
import uvicorn

if __name__ == "__main__":
    # 获取SSL配置
    ssl_config = get_uvicorn_ssl_config()
    
    # If SSL configured, use HTTPS
    if ssl_config:
        print("Starting HTTPS server...")
        print(f"SSL cert: {ssl_config.get('ssl_certfile', 'not set')}")
        print(f"SSL key: {ssl_config.get('ssl_keyfile', 'not set')}")
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=8443,
            ssl_keyfile=ssl_config.get("ssl_keyfile"),
            ssl_certfile=ssl_config.get("ssl_certfile"),
            reload=False,
        )
    else:
        print("SSL not configured, using HTTP")
        print("To enable HTTPS, set one of:")
        print("  - SSL_CERT_FILE and SSL_KEY_FILE")
        print("  - SSL_CERT_DIR (directory containing cert.pem and key.pem)")
        print("\nStarting HTTP server...")
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=8000,
            reload=False,
        )
