import { ref, onBeforeUnmount, type Ref } from 'vue';
import { formatRecordingTime } from '../utils/timeFormatters';
import { saveRecordingToIndexedDB } from './useIndexedDB';
import type { Recording } from '../types';

const MAX_RECORDING_DURATION = 3 * 60 * 60; // 3小时（秒）

export const useRecording = (sessionId: Ref<string>) => {
  const isRecording = ref(false);
  const recordingData = ref<any[]>([]);
  const recordingStartTime = ref<number>(0);
  const recordingElapsedTime = ref<number>(0);
  let recordingTimer: number | null = null;

  /**
   * 格式化录制时间
   */
  const formatTime = formatRecordingTime;

  /**
   * 自动停止录制（达到上限时）
   */
  const stopRecordingAutomatically = async () => {
    // 清除计时器
    if (recordingTimer !== null) {
      clearInterval(recordingTimer);
      recordingTimer = null;
    }
    
    const recordingId = `recording_${Date.now()}`;
    const recording: Recording = {
      id: recordingId,
      data: [...recordingData.value],
      startTime: recordingStartTime.value,
      endTime: Date.now(),
      sessionId: sessionId.value,
    };
    
    // 设置状态为 false
    isRecording.value = false;
    recordingElapsedTime.value = 0;
    
    // 保存到 IndexedDB
    try {
      await saveRecordingToIndexedDB(recording);
      recordingData.value = [];
      alert(`Recording automatically stopped (3 hour limit reached)\nRecording saved: ${recordingId}\nData points: ${recording.data.length}`);
    } catch (error) {
      console.error('Failed to save recording:', error);
      alert(`Recording automatically stopped (3 hour limit reached)\nFailed to save recording: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  /**
   * 切换录制状态
   */
  const toggleRecording = async () => {
    if (isRecording.value) {
      // 停止录制
      // 清除计时器
      if (recordingTimer !== null) {
        clearInterval(recordingTimer);
        recordingTimer = null;
      }
      
      const recordingId = `recording_${Date.now()}`;
      const recording: Recording = {
        id: recordingId,
        data: [...recordingData.value],
        startTime: recordingStartTime.value,
        endTime: Date.now(),
        sessionId: sessionId.value,
      };
      
      // 现在可以安全地设置状态为 false
      isRecording.value = false;
      recordingElapsedTime.value = 0;
      
      // 保存到 IndexedDB
      try {
        await saveRecordingToIndexedDB(recording);
        recordingData.value = [];
        alert(`Recording saved: ${recordingId}\nData points: ${recording.data.length}`);
      } catch (error) {
        console.error('Failed to save recording:', error);
        alert(`Failed to save recording: ${error instanceof Error ? error.message : 'Unknown error'}\nPlease try again.`);
        // 恢复录制状态，让用户可以重试
        isRecording.value = true;
        // 重新启动计时器
        recordingStartTime.value = Date.now();
        recordingElapsedTime.value = 0;
        recordingTimer = setInterval(() => {
          recordingElapsedTime.value = Math.floor((Date.now() - recordingStartTime.value) / 1000);
        }, 1000);
      }
    } else {
      // 开始录制
      recordingStartTime.value = Date.now();
      recordingData.value = [];
      recordingElapsedTime.value = 0;
      isRecording.value = true;
      
      // 启动计时器
      recordingTimer = setInterval(() => {
        const elapsed = Math.floor((Date.now() - recordingStartTime.value) / 1000);
        recordingElapsedTime.value = elapsed;
        
        // 检查是否超过3小时
        if (elapsed >= MAX_RECORDING_DURATION) {
          // 自动停止录制
          stopRecordingAutomatically();
        }
      }, 1000);
      
      console.log('Recording started');
    }
  };

  /**
   * 添加录制数据
   */
  const addRecordingData = (data: any) => {
    if (isRecording.value) {
      recordingData.value.push(data);
    }
  };

  /**
   * 清理资源
   */
  const cleanup = () => {
    if (recordingTimer !== null) {
      clearInterval(recordingTimer);
      recordingTimer = null;
    }
  };

  onBeforeUnmount(() => {
    cleanup();
  });

  return {
    isRecording,
    recordingData,
    recordingElapsedTime,
    formatTime,
    toggleRecording,
    addRecordingData,
    cleanup,
  };
};
