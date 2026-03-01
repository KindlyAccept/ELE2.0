export type DialogueItem = {
  role: string;
  content: string;
  timestamp: number;
};

export type MovementLog = {
  frame: number;
  content: string;
  timestamp: number;
};

export type EmotionType = {
  name: string;
  color: string;
};

export type Recording = {
  id: string;
  data: any[];
  startTime: number;
  endTime: number;
  sessionId: string;
  hasVideo?: boolean;
  videoBlob?: Blob;
  videoUrl?: string;
};
