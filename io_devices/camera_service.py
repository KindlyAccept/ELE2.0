import time
import cv2
from picamera2 import Picamera2


class CameraService:
    def __init__(self, width=1280, height=720, framerate=30):
        """
        初始化摄像头服务 (基于 Picamera2 - 适用于 Raspberry Pi 5)
        
        Args:
            width: 图像宽度
            height: 图像高度
            framerate: 帧率
        """
        self.width = width
        self.height = height
        self.framerate = framerate
        self.picam2 = Picamera2()
        self.running = False
        
        self._configure_camera()

    def _configure_camera(self):
        """配置摄像头参数"""
        config = self.picam2.create_video_configuration(
            main={"size": (self.width, self.height)}
        )
        self.picam2.configure(config)
        print(f"Camera configured: {self.width}x{self.height}")

    def start(self):
        """启动摄像头预览/捕获"""
        if not self.running:
            try:
                self.picam2.start()
                self.running = True
                # 等待自动曝光和自动白平衡稳定
                time.sleep(2) 
                print("Camera started and warmed up.")
            except Exception as e:
                print(f"Failed to start camera: {e}")
                self.running = False
                raise

    def stop(self):
        """停止摄像头"""
        if self.running:
            self.picam2.stop()
            self.running = False
            print("Camera stopped.")

    def capture_frame(self):
        """
        捕获一帧图像
        
        Returns:
            frame: numpy.ndarray (height, width, 3) BGR 图像 (适配 OpenCV)
                   如果失败返回 None
        """
        if not self.running:
            self.start()
        
        try:
            # 捕获原始数据 (默认通常是 RGB)
            frame = self.picam2.capture_array()
            
            if frame is not None:
                # Picamera2 默认输出 RGB，而 OpenCV 需要 BGR
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                
            return frame
        except Exception as e:
            print(f"Error capturing frame: {e}")
            return None
    
    def cleanup(self):
        """清理资源"""
        self.stop()
