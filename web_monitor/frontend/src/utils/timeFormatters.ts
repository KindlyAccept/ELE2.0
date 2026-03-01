/**
 * 格式化录制时间
 * @param seconds 总秒数
 * @returns 格式化后的时间字符串
 * - 0-59秒: 00:SS
 * - 1分钟-59分59秒: MM:SS
 * - 1小时及以上: HH:MM:SS
 */
export const formatRecordingTime = (seconds: number): string => {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  
  if (hours > 0) {
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  } else {
    // MM在00的时候也显示
    return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }
};

/**
 * 格式化时间戳为时间字符串
 */
export const formatTime = (timestamp: number): string => {
  return new Date(timestamp * 1000).toLocaleTimeString();
};
