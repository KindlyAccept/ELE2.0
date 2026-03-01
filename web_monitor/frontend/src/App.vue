<template>
  <Login v-if="!isAuthenticated" @login="handleLogin" />
  <div v-else class="medical-monitor-app">
    <!-- Top Navigation Bar -->
    <header class="app-header">
      <div class="header-left">
        <div class="logo">
          <img src="/logo.png" alt="Logo" class="logo-img" />
          <span class="logo-text">&ltELE 2.0&gt</span>
        </div>
        <nav class="main-nav">
          <button 
            class="nav-item" 
            :class="{ active: currentView === 'control' }"
            @click="currentView = 'control'"
            title="Switch to Control Panel view - Monitor real-time system status and interactions"
          >
            Control Panel
          </button>
          <button 
            class="nav-item" 
            :class="{ active: currentView === 'review' }"
            @click="currentView = 'review'"
            title="Switch to Review view - Review and analyze recorded sessions"
          >
            Review
          </button>
        </nav>
      </div>
      <div class="header-right">
        <div class="header-menu-group">
          <button 
            class="primary-btn record-btn"
            :class="{ recording: isRecording }"
            @click="toggleRecording"
            :title="isRecording ? 'Stop recording session data' : 'Start recording session data for later review'"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
              <circle v-if="!isRecording" cx="8" cy="8" r="5"/>
              <rect v-else x="5" y="5" width="8" height="8" rx="1"/>
            </svg>
            <span v-if="!isRecording">Start Recording</span>
            <span v-else>
              Stop Recording
              <span class="recording-timer">{{ formatRecordingTime(recordingElapsedTime) }}</span>
            </span>
          </button>
          <button 
            class="settings-btn" 
            @click="showSettings = !showSettings"
            title="Open settings panel - Configure system parameters and LLM settings"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
              <path d="M10 12a2 2 0 100-4 2 2 0 000 4z"/>
              <path fill-rule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clip-rule="evenodd"/>
            </svg>
            Settings
          </button>
          <button 
            class="logout-btn" 
            @click="handleLogout"
            title="Logout"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M3 3a1 1 0 00-1 1v12a1 1 0 001 1h12a1 1 0 001-1V4a1 1 0 00-1-1H3zm1 0h12v12H4V3z" clip-rule="evenodd"/>
              <path d="M7 7h6v1H7V7zm0 2h6v1H7V9zm0 2h4v1H7v-1z"/>
              <path fill-rule="evenodd" d="M13 13a1 1 0 011 1v2a1 1 0 01-1 1H9a1 1 0 01-1-1v-2a1 1 0 011-1h4zm-1-2V9a1 1 0 00-1-1H7a1 1 0 00-1 1v2h6z" clip-rule="evenodd"/>
            </svg>
            Logout
          </button>
        </div>
      </div>
    </header>

    <!-- Control Panel View -->
    <div v-if="currentView === 'control'" class="control-panel-view">
      <div class="main-content">
        <!-- Main Content Area -->
        <div class="main-panel">
          <!-- Left Panel: System Status, Audio Control, Video Stream -->
          <div class="left-panel">
            <!-- Top: System Status and Audio Control Side by Side -->
            <div class="top-left-panel">
              <!-- System Status -->
              <div class="card status-card">
                <div class="card-header">
                  <h3>System Status</h3>
                </div>
                <div class="status-grid">
                  <div class="status-item">
                    <span class="status-label">Session ID</span>
                    <span class="status-value">{{ sessionId || 'Not Connected' }}</span>
                  </div>
                  <div class="status-item">
                    <span class="status-label">Vision</span>
                    <span class="status-badge" :class="getEmotionClass(latestVisionLabel)">
                      {{ latestVisionLabel }}
                    </span>
                  </div>
                  <div class="status-item">
                    <span class="status-label">Audio</span>
                    <span class="status-badge" :class="getEmotionClass(latestAudioLabel)">
                      {{ latestAudioLabel }}
                    </span>
                  </div>
                  <div class="status-item">
                    <span class="status-label">Fusion</span>
                    <span class="status-badge" :class="getEmotionClass(latestFusionLabel)">
                      {{ latestFusionLabel }}
                    </span>
                  </div>
                  <div class="status-item">
                    <span class="status-label">Vision FPS</span>
                    <span class="status-value">{{ status.vision_fps ?? '-' }}</span>
                  </div>
                  <div class="status-item">
                    <span class="status-label">Face Detected</span>
                    <span class="status-value">{{ status.face_detected ? 'Yes' : 'No' }}</span>
                  </div>
                </div>
              </div>

              <!-- Audio Control -->
              <div class="card control-card">
                <div class="card-header">
                  <h3>Audio</h3>
                </div>
                <div class="audio-controls">
                  <div class="slider-control">
                    <label>Volume</label>
                    <div class="slider-wrapper">
                      <input 
                        type="range" 
                        min="0" 
                        max="100" 
                        v-model="volumeValue"
                        @input="updateVolume"
                        class="range-slider"
                        title="Adjust audio output volume (0-100%)"
                      />
                      <span class="slider-value">{{ volumeValue }}%</span>
                    </div>
                  </div>
                  <button 
                    class="primary-btn" 
                    @click="playTrumpeting"
                    title="Play trumpeting sound effect"
                  >
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                      <path d="M8 2L3 7h3v6h4V7h3L8 2z"/>
                    </svg>
                    Trumpeting
                  </button>
                </div>
              </div>
            </div>

            <!-- Video Stream -->
            <div class="card video-card">
              <div class="card-header">
                <h3>Video Stream</h3>
                <div class="status-indicators">
                  <span class="status-dot" :class="{ active: isVideoActive }"></span>
                  <span class="status-text">{{ isVideoActive ? 'Live' : 'Offline' }}</span>
                </div>
              </div>
              <div class="video-container">
                <video ref="videoRef" autoplay playsinline muted></video>
                <div v-if="!isVideoActive" class="video-placeholder">
                  <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <rect x="2" y="6" width="20" height="12" rx="2"/>
                    <path d="M2 10l7-3 5 3 5-3 3 3"/>
                  </svg>
                  <p>Waiting for video stream...</p>
                </div>
              </div>
            </div>

            <!-- Predefined Actions -->
            <div class="card control-card">
              <div class="card-header">
                <h3>Predefined Actions</h3>
              </div>
              <div class="action-grid">
                <button 
                  v-for="action in predefinedActions" 
                  :key="action.id"
                  class="action-btn"
                  @click="triggerAction(action.id)"
                  :title="`Trigger ${action.label} predefined action`"
                >
                  {{ action.label }}
                </button>
              </div>
            </div>
          </div>

          <!-- Right Panel: Emotion Charts, Dialogue History -->
          <div class="right-panel">

          <!-- Emotion Charts -->
          <div class="card chart-card">
            <div class="card-header">
              <h3>Emotions Graph</h3>
              <div class="chart-controls">
                <button 
                  v-if="controlPanelChartMode === 'line'"
                  class="chart-btn" 
                  :class="{ active: chartTimeRange === '30s' }"
                  @click="chartTimeRange = '30s'"
                  title="Show last 30 seconds of emotion data"
                >
                  30s
                </button>
                <button 
                  v-if="controlPanelChartMode === 'line'"
                  class="chart-btn" 
                  :class="{ active: chartTimeRange === '1m' }"
                  @click="chartTimeRange = '1m'"
                  title="Show last 1 minute of emotion data"
                >
                  1m
                </button>
                <button 
                  v-if="controlPanelChartMode === 'line'"
                  class="chart-btn" 
                  :class="{ active: chartTimeRange === '5m' }"
                  @click="chartTimeRange = '5m'"
                  title="Show last 5 minutes of emotion data"
                >
                  5m
                </button>
                <button 
                  class="chart-btn chart-mode-btn"
                  @click="controlPanelChartMode = controlPanelChartMode === 'line' ? 'pie' : 'line'"
                  :title="controlPanelChartMode === 'line' ? 'Switch to Pie Chart' : 'Switch to Line Chart'"
                >
                  <svg v-if="controlPanelChartMode === 'line'" width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <circle cx="8" cy="8" r="6"/>
                  </svg>
                  <svg v-else width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M2 2 L14 2 L14 14 L2 14 Z M4 4 L12 4 M4 8 L12 8 M4 12 L12 12"/>
                  </svg>
                </button>
              </div>
            </div>
            <div class="chart-container">
              <div class="chart-wrapper">
                <div v-if="controlPanelChartMode === 'line'" ref="emotionChartRef" class="emotion-chart"></div>
                <div v-else ref="controlPanelDistributionRef" class="emotion-distribution-chart"></div>
              </div>
              <div v-if="controlPanelChartMode === 'pie'" class="emotions-legend">
                <div 
                  v-for="emotion in emotionTypes" 
                  :key="emotion.name"
                  class="legend-item"
                >
                  <span class="legend-color" :style="{ backgroundColor: emotion.color }"></span>
                  <span class="legend-label">{{ emotion.name }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 对话记录 -->
          <div class="card dialogue-card">
            <div class="card-header">
              <h3>Dialogue History</h3>
            </div>
            <div ref="dialogueListRef" class="dialogue-list">
              <div
                v-for="(item, index) in dialogue"
                :key="index"
                class="dialogue-item"
                :class="item.role"
              >
                <strong>{{ item.role }}</strong>: {{ item.content }}
              </div>
              <div v-if="dialogue.length === 0" class="dialogue-empty">
                No dialogue yet
              </div>
            </div>
            <div class="button-row">
              <button 
                @click="clearDialogue"
                title="Clear all dialogue history from current session"
              >
                Clear
              </button>
            </div>
          </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Review View -->
    <div v-if="currentView === 'review'" class="review-view">
      <div class="review-header">
        <div class="file-upload-area">
          <input 
            type="text" 
            v-model="sessionFile" 
            placeholder="Session file path or ID"
            class="file-input"
            title="Enter session file path or recording ID to load"
          />
          <button 
            class="secondary-btn" 
            @click="browseFile"
            title="Browse and select a recorded session from the list"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
              <path d="M2 2h12v12H2V2zm1 1v10h10V3H3zm2 2h6v1H5V5zm0 2h6v1H5V7zm0 2h4v1H5V9z"/>
            </svg>
            Browse Recordings
          </button>
          <button 
            class="secondary-btn" 
            @click="importFromFile"
            title="Import dialogue and emotion data from a JSON file"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
              <path d="M8 2L3 7h3v6h4V7h3L8 2z"/>
            </svg>
            Import JSON
          </button>
          <input 
            ref="fileInputRef" 
            type="file" 
            accept=".json" 
            style="display: none" 
            @change="handleFileImport"
          />
          <button 
            v-if="sessionFile" 
            class="secondary-btn delete-btn" 
            @click="deleteRecording(sessionFile)"
            title="Delete current recording"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
              <path d="M5.5 5.5A.5.5 0 016 6v6a.5.5 0 01-1 0V6a.5.5 0 01.5-.5zm2.5 0a.5.5 0 01.5.5v6a.5.5 0 01-1 0V6a.5.5 0 01.5-.5zm3 .5a.5.5 0 00-1 0v6a.5.5 0 001 0V6z"/>
              <path fill-rule="evenodd" d="M14.5 3a1 1 0 01-1 1H13v9a2 2 0 01-2 2H5a2 2 0 01-2-2V4h-.5a1 1 0 01-1-1V2a1 1 0 011-1H6a1 1 0 011-1h2a1 1 0 011 1h3.5a1 1 0 011 1v1zM4.118 4L4 4.059V13a1 1 0 001 1h6a1 1 0 001-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z" clip-rule="evenodd"/>
                </svg>
            Delete
              </button>
          </div>
        </div>

      <div class="review-content">
        <div class="review-main-layout">
          <!-- Left Panel: Emotion Charts, Dialogue History -->
          <div class="review-left-panel">
            <!-- Emotion Charts -->
            <div class="card chart-card">
              <div class="card-header">
                <h3>Emotions Graph</h3>
                <div class="chart-controls">
                  <button 
                    v-if="reviewChartMode === 'line'"
                    class="chart-btn" 
                    :class="{ active: chartTimeRange === '30s' }"
                    @click="chartTimeRange = '30s'"
                    title="Show last 30 seconds of emotion data"
                  >
                    30s
                  </button>
                  <button 
                    v-if="reviewChartMode === 'line'"
                    class="chart-btn" 
                    :class="{ active: chartTimeRange === '1m' }"
                    @click="chartTimeRange = '1m'"
                    title="Show last 1 minute of emotion data"
                  >
                    1m
                  </button>
                  <button 
                    v-if="reviewChartMode === 'line'"
                    class="chart-btn" 
                    :class="{ active: chartTimeRange === '5m' }"
                    @click="chartTimeRange = '5m'"
                    title="Show last 5 minutes of emotion data"
                  >
                    5m
                  </button>
                  <button 
                    class="chart-btn chart-mode-btn"
                    @click="reviewChartMode = reviewChartMode === 'line' ? 'pie' : 'line'"
                    :title="reviewChartMode === 'pie' ? 'Switch to Line Chart' : 'Switch to Pie Chart'"
                  >
                    <svg v-if="reviewChartMode === 'pie'" width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                      <path d="M2 2 L14 2 L14 14 L2 14 Z M4 4 L12 4 M4 8 L12 8 M4 12 L12 12"/>
                    </svg>
                    <svg v-else width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                      <circle cx="8" cy="8" r="6"/>
                    </svg>
                  </button>
                </div>
              </div>
              <div class="chart-container">
                <div class="chart-wrapper">
                  <div v-if="reviewChartMode === 'line'" ref="reviewEmotionChartRef" class="emotion-chart"></div>
                  <div v-else ref="emotionDistributionRef" class="emotion-distribution-chart"></div>
                </div>
                <div v-if="reviewChartMode === 'pie'" class="emotions-legend">
                  <div 
                    v-for="emotion in emotionTypes" 
                    :key="emotion.name"
                    class="legend-item"
                  >
                    <span class="legend-color" :style="{ backgroundColor: emotion.color }"></span>
                    <span class="legend-label">{{ emotion.name }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Dialogue History -->
            <div class="card dialogue-card">
              <div class="card-header">
                <h3>Dialogue History</h3>
              </div>
              <div ref="reviewDialogueListRef" class="dialogue-list">
                <div
                  v-for="(item, index) in reviewDialogue"
                  :key="index"
                  class="dialogue-item"
                  :class="item.role"
                >
                  <strong>{{ item.role }}</strong>: {{ item.content }}
                </div>
                <div v-if="reviewDialogue.length === 0" class="dialogue-empty">
                  No dialogue yet
                </div>
              </div>
            </div>
          </div>

          <!-- Right Panel: Movements Log -->
          <div class="review-right-panel">
            <div class="card movements-log-card">
              <div class="card-header">
                <h3>Movements Log</h3>
              </div>
              <div class="movements-log">
                <div 
                  v-for="(movement, index) in movementsLog" 
                  :key="index"
                  class="log-entry"
                  :class="{ active: index === selectedLogIndex }"
                  @click="selectLogEntry(index)"
                >
                  <span class="log-frame">{{ movement.frame }}</span>
                  <span class="log-content">{{ movement.content }}</span>
                  <span class="log-time">{{ formatTime(movement.timestamp) }}</span>
                </div>
                <div v-if="movementsLog.length === 0" class="log-empty">
                  No movements recorded
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>


    <!-- Settings Panel - Right Drawer -->
    <div v-if="showSettings" class="settings-overlay" @click="showSettings = false"></div>
    <div class="settings-drawer" :class="{ open: showSettings }">
      <div class="settings-panel">
        <div class="settings-header">
          <h2>Settings</h2>
          <button 
            @click="showSettings = false" 
            class="close-btn"
            title="Close settings panel"
          >
            ×
          </button>
        </div>
        <div class="settings-content">
          <div class="settings-tabs">
          <button 
            class="settings-tab" 
            :class="{ active: settingsTab === 'general' }"
            @click="settingsTab = 'general'"
            title="General application settings"
          >
            General
          </button>
          <button 
            class="settings-tab" 
            :class="{ active: settingsTab === 'llm' }"
            @click="settingsTab = 'llm'"
            title="Configure LLM parameters and prompt settings"
          >
            LLM Config
          </button>
          </div>
          
          <!-- General Settings -->
          <div v-if="settingsTab === 'general'" class="settings-tab-content">
            <div class="setting-item">
              <label>API Base URL</label>
              <input 
                type="text" 
                v-model="apiBase"
                title="Backend API server URL (e.g., http://127.0.0.1:8000)"
              />
            </div>
            <div class="setting-item">
              <label>Chart Update Interval (ms)</label>
              <input 
                type="number" 
                v-model="chartUpdateInterval"
                title="Time interval in milliseconds for updating emotion charts"
              />
            </div>
          </div>
          
          <!-- LLM Settings -->
          <div v-if="settingsTab === 'llm'" class="settings-tab-content">
            <div class="llm-config-section">
              <h3>LLM Parameters</h3>
              <div class="setting-item">
                <label>Context Size (n_ctx)</label>
                <input 
                  type="number" 
                  v-model.number="llmConfig.n_ctx" 
                  min="512" 
                  max="8192" 
                  step="256"
                  title="Maximum context window size for the LLM (512-8192 tokens)"
                />
              </div>
              <div class="setting-item">
                <label>Threads (n_threads)</label>
                <input 
                  type="number" 
                  v-model.number="llmConfig.n_threads" 
                  min="1" 
                  max="16"
                  title="Number of CPU threads to use for LLM inference (1-16)"
                />
              </div>
              <div class="setting-item">
                <label>Max Tokens</label>
                <input 
                  type="number" 
                  v-model.number="llmConfig.max_tokens" 
                  min="10" 
                  max="500"
                  title="Maximum number of tokens to generate in the response (10-500)"
                />
              </div>
              <div class="setting-item">
                <label>Temperature</label>
                <input 
                  type="number" 
                  v-model.number="llmConfig.temperature" 
                  min="0" 
                  max="2" 
                  step="0.1"
                  title="Sampling temperature - higher values make output more random (0-2)"
                />
              </div>
              <div class="setting-item">
                <label>Top P</label>
                <input 
                  type="number" 
                  v-model.number="llmConfig.top_p" 
                  min="0" 
                  max="1" 
                  step="0.05"
                  title="Nucleus sampling parameter - controls diversity of output (0-1)"
                />
              </div>
              <div class="setting-item">
                <label>Repeat Penalty</label>
                <input 
                  type="number" 
                  v-model.number="llmConfig.repeat_penalty" 
                  min="0.5" 
                  max="2" 
                  step="0.1"
                  title="Penalty for repeating tokens - higher values reduce repetition (0.5-2)"
                />
              </div>
            </div>
            
            <div class="llm-config-section">
              <h3>Prompt Configuration</h3>
              <div class="setting-item">
                <label>System Part</label>
                <textarea 
                  v-model="llmConfig.prompt.system_part" 
                  rows="4" 
                  placeholder="System instruction for the LLM..."
                  class="prompt-textarea"
                  title="System instruction that defines the robot's role and behavior"
                ></textarea>
              </div>
              <div class="setting-item">
                <label>Emotion Prefix (use {emotion_desc} as placeholder)</label>
                <input 
                  type="text" 
                  v-model="llmConfig.prompt.emotion_prefix" 
                  placeholder="The child feels: {emotion_desc}\n\n"
                  title="Template for emotion description in prompt (use {emotion_desc} as placeholder)"
                />
              </div>
              <div class="setting-item">
                <label>History Format (use {role} and {content} as placeholders)</label>
                <input 
                  type="text" 
                  v-model="llmConfig.prompt.history_format" 
                  placeholder="{role}: {content}\n"
                  title="Format template for dialogue history (use {role} and {content} as placeholders)"
                />
              </div>
              <div class="setting-item">
                <label>User Prefix</label>
                <input 
                  type="text" 
                  v-model="llmConfig.prompt.user_prefix" 
                  placeholder="Child: "
                  title="Prefix text before user input in the prompt"
                />
              </div>
              <div class="setting-item">
                <label>Assistant Prefix</label>
                <input 
                  type="text" 
                  v-model="llmConfig.prompt.assistant_prefix" 
                  placeholder="Robot: ["
                  title="Prefix text before assistant response in the prompt"
                />
              </div>
            </div>
            
            <div class="llm-config-actions">
              <button 
                class="primary-btn" 
                @click="saveLLMConfig"
                title="Save LLM configuration - changes will take effect immediately"
              >
                Save LLM Config
              </button>
              <button 
                class="secondary-btn" 
                @click="loadLLMConfig"
                title="Reset all LLM settings to default values"
              >
                Reset to Default
              </button>
            </div>
            <div v-if="llmConfigMessage" class="llm-config-message" :class="{ error: llmConfigError }">
              {{ llmConfigMessage }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Recording List Panel - Right Drawer -->
    <div v-if="showRecordingList" class="settings-overlay" @click="showRecordingList = false"></div>
    <div class="settings-drawer" :class="{ open: showRecordingList }">
      <div class="settings-panel recording-list-panel">
        <div class="settings-header">
          <h2>Select Recording</h2>
          <button 
            @click="showRecordingList = false" 
            class="close-btn"
            title="Close recordings list"
          >
            ×
          </button>
        </div>
        <div class="recording-list-content">
          <div 
            v-for="recording in availableRecordings" 
            :key="recording.id"
            class="recording-item"
          >
            <div 
              class="recording-item-content" 
              @click="selectRecording(recording)"
              title="Click to load this recording"
            >
            <div class="recording-info">
              <strong>{{ recording.id }}</strong>
              <span class="recording-time">{{ new Date(recording.startTime).toLocaleString() }}</span>
            </div>
            <div class="recording-meta">
              <span>{{ recording.data?.length || 0 }} data points</span>
            </div>
            </div>
            <button 
              class="delete-recording-btn"
              @click="deleteRecording(recording.id, $event)"
              title="Delete recording"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M5.5 5.5A.5.5 0 016 6v6a.5.5 0 01-1 0V6a.5.5 0 01.5-.5zm2.5 0a.5.5 0 01.5.5v6a.5.5 0 01-1 0V6a.5.5 0 01.5-.5zm3 .5a.5.5 0 00-1 0v6a.5.5 0 001 0V6z"/>
                <path fill-rule="evenodd" d="M14.5 3a1 1 0 01-1 1H13v9a2 2 0 01-2 2H5a2 2 0 01-2-2V4h-.5a1 1 0 01-1-1V2a1 1 0 011-1H6a1 1 0 011-1h2a1 1 0 011 1h3.5a1 1 0 011 1v1zM4.118 4L4 4.059V13a1 1 0 001 1h6a1 1 0 001-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z" clip-rule="evenodd"/>
              </svg>
            </button>
          </div>
          <div v-if="availableRecordings.length === 0" class="recording-empty">
            No recordings available
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch, nextTick } from "vue";
import type { DialogueItem, MovementLog, EmotionType } from "./types";
import { useRecording } from "./composables/useRecording";
import { useCharts } from "./composables/useCharts";
import { useSSE } from "./composables/useSSE";
import { useWebRTC } from "./composables/useWebRTC";
import { formatRecordingTime, formatTime } from "./utils/timeFormatters";
import { exportDataAsJSON, prepareExportData } from "./utils/dataExport";
import {
  saveRecordingToIndexedDB,
  loadRecordingsFromIndexedDB,
  loadRecordingFromIndexedDB,
  deleteRecordingFromIndexedDB,
} from "./composables/useIndexedDB";
import Login from "./components/Login.vue";
import { apiFetch } from "./utils/api";

const apiBase = ref((import.meta as any).env?.VITE_API_BASE ?? "http://127.0.0.1:8000");

// Authentication state
const isAuthenticated = ref(false);
const authToken = ref<string | null>(null);

// Check token in local storage
const checkAuth = () => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    authToken.value = token;
    isAuthenticated.value = true;
    // Verify token is still valid
    verifyToken(token);
  }
};

