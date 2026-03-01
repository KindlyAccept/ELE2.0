import { ref, type Ref } from 'vue';
import type { DialogueItem } from '../types';

export const useSSE = (
  apiBase: Ref<string>,
  autoRecordingData: Ref<any[]>,
  recordingData: Ref<any[]>,
  isRecording: Ref<boolean>,
  dialogue: Ref<DialogueItem[]>,
  status: Ref<Record<string, any>>,
  latestVisionLabel: Ref<string>,
  latestAudioLabel: Ref<string>,
  latestFusionLabel: Ref<string>,
  isVideoActive: Ref<boolean>,
  pushSeries: (key: string, value: number, ts: number) => void,
  updateEmotionChart: () => void
) => {
  let eventSource: EventSource | null = null;

  /**
   * 连接 SSE
   */
  const connectSSE = () => {
    // Close any existing connection before opening a new one
    eventSource?.close();
    eventSource = null;

    // EventSource不支持自定义headers，使用URL参数传递token
    const token = localStorage.getItem('auth_token');
    const url = token
      ? `${apiBase.value}/api/stream?token=${encodeURIComponent(token)}`
      : `${apiBase.value}/api/stream`;
    eventSource = new EventSource(url);
    eventSource.onmessage = (event) => {
      if (!event.data) return;
      const payload = JSON.parse(event.data);
      
      if (payload.type === "emotion_ser") {
        latestAudioLabel.value = payload.label ?? "unknown";
      }
      if (payload.type === "emotion_fer") {
        latestVisionLabel.value = payload.label ?? "unknown";
      }
      if (payload.type === "emotion_fusion") {
        latestFusionLabel.value = payload.label ?? "unknown";
        const ts = payload.timestamp ?? Date.now() / 1000;
        pushSeries("valence", payload.valence ?? 0, ts);
        pushSeries("arousal", payload.arousal ?? 0, ts);
        pushSeries("dominance", payload.dominance ?? 0, ts);
        updateEmotionChart();
        
        // 自动录制暂存（所有数据自动收集）
        autoRecordingData.value.push({
          type: 'emotion_fusion',
          timestamp: ts,
          ...payload,
        });
        
        // 手动录制时收集数据
        if (isRecording.value) {
          recordingData.value.push({
            type: 'emotion_fusion',
            timestamp: ts,
            ...payload,
          });
        }
      }
      if (payload.type === "dialogue_event") {
        dialogue.value.push({
          role: payload.role,
          content: payload.content,
          timestamp: payload.timestamp,
        });
        
        // 自动录制暂存（所有数据自动收集）
        autoRecordingData.value.push({
          type: 'dialogue_event',
          timestamp: payload.timestamp,
          ...payload,
        });
        
        // 手动录制时收集数据
        if (isRecording.value) {
          recordingData.value.push({
            type: 'dialogue_event',
            timestamp: payload.timestamp,
            ...payload,
          });
        }
      }
      if (payload.type === "dialogue_cleared") {
        dialogue.value = [];
      }
      if (payload.type === "status_event") {
        status.value = payload;
        isVideoActive.value = (payload.vision_fps ?? 0) > 0;
      }
    };
    
    eventSource.onerror = () => {
      console.error('SSE connection error');
    };
  };

  /**
   * 关闭 SSE 连接
   */
  const closeSSE = () => {
    eventSource?.close();
    eventSource = null;
  };

  return {
    connectSSE,
    closeSSE,
  };
};
