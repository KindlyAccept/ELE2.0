"""
HTTPS config module.
Supports SSL certificate config and HTTPS server startup.
"""
import os
import ssl
from pathlib import Path
from typing import Optional, Tuple


def get_ssl_context(
    cert_file: Optional[str] = None,
    key_file: Optional[str] = None,
    cert_dir: Optional[str] = None,
) -> Optional[ssl.SSLContext]:
    """
    Get SSL context.
    
    Args:
        cert_file: SSL certificate file path
        key_file: SSL key file path
        cert_dir: Cert directory (if provided, looks for cert.pem and key.pem)
    
    Returns:
        SSL context object, None if not configured
    """
    # Prefer environment variables
    cert_file = cert_file or os.getenv("SSL_CERT_FILE")
    key_file = key_file or os.getenv("SSL_KEY_FILE")
    cert_dir = cert_dir or os.getenv("SSL_CERT_DIR")
    
    # If cert dir provided, look for standard filenames
    if cert_dir and not (cert_file and key_file):
        cert_dir_path = Path(cert_dir)
        cert_file = cert_file or str(cert_dir_path / "cert.pem")
        key_file = key_file or str(cert_dir_path / "key.pem")
    
    # If none configured, return None (use HTTP)
    if not (cert_file and key_file):
        return None
    
    cert_path = Path(cert_file)
    key_path = Path(key_file)
    
    # 检查文件是否存在
    if not cert_path.exists():
        raise FileNotFoundError(f"SSL certificate file not found: {cert_file}")
    if not key_path.exists():
        raise FileNotFoundError(f"SSL key file not found: {key_file}")
    
    # Create SSL context
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)
    
    return context


def get_uvicorn_ssl_config() -> dict:
    """
    Get uvicorn SSL config.
    
    Returns:
        Dict with ssl_keyfile and ssl_certfile
    """
    cert_file = os.getenv("SSL_CERT_FILE")
    key_file = os.getenv("SSL_KEY_FILE")
    cert_dir = os.getenv("SSL_CERT_DIR")
    
    if cert_dir:
        cert_dir_path = Path(cert_dir)
        cert_file = cert_file or str(cert_dir_path / "cert.pem")
        key_file = key_file or str(cert_dir_path / "key.pem")
    
    config = {}
    if cert_file and Path(cert_file).exists():
        config["ssl_certfile"] = cert_file
    if key_file and Path(key_file).exists():
        config["ssl_keyfile"] = key_file
    
    return config