// Verify token validity
const verifyToken = async (token: string) => {
  try {
    const response = await apiFetch(`${apiBase.value}/api/auth/me`);
    if (!response.ok) {
      throw new Error('Invalid token');
    }
  } catch (error) {
    // Token invalid, clear local storage
    localStorage.removeItem('auth_token');
    localStorage.removeItem('username');
    isAuthenticated.value = false;
    authToken.value = null;
  }
};

// Listen for logout event
window.addEventListener('auth:logout', () => {
  handleLogout();
});

// Handle login
const handleLogin = async (token: string) => {
  authToken.value = token;
  isAuthenticated.value = true;
  // watch(isAuthenticated) with flush:'post' handles initializeApp() after DOM update
};

// Initialize application features
const initializeApp = async () => {
  try {
    // Initialize charts
    initEmotionChart();
    
    // Connect SSE
    connectSSE();
    
    // Load status and history
    await loadStatus();
    await loadHistory();
    
    // Start WebRTC connection (if currently in Control Panel view)
    if (currentView.value === 'control') {
      // Wait for DOM update to ensure video element is created
      await nextTick();
      await new Promise(resolve => setTimeout(resolve, 100));
      
      if (videoRef.value) {
        console.log('Starting WebRTC connection...');
        await startWebRTCConnection(apiBase.value);
      } else {
        console.warn('Video element not found');
      }
    }
    
    // Initialize auto recording cache
    autoRecordingStartTime.value = Date.now();
    
    console.log('Application initialization completed');
  } catch (error) {
    console.error('Error initializing application:', error);
  }
};

