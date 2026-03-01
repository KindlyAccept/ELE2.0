import { ref, type Ref } from 'vue';
import { apiFetch } from '../utils/api';

export const useWebRTC = (
  videoRef: Ref<HTMLVideoElement | null>,
  isVideoActive: Ref<boolean>
) => {
  let peerConnection: RTCPeerConnection | null = null;
  let currentStream: MediaStream | null = null;

  /**
   * 启动 WebRTC 连接
   */
  const startWebRTC = async (apiBase: string) => {
    if (!videoRef.value) {
      console.warn('Video element not available');
      return;
    }
    
    // 关闭现有连接
    if (peerConnection) {
      peerConnection.close();
      peerConnection = null;
    }
    
    // 清理旧的视频流
    if (videoRef.value.srcObject) {
      const stream = videoRef.value.srcObject as MediaStream;
      stream.getTracks().forEach(track => track.stop());
      videoRef.value.srcObject = null;
    }
    
    // 重置状态
    isVideoActive.value = false;
    
    try {
      const pc = new RTCPeerConnection();
      peerConnection = pc;
      
      // 设置 ontrack 事件处理
      pc.ontrack = (event) => {
        console.log('WebRTC track received', event);
        // 确保视频元素存在
        if (!videoRef.value) {
          console.warn('Video element not available when track received');
          return;
        }
        
        const stream = event.streams[0];
        currentStream = stream;
        
        // 设置视频流
        videoRef.value.srcObject = stream;
        
        // 确保视频播放
        videoRef.value.play().catch(err => {
          console.error('Error playing video:', err);
        });
        
        isVideoActive.value = true;
      };
      
      // 添加 transceiver
      pc.addTransceiver("video", { direction: "recvonly" });
      
      // 创建 offer
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      
      // 等待 ICE 收集完成
      await waitForIce(pc);
      
      // 发送 offer 到服务器
      const res = await apiFetch(`${apiBase}/api/webrtc/offer`, {
        method: "POST",
        body: JSON.stringify(pc.localDescription),
      });
      
      if (!res.ok) {
        throw new Error(`Failed to send offer: ${res.statusText}`);
      }
      
      const answer = await res.json();
      await pc.setRemoteDescription(answer);
      
      console.log('WebRTC connection established');
    } catch (error) {
      console.error('WebRTC error:', error);
      isVideoActive.value = false;
      
      // 清理失败的连接
      if (peerConnection) {
        peerConnection.close();
        peerConnection = null;
      }
    }
  };

  /**
   * 等待 ICE 收集完成
   */
  const waitForIce = (pc: RTCPeerConnection) => {
    if (pc.iceGatheringState === "complete") return Promise.resolve();
    return new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => {
        pc.removeEventListener("icegatheringstatechange", handler);
        reject(new Error('ICE gathering timeout'));
      }, 5000);
      
      const handler = () => {
        if (pc.iceGatheringState === "complete") {
          clearTimeout(timeout);
          pc.removeEventListener("icegatheringstatechange", handler);
          resolve();
        }
      };
      pc.addEventListener("icegatheringstatechange", handler);
    });
  };

  /**
   * 关闭 WebRTC 连接
   */
  const closeWebRTC = () => {
    // 清理视频元素的 srcObject
    if (videoRef.value && videoRef.value.srcObject) {
      const stream = videoRef.value.srcObject as MediaStream;
      stream.getTracks().forEach(track => {
        track.stop();
        console.log('Stopped track:', track.kind);
      });
      videoRef.value.srcObject = null;
    }
    
    // 清理当前流
    if (currentStream) {
      currentStream.getTracks().forEach(track => track.stop());
      currentStream = null;
    }
    
    // 关闭 peer connection
    if (peerConnection) {
      peerConnection.close();
      peerConnection = null;
    }
    
    // 重置状态
    isVideoActive.value = false;
    
    console.log('WebRTC connection closed');
  };

  return {
    startWebRTC,
    closeWebRTC,
  };
};
