<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <img src="/logo.png" alt="Logo" class="login-logo" />
        <h1 class="login-title">&ltELE 2.0&gt</h1>
        <p class="login-subtitle">Emotion Robot Monitor</p>
      </div>
      
      <form @submit.prevent="handleLogin" class="login-form">
        <div class="form-group">
          <label for="username">Username</label>
          <input
            id="username"
            v-model="username"
            type="text"
            required
            autocomplete="username"
            placeholder="Enter username"
            class="form-input"
            :class="{ error: loginError }"
          />
        </div>
        
        <div class="form-group">
          <label for="password">Password</label>
          <div class="password-input-wrapper">
            <input
              id="password"
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              required
              autocomplete="current-password"
              placeholder="Enter password"
              class="form-input"
              :class="{ error: loginError }"
            />
            <button
              type="button"
              class="password-toggle"
              @click="showPassword = !showPassword"
              :aria-label="showPassword ? 'Hide password' : 'Show password'"
            >
              <svg v-if="showPassword" width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                <path d="M10 12a2 2 0 100-4 2 2 0 000 4z"/>
                <path fill-rule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clip-rule="evenodd"/>
              </svg>
              <svg v-else width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M3.707 2.293a1 1 0 00-1.414 1.414l14 14a1 1 0 001.414-1.414l-1.473-1.473A10.014 10.014 0 0019.542 10C18.268 5.943 14.478 3 10 3a9.958 9.958 0 00-4.906 1.285L2.293 2.293zm4.474 4.474L5.586 8.414A4 4 0 008.414 6.767zM8 10a2 2 0 00-.586 1.414L8 10zm2-4a2 2 0 012 2v.586l-2-2V6z" clip-rule="evenodd"/>
                <path d="M10 14a2 2 0 01-2-2v-.586l2 2V14zm4-4a2 2 0 00-.586-1.414L14 10a2 2 0 00-2 2v.586l2-2V10z"/>
              </svg>
            </button>
          </div>
        </div>
        
        <div v-if="loginError" class="error-message">
          {{ loginError }}
        </div>
        
        <button
          type="submit"
          class="login-button"
          :disabled="isLoading"
        >
          <span v-if="!isLoading">Login</span>
          <span v-else class="loading-spinner">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
              <circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="31.416" stroke-dashoffset="31.416">
                <animate attributeName="stroke-dasharray" dur="2s" values="0 31.416;15.708 15.708;0 31.416;0 31.416" repeatCount="indefinite"/>
                <animate attributeName="stroke-dashoffset" dur="2s" values="0;-15.708;-31.416;-31.416" repeatCount="indefinite"/>
              </circle>
            </svg>
            Logging in...
          </span>
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';

const emit = defineEmits<{
  (e: 'login', token: string): void;
}>();

const username = ref('');
const password = ref('');
const showPassword = ref(false);
const loginError = ref('');
const isLoading = ref(false);

const apiBase = ref((import.meta as any).env?.VITE_API_BASE ?? "http://127.0.0.1:8000");

// 检查服务器连接
const checkServerConnection = async () => {
  try {
    const response = await fetch(`${apiBase.value}/api/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(3000), // 3秒超时
    });
    return response.ok;
  } catch (error) {
    console.error('Server connection check failed:', error);
    return false;
  }
};

// Check connection when component mounts
onMounted(async () => {
  const isConnected = await checkServerConnection();
  if (!isConnected) {
    loginError.value = `Cannot connect to server (${apiBase.value})\n\nPlease check:\n1. Is the backend server running?\n2. Run: cd web_monitor/backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000\n3. Is the API address correct?`;
  }
});

const handleLogin = async () => {
  loginError.value = '';
  isLoading.value = true;
  
  try {
    // Check if API address is accessible
    const loginUrl = `${apiBase.value}/api/auth/login`;
    console.log('Attempting to login to:', loginUrl);
    
    const response = await fetch(loginUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        username: username.value,
        password: password.value,
      }),
    }).catch((fetchError) => {
      // Network error handling
      console.error('Network error:', fetchError);
      if (fetchError instanceof TypeError && fetchError.message.includes('fetch')) {
        throw new Error(`Cannot connect to server (${apiBase.value}). Please check:\n1. Is the backend server running?\n2. Is the API address correct?\n3. Is the network connection normal?`);
      }
      throw fetchError;
    });
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const statusText = response.statusText || 'Unknown error';
      const detail = errorData.detail || errorData.message || `HTTP ${response.status}: ${statusText}`;
      throw new Error(detail);
    }
    
    const data = await response.json();
    if (data.access_token) {
      // Save token to localStorage
      localStorage.setItem('auth_token', data.access_token);
      localStorage.setItem('username', username.value);
      emit('login', data.access_token);
    } else {
      throw new Error('Login response format error: access_token not found');
    }
  } catch (error) {
    console.error('Login error:', error);
    if (error instanceof Error) {
      loginError.value = error.message;
    } else {
      loginError.value = 'Login failed, please try again later. Error: ' + String(error);
    }
  } finally {
    isLoading.value = false;
  }
};
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
  padding: 20px;
  animation: fadeIn var(--transition-normal) ease-out;
}

.login-card {
  background: var(--surface);
  border-radius: var(--radius-lg);
  padding: 40px;
  width: 100%;
  max-width: 400px;
  box-shadow: var(--shadow-xl);
  animation: scaleIn var(--transition-normal) ease-out;
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.login-logo {
  width: 80px;
  height: 80px;
  margin: 0 auto 16px;
  object-fit: contain;
  animation: fadeIn var(--transition-slow) ease-out;
}

.login-title {
  font-family: 'Butterpop', sans-serif;
  font-size: 28px;
  color: var(--primary);
  margin-bottom: 8px;
  letter-spacing: 2px;
}

.login-subtitle {
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 500;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-group label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.password-input-wrapper {
  position: relative;
}

.form-input {
  width: 100%;
  padding: 12px 16px;
  border: 2px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 14px;
  background: var(--surface);
  color: var(--text-primary);
  transition: all var(--transition-normal) ease;
  font-family: 'Fira Sans', sans-serif;
}

.form-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(30, 64, 175, 0.1);
}

.form-input.error {
  border-color: var(--error);
}

.password-toggle {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color var(--transition-fast) ease;
}

.password-toggle:hover {
  color: var(--text-primary);
}

.error-message {
  padding: 12px;
  background: rgba(230, 57, 70, 0.1);
  color: var(--error);
  border-radius: var(--radius-sm);
  font-size: 14px;
  border: 1px solid rgba(230, 57, 70, 0.2);
  animation: slideInRight var(--transition-fast) ease-out;
}

.login-button {
  width: 100%;
  padding: 14px;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-normal) ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-family: 'Fira Sans', sans-serif;
}

.login-button:hover:not(:disabled) {
  background: #1E3A8A;
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
}

.login-button:active:not(:disabled) {
  transform: translateY(0);
}

.login-button:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.loading-spinner {
  display: flex;
  align-items: center;
  gap: 8px;
}

.loading-spinner svg {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 480px) {
  .login-card {
    padding: 32px 24px;
  }
  
  .login-title {
    font-size: 24px;
  }
}
</style>