// Logout function
const handleLogout = () => {
  localStorage.removeItem('auth_token');
  localStorage.removeItem('username');
  isAuthenticated.value = false;
  authToken.value = null;
  // Close all connections
  closeSSE();
  closeWebRTC();
  disposeCharts();
  cleanupRecording();
};

// View state
const currentView = ref<'control' | 'review'>('control');
const showSettings = ref(false);
const chartUpdateInterval = ref(1000);
const settingsTab = ref<'general' | 'llm'>('general');

// LLM configuration state
const llmConfig = ref({
  n_ctx: 2048,
  n_threads: 4,
  max_tokens: 100,
  temperature: 0.7,
  top_p: 0.9,
  repeat_penalty: 1.1,
  prompt: {
    system_part: "You are a friendly robot talking to a child. Start your reply with a single tone tag in brackets.\nTone options: [cheerful] [excited] [comforting] [gentle] [calm] [neutral]\nExample: [cheerful] Hello! Nice to see you!",
    emotion_prefix: "The child feels: {emotion_desc}\n\n",
    history_format: "{role}: {content}\n",
    user_prefix: "Child: ",
    assistant_prefix: "Robot: [",
  },
});
const llmConfigMessage = ref("");
const llmConfigError = ref(false);

// Video related (for real-time display only, not recording)
const videoRef = ref<HTMLVideoElement | null>(null);
const isVideoActive = ref(false);
const { startWebRTC: startWebRTCConnection, closeWebRTC } = useWebRTC(videoRef, isVideoActive);

