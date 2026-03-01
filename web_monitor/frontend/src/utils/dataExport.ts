/**
 * 导出数据为 JSON
 */
export const exportDataAsJSON = (data: any, filename: string = `emotion_data_${Date.now()}.json`) => {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
};

/**
 * 准备导出数据
 */
export const prepareExportData = (
  sessionId: string,
  dialogue: any[],
  emotionFusionData: any[],
  status: any,
  latestVisionLabel: string,
  latestAudioLabel: string,
  latestFusionLabel: string
) => {
  const dialogueData = dialogue.map(item => ({
    role: item.role,
    content: item.content,
    timestamp: item.timestamp,
    timestampISO: new Date(item.timestamp * 1000).toISOString(),
  }));
  
  const valenceData: any[] = [];
  const arousalData: any[] = [];
  const dominanceData: any[] = [];
  
  emotionFusionData.forEach(item => {
    const ts = item.timestamp;
    if (item.valence !== undefined) {
      valenceData.push({
        value: item.valence,
        timestamp: ts,
        timestampISO: new Date(ts * 1000).toISOString(),
      });
    }
    if (item.arousal !== undefined) {
      arousalData.push({
        value: item.arousal,
        timestamp: ts,
        timestampISO: new Date(ts * 1000).toISOString(),
      });
    }
    if (item.dominance !== undefined) {
      dominanceData.push({
        value: item.dominance,
        timestamp: ts,
        timestampISO: new Date(ts * 1000).toISOString(),
      });
    }
  });
  
  return {
    sessionId,
    exportTimestamp: new Date().toISOString(),
    dialogue: dialogueData,
    emotionData: {
      valence: valenceData,
      arousal: arousalData,
      dominance: dominanceData,
    },
    status: {
      ...status,
      latestVisionLabel,
      latestAudioLabel,
      latestFusionLabel,
    },
  };
};
