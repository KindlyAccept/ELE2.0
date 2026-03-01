/**
 * API工具函数 - 统一处理认证和请求
 */

export const getAuthHeaders = (): HeadersInit => {
  const token = localStorage.getItem('auth_token');
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
};

export const apiFetch = async (
  url: string,
  options: RequestInit = {}
): Promise<Response> => {
  const headers = {
    ...getAuthHeaders(),
    ...options.headers,
  };
  
  const response = await fetch(url, {
    ...options,
    headers,
  });
  
  // 如果token过期，清除本地存储
  if (response.status === 401) {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('username');
    // 可以触发登出事件或重定向到登录页
    window.dispatchEvent(new CustomEvent('auth:logout'));
  }
  
  return response;
};