// Data state
const sessionId = ref<string>("");
const dialogue = ref<DialogueItem[]>([]);
const status = ref<Record<string, any>>({});
const latestVisionLabel = ref("unknown");
const latestAudioLabel = ref("unknown");
const latestFusionLabel = ref("unknown");

// Control state (isRecording is defined in useRecording composable)
const proboscisValue = ref(50);
const volumeValue = ref(50);
const chartTimeRange = ref<'30s' | '1m' | '5m'>('1m');

// Chart display mode
const controlPanelChartMode = ref<'line' | 'pie'>('line');
const reviewChartMode = ref<'line' | 'pie'>('pie');

// Auto recording cache (all data automatically collected, no manual recording needed)
const autoRecordingData = ref<any[]>([]);
const autoRecordingStartTime = ref<number>(Date.now());

// Recording related (using composable)
const {
  isRecording,
  recordingData,
  recordingElapsedTime,
  formatTime: formatRecordingTimeDisplay,
  toggleRecording,
  addRecordingData,
  cleanup: cleanupRecording,
} = useRecording(sessionId);

// Review related
const sessionFile = ref("");
const selectedLogIndex = ref(-1);
const movementsLog = ref<MovementLog[]>([]);
const reviewDialogue = ref<DialogueItem[]>([]);
const fileInputRef = ref<HTMLInputElement | null>(null);

