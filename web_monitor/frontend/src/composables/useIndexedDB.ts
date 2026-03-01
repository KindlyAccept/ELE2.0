import type { Recording } from '../types';

const DB_NAME = 'EmotionRobotRecordings';
const DB_VERSION = 1;
const STORE_NAME = 'recordings';

/**
 * 打开数据库
 */
const openDB = (): Promise<IDBDatabase> => {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
    
    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' });
      }
    };
  });
};

/**
 * 深度清理对象，移除不可序列化的属性
 * 确保对象可以被 IndexedDB 的结构化克隆算法处理
 * IndexedDB 支持：基本类型、Date、Blob、File、ArrayBuffer、Array、普通对象
 * IndexedDB 不支持：函数、Symbol、循环引用
 */
const sanitizeForIndexedDB = (obj: any, visited = new WeakSet()): any => {
  if (obj === null || obj === undefined) {
    return obj;
  }
  
  // 处理基本类型
  if (typeof obj !== 'object') {
    return obj;
  }
  
  // 检测循环引用
  if (visited.has(obj)) {
    console.warn('Circular reference detected, removing from object');
    return null;
  }
  
  // IndexedDB 原生支持的类型，直接返回
  if (
    obj instanceof Date ||
    obj instanceof Blob ||
    obj instanceof File ||
    obj instanceof ArrayBuffer ||
    obj instanceof Uint8Array ||
    obj instanceof Uint16Array ||
    obj instanceof Uint32Array ||
    obj instanceof Int8Array ||
    obj instanceof Int16Array ||
    obj instanceof Int32Array ||
    obj instanceof Float32Array ||
    obj instanceof Float64Array
  ) {
    return obj;
  }
  
  // 处理数组
  if (Array.isArray(obj)) {
    visited.add(obj);
    const sanitized = obj.map(item => sanitizeForIndexedDB(item, visited));
    visited.delete(obj);
    return sanitized;
  }
  
  // 处理普通对象
  visited.add(obj);
  const sanitized: any = {};
  for (const key in obj) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      const value = obj[key];
      
      // 跳过函数、Symbol 等不可序列化的值
      if (typeof value === 'function' || typeof value === 'symbol') {
        continue;
      }
      
      // 递归清理嵌套对象
      sanitized[key] = sanitizeForIndexedDB(value, visited);
    }
  }
  visited.delete(obj);
  
  return sanitized;
};

/**
 * 保存录制到 IndexedDB
 */
export const saveRecordingToIndexedDB = async (recording: Recording): Promise<void> => {
  // 清理 recording 对象，确保可以序列化
  const sanitizedRecording = sanitizeForIndexedDB(recording) as Recording;
  
  const db = await openDB();
  const transaction = db.transaction([STORE_NAME], 'readwrite');
  const store = transaction.objectStore(STORE_NAME);
  
  return new Promise((resolve, reject) => {
    const request = store.add(sanitizedRecording);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
    transaction.onerror = () => reject(transaction.error);
  });
};

/**
 * 从 IndexedDB 加载所有录制
 */
export const loadRecordingsFromIndexedDB = async (): Promise<Recording[]> => {
  const db = await openDB();
  const transaction = db.transaction([STORE_NAME], 'readonly');
  const store = transaction.objectStore(STORE_NAME);
  
  return new Promise((resolve, reject) => {
    const request = store.getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
};

/**
 * 从 IndexedDB 加载单个录制
 */
export const loadRecordingFromIndexedDB = async (id: string): Promise<Recording | undefined> => {
  const db = await openDB();
  const transaction = db.transaction([STORE_NAME], 'readonly');
  const store = transaction.objectStore(STORE_NAME);
  
  return new Promise((resolve, reject) => {
    const request = store.get(id);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
};

/**
 * 从 IndexedDB 删除录制
 */
export const deleteRecordingFromIndexedDB = async (id: string): Promise<void> => {
  const db = await openDB();
  const transaction = db.transaction([STORE_NAME], 'readwrite');
  const store = transaction.objectStore(STORE_NAME);
  
  return new Promise((resolve, reject) => {
    const request = store.delete(id);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
};
