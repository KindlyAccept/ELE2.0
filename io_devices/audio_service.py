# io_devices/audio_service.py
"""
Audio service module - ALSA-based audio capture and playback.
Uses pyalsaaudio for direct ALSA hardware access, providing low-latency audio I/O.
"""
from __future__ import annotations

import alsaaudio
import numpy as np
import threading
import queue
from typing import Optional, Callable


class AudioService:
    """
    ALSA audio service class.
    
    Features:
    1. Record audio (single recording, streaming)
    2. Play audio (WAV files)
    3. VAD voice activity detection (simple energy threshold)
    
    Characteristics:
    - Direct ALSA access, low latency
    - Streaming capture (background thread)
    - Simple VAD implementation
    """
    
    def __init__(
        self,
        device: str = "default",
        rate: int = 16000,           # 16kHz sample rate, Whisper standard
        channels: int = 1,            # Mono, saves computation
        format: int = alsaaudio.PCM_FORMAT_S16_LE,  # 16-bit signed integer, little-endian
        period_size: int = 1024,      # Frames per read
    ):
        """
        Initialize ALSA audio service.
        
        Parameters:
            device: ALSA device name
                - "default": system default
                - "plughw:0,0": first device of first sound card
                - "hw:1,0": second sound card (e.g. USB mic)
            rate: Sample rate (Hz)
                - 16000: Whisper recommended, balance quality and performance
                - 44100: CD quality (unnecessary, increases compute)
            channels: Channel count
                - 1: Mono (recommended for speech)
                - 2: Stereo (wastes resources)
            format: Audio format
                - PCM_FORMAT_S16_LE: 16-bit integer (standard)
            period_size: Buffer size (frames)
                - 1024: ~64ms latency @ 16kHz
                - Smaller = lower latency but higher CPU usage
        """
        self.device = device
        self.rate = rate
        self.channels = channels
        self.format = format
        self.period_size = period_size
        
        # Recording state management
        self.recording = False
        self.audio_queue = queue.Queue()
        self.record_thread: Optional[threading.Thread] = None
        
        # VAD parameters (voice activity detection)
        self.vad_threshold = 500  # Energy threshold, tune for environment
        self.silence_duration = 1.0  # Silence duration to stop recording (seconds)
        
        print(f"[AudioService] Initialized:")
        print(f"  - Sample rate: {rate} Hz")
        print(f"  - Channels: {channels}")
        print(f"  - Device: {device}")
        print(f"  - Buffer: {period_size} frames (~{period_size/rate*1000:.1f}ms)")
    
    def record_once(self, duration: float, use_vad: bool = False) -> bytes:
        """
        Record audio for specified duration (blocking).
        
        Parameters:
            duration: Recording duration (seconds)
            use_vad: Use VAD to auto-stop
                - False: Fixed duration recording
                - True: Stop on silence (max duration seconds)
        
        Returns:
            bytes: Raw PCM audio (16-bit signed integer, little-endian)
        
        Use case:
            Suitable for button-triggered recording, e.g.:
            "Hold to talk, release to stop" or "Record 5 seconds"
        """
        # Create ALSA capture object
        inp = alsaaudio.PCM(
            alsaaudio.PCM_CAPTURE,    # Capture mode
            alsaaudio.PCM_NORMAL,      # Blocking mode
            device=self.device
        )
        
        # Configure audio parameters
        inp.setchannels(self.channels)
        inp.setrate(self.rate)
        inp.setformat(self.format)
        inp.setperiodsize(self.period_size)
        
        # Calculate total frames to record
        num_frames = int(self.rate * duration)
        frames_read = 0
        audio_chunks = []
        
        # If VAD enabled, initialize silence counter
        if use_vad:
            silent_frames = 0
            max_silent_frames = int(self.silence_duration * self.rate / self.period_size)
            speech_started = False
        
        print(f"[AudioService] Recording {duration}s" + (" (VAD enabled)" if use_vad else ""))
        
        # Recording loop
        while frames_read < num_frames:
            length, data = inp.read()
            
            if length > 0:
                audio_chunks.append(data)
                frames_read += length
                
                # VAD detection
                if use_vad:
                    # Compute audio energy (simple RMS)
                    audio_array = np.frombuffer(data, dtype=np.int16)
                    energy = np.sqrt(np.mean(audio_array.astype(float) ** 2))
                    
                    # Detect if speech present
                    if energy > self.vad_threshold:
                        speech_started = True
                        silent_frames = 0
                    elif speech_started:
                        silent_frames += 1
                        
                        # If silence exceeds threshold, stop recording
                        if silent_frames >= max_silent_frames:
                            print(f"[AudioService] Silence detected, stopping early")
                            break
        
        print(f"[AudioService] 录音完成，共 {frames_read/self.rate:.2f} 秒")
        
        return b''.join(audio_chunks)
    
    def start_streaming(self, callback: Callable[[bytes], None]):
        """
        Start streaming recording (background thread, non-blocking).
        
        Parameters:
            callback: Callback receiving audio data, signature: callback(audio_chunk: bytes) -> None
        
        Use case:
            Suitable for real-time audio processing, e.g.:
            - Real-time speech recognition
            - Real-time emotion analysis
            - Voiceprint recognition
        
        Note:
            - This method returns immediately, recording runs in background thread
            - Call stop_streaming() to stop
        """
        if self.recording:
            print("[AudioService] Warning: already recording")
            return
        
        self.recording = True
        self.record_thread = threading.Thread(
            target=self._recording_loop,
            args=(callback,),
            daemon=True  # Daemon thread, auto-terminate when main exits
        )
        self.record_thread.start()
        print("[AudioService] Streaming recording started")
    
    def stop_streaming(self):
        """
        Stop streaming recording.
        - Set stop flag
        - Wait for background thread (max 2s)
        - Clean up resources
        """
        if self.recording:
            self.recording = False
            if self.record_thread:
                self.record_thread.join(timeout=2.0)
            print("[AudioService] Streaming recording stopped")

    def close(self):
        """Stop any background recording and release resources."""
        self.stop_streaming()
    
    def _recording_loop(self, callback: Callable[[bytes], None]):
        """
        Background recording loop (internal, do not call directly).
        Runs in separate thread, continuously reads audio and invokes callback.
        Explicitly releases ALSA PCM device in finally for next streaming session.
        """
        inp = None
        try:
            inp = alsaaudio.PCM(
                alsaaudio.PCM_CAPTURE,
                alsaaudio.PCM_NORMAL,
                device=self.device,
            )
            inp.setchannels(self.channels)
            inp.setrate(self.rate)
            inp.setformat(self.format)
            inp.setperiodsize(self.period_size)

            while self.recording:
                try:
                    length, data = inp.read()
                    if length > 0:
                        callback(data)
                except Exception as e:
                    print(f"[AudioService] 录音错误: {e}")
                    break
        finally:
            if inp is not None:
                try:
                    del inp
                except Exception:
                    pass
    
    def play_wav(self, filename: str):
        """
        Play WAV file (uses system aplay command).
        
        Parameters:
            filename: WAV file path
        
        Note:
            Simple implementation using Raspberry Pi's built-in aplay.
            Pros: Simple, reliable, no extra dependencies.
            Cons: Blocking playback, no volume/pause control.
        
        Alternatives:
            For more control: pygame.mixer (used in TTS), pyalsaaudio playback.
        """
        import subprocess
        try:
            subprocess.run(["aplay", "-q", filename], check=True)
        except FileNotFoundError:
            print("[AudioService] Error: aplay command not found")
        except subprocess.CalledProcessError as e:
            print(f"[AudioService] Playback failed: {e}")
    
    def set_vad_threshold(self, threshold: int):
        """
        Set VAD energy threshold.
        
        Parameters:
            threshold: Energy threshold (typical: 100-1000)
                - Too low: noise gets detected as speech
                - Too high: soft speech may not be detected
        
        Tip: Record in environment and check energy values, then set appropriate threshold.
        """
        self.vad_threshold = threshold
        print(f"[AudioService] VAD threshold set to: {threshold}")