// Predefined actions
const predefinedActions = [
  { id: 'hello', label: 'HELLO' },
  { id: 'shy', label: 'SHY' },
  { id: 'happy', label: 'HAPPY' },
  { id: 'afraid', label: 'AFRAID' },
];

// Emotion types
const emotionTypes: EmotionType[] = [
  { name: 'joy', color: '#FF6B9D' },
  { name: 'sadness', color: '#4ECDC4' },
  { name: 'disgust', color: '#FFA07A' },
  { name: 'contempt', color: '#9B59B6' },
  { name: 'anger', color: '#06A77D' },
  { name: 'fear', color: '#E63946' },
  { name: 'surprise', color: '#FFD93D' },
  { name: 'engagement', color: '#F77F00' },
];

// Chart related (using composable)
const {
  emotionChartRef,
  controlPanelDistributionRef,
  reviewEmotionChartRef,
  emotionDistributionRef,
  timeAxis,
  seriesData,
  pushSeries,
  initEmotionChart,
  updateEmotionChart,
  initControlPanelDistributionChart,
  updateControlPanelDistributionChart,
  initReviewEmotionChart,
  updateReviewEmotionChart,
  initDistributionChart,
  updateDistributionChart,
  dispose: disposeCharts,
} = useCharts(emotionTypes, autoRecordingData);

