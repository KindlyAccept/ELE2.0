import { ref, type Ref } from 'vue';
import * as echarts from 'echarts';
import type { EmotionType } from '../types';

const MAX_POINTS = 300;

export const useCharts = (
  emotionTypes: EmotionType[],
  autoRecordingData: Ref<any[]>
) => {
  // 图表引用
  const emotionChartRef = ref<HTMLDivElement | null>(null);
  const controlPanelDistributionRef = ref<HTMLDivElement | null>(null);
  const reviewEmotionChartRef = ref<HTMLDivElement | null>(null);
  const emotionDistributionRef = ref<HTMLDivElement | null>(null);
  
  // 图表实例
  let emotionChart: echarts.ECharts | null = null;
  let controlPanelDistributionChart: echarts.ECharts | null = null;
  let reviewEmotionChart: echarts.ECharts | null = null;
  let distributionChart: echarts.ECharts | null = null;
  
  // 图表数据
  const timeAxis: number[] = [];
  const seriesData: Record<string, number[]> = {
    valence: [],
    arousal: [],
    dominance: [],
    joy: [],
    sadness: [],
    disgust: [],
    contempt: [],
    anger: [],
    fear: [],
    surprise: [],
    engagement: [],
  };

  /**
   * 推送数据到系列
   */
  const pushSeries = (key: string, value: number, ts: number) => {
    if (!seriesData[key]) return;
    // Only advance timeAxis once per unique timestamp (multiple series share the same ts)
    if (timeAxis.length === 0 || timeAxis[timeAxis.length - 1] !== ts) {
      timeAxis.push(ts);
      if (timeAxis.length > MAX_POINTS) {
        timeAxis.shift();
      }
    }
    seriesData[key].push(value);
    if (seriesData[key].length > MAX_POINTS) {
      seriesData[key].shift();
    }
  };

  /**
   * 初始化情绪时序图
   */
  const initEmotionChart = () => {
    if (!emotionChartRef.value) return;
    emotionChart = echarts.init(emotionChartRef.value);
    emotionChart.setOption({
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
      },
      legend: {
        data: ['Valence', 'Arousal', 'Dominance'],
        bottom: 0,
        textStyle: { fontSize: 11 },
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '15%',
        top: '10%',
        containLabel: true,
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: [],
      },
      yAxis: {
        type: "value",
        min: -1,
        max: 1,
        name: 'Intensity',
      },
      series: [
        { name: "Valence", type: "line", smooth: true, data: [], symbol: 'none' },
        { name: "Arousal", type: "line", smooth: true, data: [], symbol: 'none' },
        { name: "Dominance", type: "line", smooth: true, data: [], symbol: 'none' },
      ],
    });
  };

  /**
   * 更新情绪时序图
   */
  const updateEmotionChart = () => {
    if (!emotionChart) return;
    const colors: Record<string, string> = {
      valence: '#2E86AB',
      arousal: '#F77F00',
      dominance: '#06A77D',
      joy: '#FF6B9D',
      sadness: '#4ECDC4',
      disgust: '#FFA07A',
      contempt: '#9B59B6',
      anger: '#06A77D',
      fear: '#E63946',
      surprise: '#FFD93D',
      engagement: '#F77F00',
    };
    
    // 优先显示情绪数据，如果没有则显示V/A/D
    const hasEmotionData = seriesData.joy.length > 0 || seriesData.sadness.length > 0;
    const series = hasEmotionData 
      ? Object.keys(seriesData).filter(k => ['joy', 'sadness', 'disgust', 'contempt', 'anger', 'fear', 'surprise', 'engagement'].includes(k))
          .map(key => ({
            name: key,
            type: "line",
            smooth: true,
            data: seriesData[key],
            itemStyle: { color: colors[key] },
            lineStyle: { width: 2 },
            symbol: 'none',
          }))
      : [
          { name: "Valence", type: "line", smooth: true, data: seriesData.valence, itemStyle: { color: colors.valence } },
          { name: "Arousal", type: "line", smooth: true, data: seriesData.arousal, itemStyle: { color: colors.arousal } },
          { name: "Dominance", type: "line", smooth: true, data: seriesData.dominance, itemStyle: { color: colors.dominance } },
        ];
    
    emotionChart.setOption({
      xAxis: {
        type: "category",
        data: timeAxis.map((t) => new Date(t * 1000).toLocaleTimeString()),
      },
      series,
    });
  };

  /**
   * 初始化 Control Panel 饼图
   */
  const initControlPanelDistributionChart = () => {
    if (!controlPanelDistributionRef.value) return;
    controlPanelDistributionChart = echarts.init(controlPanelDistributionRef.value);
    controlPanelDistributionChart.setOption({
      tooltip: {
        trigger: 'item',
        formatter: '{b}: {c} ({d}%)',
      },
      series: [{
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#fff',
          borderWidth: 2,
        },
        label: {
          show: false,
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 14,
            fontWeight: 'bold',
          },
        },
        data: emotionTypes.map(e => ({ name: e.name, value: 0 })),
      }],
    });
    updateControlPanelDistributionChart();
  };

  /**
   * 更新 Control Panel 饼图
   */
  const updateControlPanelDistributionChart = () => {
    if (!controlPanelDistributionChart) return;
    const emotionData: Record<string, number> = {};
    autoRecordingData.value.forEach((item: any) => {
      if (item.type === 'emotion_fusion' && item.label) {
        const emotion = item.label.toLowerCase();
        emotionData[emotion] = (emotionData[emotion] || 0) + 1;
      }
    });
    const chartData = emotionTypes.map(e => ({
      name: e.name,
      value: emotionData[e.name] || 0,
    }));
    controlPanelDistributionChart.setOption({
      series: [{
        data: chartData,
      }],
    });
  };

  /**
   * 初始化 Review 情绪时序图
   */
  const initReviewEmotionChart = () => {
    if (!reviewEmotionChartRef.value) return;
    reviewEmotionChart = echarts.init(reviewEmotionChartRef.value);
    reviewEmotionChart.setOption({
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
      },
      legend: {
        data: ['Valence', 'Arousal', 'Dominance'],
        bottom: 0,
        textStyle: { fontSize: 11 },
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '15%',
        top: '10%',
        containLabel: true,
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: [],
      },
      yAxis: {
        type: "value",
        min: -1,
        max: 1,
        name: 'Intensity',
      },
      series: [
        { name: "Valence", type: "line", smooth: true, data: [], symbol: 'none' },
        { name: "Arousal", type: "line", smooth: true, data: [], symbol: 'none' },
        { name: "Dominance", type: "line", smooth: true, data: [], symbol: 'none' },
      ],
    });
  };

  /**
   * 更新 Review 情绪时序图
   */
  const updateReviewEmotionChart = (data: any[]) => {
    if (!reviewEmotionChart) return;
    const reviewTimeAxis: number[] = [];
    const reviewSeriesData: Record<string, number[]> = {
      valence: [],
      arousal: [],
      dominance: [],
    };
    
    data.forEach((item: any) => {
      if (item.type === 'emotion_fusion' && item.timestamp) {
        const ts = item.timestamp;
        reviewTimeAxis.push(ts);
        reviewSeriesData.valence.push(item.valence ?? 0);
        reviewSeriesData.arousal.push(item.arousal ?? 0);
        reviewSeriesData.dominance.push(item.dominance ?? 0);
      }
    });
    
    reviewEmotionChart.setOption({
      xAxis: {
        data: reviewTimeAxis.map((t) => new Date(t * 1000).toLocaleTimeString()),
      },
      series: [
        { name: "Valence", data: reviewSeriesData.valence },
        { name: "Arousal", data: reviewSeriesData.arousal },
        { name: "Dominance", data: reviewSeriesData.dominance },
      ],
    });
  };

  /**
   * 初始化 Review 饼图
   */
  const initDistributionChart = () => {
    if (!emotionDistributionRef.value) return;
    distributionChart = echarts.init(emotionDistributionRef.value);
    distributionChart.setOption({
      tooltip: {
        trigger: 'item',
        formatter: '{b}: {c} ({d}%)',
      },
      series: [{
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#fff',
          borderWidth: 2,
        },
        label: {
          show: false,
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 14,
            fontWeight: 'bold',
          },
        },
        data: emotionTypes.map(e => ({ name: e.name, value: 0 })),
      }],
    });
  };

  /**
   * 更新 Review 饼图
   */
  const updateDistributionChart = (emotionData: Record<string, number>) => {
    if (!distributionChart) return;
    const chartData = emotionTypes.map(e => ({
      name: e.name,
      value: emotionData[e.name] || 0,
    }));
    distributionChart.setOption({
      series: [{
        data: chartData,
      }],
    });
  };

  /**
   * 清理图表资源
   */
  const dispose = () => {
    emotionChart?.dispose();
    controlPanelDistributionChart?.dispose();
    reviewEmotionChart?.dispose();
    distributionChart?.dispose();
  };

  return {
    // Refs
    emotionChartRef,
    controlPanelDistributionRef,
    reviewEmotionChartRef,
    emotionDistributionRef,
    // Data
    timeAxis,
    seriesData,
    // Methods
    pushSeries,
    initEmotionChart,
    updateEmotionChart,
    initControlPanelDistributionChart,
    updateControlPanelDistributionChart,
    initReviewEmotionChart,
    updateReviewEmotionChart,
    initDistributionChart,
    updateDistributionChart,
    dispose,
  };
};