// Dialogue list references
const dialogueListRef = ref<HTMLDivElement | null>(null);
const reviewDialogueListRef = ref<HTMLDivElement | null>(null);

// SSE connection (using composable)
const { connectSSE, closeSSE } = useSSE(
  apiBase,
  autoRecordingData,
  recordingData,
  isRecording,
  dialogue,
  status,
  latestVisionLabel,
  latestAudioLabel,
  latestFusionLabel,
  isVideoActive,
  pushSeries,
  () => {
    updateEmotionChart();
    // If Control Panel is in pie chart mode, also update pie chart
    if (controlPanelChartMode.value === 'pie') {
      updateControlPanelDistributionChart();
    }
  }
);

const loadStatus = async () => {
  try {
    const res = await apiFetch(`${apiBase.value}/api/status`);
    const data = await res.json();
    sessionId.value = data.session_id || "";
  } catch (error) {
    console.error('Failed to load status:', error);
  }
};

const loadHistory = async () => {
  try {
    const res = await apiFetch(`${apiBase.value}/api/dialogue/history`);
    const data = await res.json();
    dialogue.value = data.items || [];
  } catch (error) {
    console.error('Failed to load history:', error);
  }
};

const clearDialogue = async () => {
  try {
    await apiFetch(`${apiBase.value}/api/dialogue/clear`, { method: "POST" });
    dialogue.value = [];
  } catch (error) {
    console.error('Failed to clear dialogue:', error);
  }
};

// Recording related functions are defined in composables/useRecording.ts

const triggerAction = (actionId: string) => {
  console.log('Trigger action:', actionId);
  // TODO: Implement action trigger
};

const triggerMovement = (part: string, type: string) => {
  console.log('Trigger movement:', part, type);
  // TODO: Implement movement control
};

const updateProboscis = () => {
  console.log('Update proboscis:', proboscisValue.value);
  // TODO: Implement proboscis control
};

const updateVolume = async () => {
  try {
    const response = await apiFetch(`${apiBase.value}/api/audio/volume`, {
      method: 'POST',
      body: JSON.stringify({ volume: volumeValue.value }),
    });
    
    if (!response.ok) {
      throw new Error(`Failed to update volume: ${response.statusText}`);
    }
    
    console.log('Volume updated:', volumeValue.value);
  } catch (error) {
    console.error('Failed to update volume:', error);
    // Can optionally show error message to user
  }
};

const loadLLMConfig = async () => {
  try {
    const response = await apiFetch(`${apiBase.value}/api/llm/config`);
    if (!response.ok) {
      throw new Error(`Failed to load LLM config: ${response.statusText}`);
    }
    const data = await response.json();
    if (data.config) {
      llmConfig.value = JSON.parse(JSON.stringify(data.config)); // Deep copy
      llmConfigMessage.value = "Configuration loaded";
      llmConfigError.value = false;
    }
  } catch (error) {
    console.error('Failed to load LLM config:', error);
    llmConfigMessage.value = `Failed to load configuration: ${error instanceof Error ? error.message : 'Unknown error'}`;
    llmConfigError.value = true;
  }
};

const saveLLMConfig = async () => {
  try {
    const response = await apiFetch(`${apiBase.value}/api/llm/config`, {
      method: 'POST',
      body: JSON.stringify({ config: llmConfig.value }),
    });
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.message || `Failed to save LLM config: ${response.statusText}`);
    }
    
    const data = await response.json();
    llmConfigMessage.value = data.message || "Configuration saved";
    llmConfigError.value = false;
  } catch (error) {
    console.error('Failed to save LLM config:', error);
    llmConfigMessage.value = `Failed to save configuration: ${error instanceof Error ? error.message : 'Unknown error'}`;
    llmConfigError.value = true;
  }
};

const playTrumpeting = () => {
  console.log('Play trumpeting');
  // TODO: Implement trumpeting sound playback
};

const getEmotionClass = (emotion: string) => {
  const emotionMap: Record<string, string> = {
    joy: 'emotion-joy',
    sadness: 'emotion-sadness',
    anger: 'emotion-anger',
    fear: 'emotion-fear',
    happy: 'emotion-joy',
  };
  return emotionMap[emotion.toLowerCase()] || '';
};

// IndexedDB 函数已在 composables/useIndexedDB.ts 中定义

const deleteRecording = async (recordingId: string, event?: Event) => {
  if (event) {
    event.stopPropagation(); // 防止触发 selectRecording
  }
  
  if (!confirm(`Are you sure you want to delete recording "${recordingId}"?`)) {
    return;
  }
  
  try {
    await deleteRecordingFromIndexedDB(recordingId);
    
    // If deleting the currently viewed recording, clear display
    if (sessionFile.value === recordingId) {
      sessionFile.value = '';
      movementsLog.value = [];
      updateDistributionChart({});
    }
    
    // Update recording list
    availableRecordings.value = availableRecordings.value.filter(r => r.id !== recordingId);
    
    // If in recording list, refresh list
    if (showRecordingList.value) {
      availableRecordings.value = await loadRecordingsFromIndexedDB();
    }
    
    alert('Recording deleted successfully');
  } catch (error) {
    console.error('Failed to delete recording:', error);
    alert(`Failed to delete recording: ${error instanceof Error ? error.message : 'Unknown error'}`);
  }
};

// Review 功能
const availableRecordings = ref<any[]>([]);
const showRecordingList = ref(false);

const browseFile = async () => {
  // Load all recordings from IndexedDB
  try {
    availableRecordings.value = await loadRecordingsFromIndexedDB();
    if (availableRecordings.value.length > 0) {
      showRecordingList.value = true;
    } else {
      alert('No recordings found. Please record a session first.');
    }
  } catch (error) {
    console.error('Failed to load recordings:', error);
    alert('Failed to load recordings');
  }
};

const selectRecording = async (recording: any) => {
  showRecordingList.value = false;
  await loadRecording(recording.id);
};

const openFromCloud = () => {
  // Cloud storage feature not yet implemented
  alert('Cloud storage feature not implemented yet');
};

const loadRecording = async (recordingId: string) => {
  try {
    const recording = await loadRecordingFromIndexedDB(recordingId);
    if (!recording) {
      alert('Recording not found');
      return;
    }
    
    // Load data
    if (recording.data) {
      // Process emotion data (for pie chart)
      const emotionData: Record<string, number> = {};
      const emotionFusionData: any[] = [];
      
      recording.data.forEach((item: any) => {
        if (item.type === 'emotion_fusion') {
          emotionFusionData.push(item);
          const emotion = item.label?.toLowerCase();
          if (emotion) {
            emotionData[emotion] = (emotionData[emotion] || 0) + 1;
          }
        }
      });
      
      // Update emotion distribution chart (pie chart)
      updateDistributionChart(emotionData);
      
      // Update time series chart
      updateReviewEmotionChart(emotionFusionData);
      
      // Load dialogue data
      reviewDialogue.value = recording.data
        .filter((item: any) => item.type === 'dialogue_event')
        .map((item: any) => ({
          role: item.role,
          content: item.content,
          timestamp: item.timestamp,
        }));
      
      // Load movement log
      movementsLog.value = recording.data
        .filter((item: any) => item.type === 'movement' || item.type === 'action')
        .map((item: any, index: number) => ({
          frame: index + 1,
          content: item.content || `${item.type}: ${item.action || item.movement}`,
          timestamp: item.timestamp || recording.startTime / 1000,
        }));
    }
    
    sessionFile.value = recordingId;
  } catch (error) {
    console.error('Failed to load recording:', error);
    alert('Failed to load recording');
  }
};

const selectLogEntry = (index: number) => {
  selectedLogIndex.value = index;
};

// formatTime 已在 utils/timeFormatters.ts 中定义

const importFromFile = () => {
  fileInputRef.value?.click();
};

const handleFileImport = async (event: Event) => {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0];
  if (!file) return;
  
  // Validate file size (max 10MB)
  const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
  if (file.size > MAX_FILE_SIZE) {
    alert(`File size exceeds maximum allowed size (10MB). File size: ${(file.size / 1024 / 1024).toFixed(2)}MB`);
    if (target) {
      target.value = '';
    }
    return;
  }
  
  // Validate file type
  if (!file.name.endsWith('.json') && file.type !== 'application/json') {
    alert('Invalid file type. Please select a JSON file.');
    if (target) {
      target.value = '';
    }
    return;
  }
  
  try {
    const text = await file.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch (parseError) {
      alert('Invalid JSON format. The file is not valid JSON.');
      if (target) {
        target.value = '';
      }
      return;
    }
    
    // Validate data format
    if (!data || typeof data !== 'object') {
      alert('Invalid JSON format. Expected an object.');
      if (target) {
        target.value = '';
      }
      return;
    }
    
    if (!data.dialogue || !data.emotionData) {
      alert('Invalid JSON format. Expected dialogue and emotionData fields.');
      if (target) {
        target.value = '';
      }
      return;
    }
    
    // Convert imported data to recording format
    const recordingId = `imported_${Date.now()}`;
    const recording: any = {
      id: recordingId,
      data: [],
      startTime: data.exportTimestamp ? new Date(data.exportTimestamp).getTime() : Date.now(),
      endTime: Date.now(),
      sessionId: data.sessionId || '',
    };
    
    // Convert dialogue data
    if (Array.isArray(data.dialogue)) {
      data.dialogue.forEach((item: any) => {
        recording.data.push({
          type: 'dialogue_event',
          role: item.role,
          content: item.content,
          timestamp: item.timestamp || (item.timestampISO ? new Date(item.timestampISO).getTime() / 1000 : Date.now() / 1000),
        });
      });
    }
    
    // Convert emotion data
    if (data.emotionData) {
      ['valence', 'arousal', 'dominance'].forEach(key => {
        if (Array.isArray(data.emotionData[key])) {
          data.emotionData[key].forEach((item: any) => {
            recording.data.push({
              type: 'emotion_fusion',
              timestamp: item.timestamp || (item.timestampISO ? new Date(item.timestampISO).getTime() / 1000 : Date.now() / 1000),
              [key]: item.value,
            });
          });
        }
      });
    }
    
    // Save to IndexedDB
    await saveRecordingToIndexedDB(recording);
    
    // Load imported data
    await loadRecording(recordingId);
    
    // Refresh recording list
    availableRecordings.value = await loadRecordingsFromIndexedDB();
    
    alert(`Data imported successfully: ${recordingId}\nData points: ${recording.data.length}`);
  } catch (error) {
    console.error('Failed to import file:', error);
    alert(`Failed to import file: ${error instanceof Error ? error.message : 'Unknown error'}`);
  } finally {
    // Reset file input
    if (target) {
      target.value = '';
    }
  }
};

const exportDataAndDialogue = () => {
  const emotionFusionData = autoRecordingData.value.filter(item => item.type === 'emotion_fusion');
  const dialogueData = autoRecordingData.value.filter(item => item.type === 'dialogue_event');
  
  const exportData = prepareExportData(
    sessionId.value,
    dialogueData,
    emotionFusionData,
    status.value,
    latestVisionLabel.value,
    latestAudioLabel.value,
    latestFusionLabel.value
  );
  
  exportDataAsJSON(exportData);
  
  // Clear auto recording cache after export
  autoRecordingData.value = [];
  autoRecordingStartTime.value = Date.now();
};

// Auto scroll dialogue list to bottom
const scrollDialogueToBottom = () => {
  if (dialogueListRef.value) {
    nextTick(() => {
      dialogueListRef.value!.scrollTop = dialogueListRef.value!.scrollHeight;
    });
  }
};

// Watch dialogue changes, auto scroll to bottom
watch(dialogue, () => {
  scrollDialogueToBottom();
}, { deep: true });

// Watch chart mode changes
watch(controlPanelChartMode, async (newMode) => {
  await nextTick();
  if (newMode === 'pie') {
    initControlPanelDistributionChart();
  }
}, { immediate: false });

watch(reviewChartMode, async (newMode) => {
  await nextTick();
  if (newMode === 'line') {
    initReviewEmotionChart();
    // If there is loaded recording data, update chart
    if (sessionFile.value) {
      // Reload recording to update time series chart
      const recording = await loadRecordingFromIndexedDB(sessionFile.value);
      if (recording && recording.data) {
        const emotionFusionData = recording.data.filter((item: any) => item.type === 'emotion_fusion');
        updateReviewEmotionChart(emotionFusionData);
      }
    }
  }
}, { immediate: false });

watch(currentView, async (newView) => {
  if (newView === 'review') {
    await nextTick();
    // Close video stream when switching to Review
    closeWebRTC();
    // Initialize chart based on current mode
    if (reviewChartMode.value === 'pie') {
      initDistributionChart();
    } else {
      initReviewEmotionChart();
    }
    // Load available recording list
    try {
      availableRecordings.value = await loadRecordingsFromIndexedDB();
    } catch (error) {
      console.error('Failed to load recordings:', error);
    }
  } else if (newView === 'control') {
    // Restart video stream when switching back to Control Panel
    await nextTick();
    // Wait for DOM to fully update, ensure video element is created
    await new Promise(resolve => setTimeout(resolve, 100));
    
    // Restart connection regardless of isVideoActive state
    // Because video element is recreated, need to reset srcObject
    if (videoRef.value) {
      console.log('Restarting WebRTC connection...');
      await startWebRTCConnection(apiBase.value);
    } else {
      console.warn('Video element not found when switching to control panel');
    }
    // Scroll dialogue to bottom
    scrollDialogueToBottom();
    // Initialize chart based on current mode
    if (controlPanelChartMode.value === 'pie') {
      initControlPanelDistributionChart();
    }
  }
});

// When opening settings panel, if LLM tab, load configuration
watch(showSettings, (newVal) => {
  if (newVal && settingsTab.value === 'llm') {
    loadLLMConfig();
  }
});

watch(settingsTab, (newTab) => {
  if (newTab === 'llm' && showSettings.value) {
    loadLLMConfig();
  }
});

onMounted(() => {
  // Check authentication state; watch(isAuthenticated) will call initializeApp() if authenticated
  checkAuth();
});

// Single source of truth for initialization/cleanup on auth state change.
// flush:'post' ensures DOM is updated (Login hidden, app rendered) before chart init.
watch(isAuthenticated, async (newVal, oldVal) => {
  if (newVal && !oldVal) {
    // Changed from unauthenticated to authenticated, initialize application
    await initializeApp();
  } else if (!newVal && oldVal) {
    // Changed from authenticated to unauthenticated, cleanup resources
    closeSSE();
    closeWebRTC();
    disposeCharts();
    cleanupRecording();
    autoRecordingData.value = [];
  }
}, { flush: 'post' });

onBeforeUnmount(() => {
  closeSSE();
  closeWebRTC();
  disposeCharts();
  cleanupRecording();
  // Clear auto recording cache when exiting
  autoRecordingData.value = [];
});
</script>
