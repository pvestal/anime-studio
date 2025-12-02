/**
 * WebSocket Progress Client for Anime Production System
 * Handles real-time progress updates from the anime production backend
 */

class AnimeProductionProgressClient {
    constructor(options = {}) {
        this.wsUrl = options.wsUrl || 'ws://192.168.50.135:8329';
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = options.maxReconnectAttempts || 10;
        this.reconnectDelay = options.reconnectDelay || 3000;
        this.reconnectBackoff = options.reconnectBackoff || 1.5;
        this.pingInterval = options.pingInterval || 30000;

        this.socket = null;
        this.isConnected = false;
        this.pingTimer = null;
        this.reconnectTimer = null;

        this.callbacks = {
            onConnect: options.onConnect || (() => {}),
            onDisconnect: options.onDisconnect || (() => {}),
            onProgressUpdate: options.onProgressUpdate || (() => {}),
            onJobComplete: options.onJobComplete || (() => {}),
            onError: options.onError || (() => {}),
            onInitialJobs: options.onInitialJobs || (() => {})
        };

        // Active jobs tracking
        this.activeJobs = new Map();

        // Statistics
        this.stats = {
            totalMessages: 0,
            totalReconnects: 0,
            lastMessageTime: null,
            connectionStartTime: null
        };
    }

    /**
     * Connect to the WebSocket server
     */
    connect() {
        try {
            console.log(`Connecting to anime production progress server: ${this.wsUrl}`);

            this.socket = new WebSocket(this.wsUrl);

            this.socket.onopen = (event) => {
                console.log('WebSocket connection established');
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.stats.connectionStartTime = Date.now();

                this.startPingTimer();
                this.callbacks.onConnect(event);
            };

            this.socket.onmessage = (event) => {
                this.handleMessage(event.data);
            };

            this.socket.onclose = (event) => {
                console.log('WebSocket connection closed:', event.code, event.reason);
                this.isConnected = false;
                this.stopPingTimer();

                this.callbacks.onDisconnect(event);

                // Attempt reconnection if not intentionally closed
                if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.scheduleReconnect();
                }
            };

            this.socket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.callbacks.onError(error);
            };

        } catch (error) {
            console.error('Failed to create WebSocket connection:', error);
            this.callbacks.onError(error);
        }
    }

    /**
     * Handle incoming WebSocket messages
     */
    handleMessage(data) {
        try {
            const message = JSON.parse(data);
            this.stats.totalMessages++;
            this.stats.lastMessageTime = Date.now();

            console.log('Received message:', message.type, message);

            switch (message.type) {
                case 'progress_update':
                    this.handleProgressUpdate(message);
                    break;

                case 'initial_jobs':
                    this.handleInitialJobs(message);
                    break;

                case 'job_status':
                    this.handleJobStatus(message);
                    break;

                case 'pong':
                    // Server responded to ping
                    console.log('Received pong from server');
                    break;

                default:
                    console.log('Unknown message type:', message.type);
            }

        } catch (error) {
            console.error('Error parsing WebSocket message:', error, data);
        }
    }

    /**
     * Handle progress update messages
     */
    handleProgressUpdate(message) {
        const job = message.job;
        const jobId = job.id || job.job_id;

        if (!jobId) {
            console.warn('Progress update missing job ID:', message);
            return;
        }

        // Update active jobs tracking
        this.activeJobs.set(jobId, job);

        // Add computed fields for UI
        const enrichedJob = this.enrichJobData(job);

        // Check if job completed
        if (enrichedJob.status === 'completed' || enrichedJob.status === 'failed') {
            this.callbacks.onJobComplete(enrichedJob);

            // Remove from active jobs after short delay
            setTimeout(() => {
                this.activeJobs.delete(jobId);
            }, 5000);
        }

        this.callbacks.onProgressUpdate(enrichedJob);
    }

    /**
     * Handle initial jobs data
     */
    handleInitialJobs(message) {
        const jobs = message.jobs || [];

        // Clear existing active jobs
        this.activeJobs.clear();

        // Add all initial jobs
        jobs.forEach(job => {
            if (job.id) {
                const enrichedJob = this.enrichJobData(job);
                this.activeJobs.set(job.id, enrichedJob);
            }
        });

        this.callbacks.onInitialJobs(Array.from(this.activeJobs.values()));
    }

    /**
     * Handle job status messages
     */
    handleJobStatus(message) {
        this.handleProgressUpdate(message);
    }

    /**
     * Enrich job data with computed fields for UI
     */
    enrichJobData(job) {
        const enriched = { ...job };

        // Format progress percentage
        enriched.progressFormatted = `${enriched.progress || 0}%`;

        // Format elapsed time
        if (enriched.elapsed_time) {
            enriched.elapsedFormatted = this.formatDuration(enriched.elapsed_time);
        }

        // Progress bar color based on status
        enriched.progressColor = this.getProgressColor(enriched.status, enriched.progress || 0);

        // Status icon
        enriched.statusIcon = this.getStatusIcon(enriched.status);

        // Time ago since created
        if (enriched.created_at) {
            enriched.createdAgo = this.getTimeAgo(new Date(enriched.created_at));
        }

        return enriched;
    }

    /**
     * Get progress bar color based on status and progress
     */
    getProgressColor(status, progress) {
        switch (status) {
            case 'completed':
                return '#4CAF50'; // Green
            case 'failed':
            case 'error':
                return '#F44336'; // Red
            case 'running':
            case 'processing':
                if (progress > 75) return '#8BC34A'; // Light green
                if (progress > 50) return '#FFC107'; // Amber
                return '#2196F3'; // Blue
            case 'queued':
            case 'pending':
                return '#9E9E9E'; // Grey
            default:
                return '#607D8B'; // Blue grey
        }
    }

    /**
     * Get status icon
     */
    getStatusIcon(status) {
        switch (status) {
            case 'completed':
                return '✅';
            case 'failed':
            case 'error':
                return '❌';
            case 'running':
            case 'processing':
                return '⚡';
            case 'queued':
            case 'pending':
                return '⏳';
            default:
                return '❓';
        }
    }

    /**
     * Format duration in seconds to human readable
     */
    formatDuration(seconds) {
        if (seconds < 60) {
            return `${seconds}s`;
        }

        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;

        if (minutes < 60) {
            return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
        }

        const hours = Math.floor(minutes / 60);
        const remainingMinutes = minutes % 60;

        return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
    }

    /**
     * Get time ago string
     */
    getTimeAgo(date) {
        const now = new Date();
        const diffMs = now - date;
        const diffSec = Math.floor(diffMs / 1000);
        const diffMin = Math.floor(diffSec / 60);
        const diffHour = Math.floor(diffMin / 60);

        if (diffSec < 60) return 'just now';
        if (diffMin < 60) return `${diffMin}m ago`;
        if (diffHour < 24) return `${diffHour}h ago`;

        const diffDays = Math.floor(diffHour / 24);
        return `${diffDays}d ago`;
    }

    /**
     * Subscribe to updates for a specific job
     */
    subscribeToJob(jobId) {
        if (this.isConnected) {
            this.send({
                type: 'subscribe_job',
                job_id: jobId
            });
        }
    }

    /**
     * Send message to server
     */
    send(data) {
        if (this.isConnected && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(data));
        } else {
            console.warn('Cannot send message: WebSocket not connected');
        }
    }

    /**
     * Send ping to server
     */
    sendPing() {
        this.send({ type: 'ping' });
    }

    /**
     * Start ping timer to keep connection alive
     */
    startPingTimer() {
        this.stopPingTimer();
        this.pingTimer = setInterval(() => {
            if (this.isConnected) {
                this.sendPing();
            }
        }, this.pingInterval);
    }

    /**
     * Stop ping timer
     */
    stopPingTimer() {
        if (this.pingTimer) {
            clearInterval(this.pingTimer);
            this.pingTimer = null;
        }
    }

    /**
     * Schedule reconnection attempt
     */
    scheduleReconnect() {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
        }

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(this.reconnectBackoff, this.reconnectAttempts - 1);

        console.log(`Scheduling reconnection attempt ${this.reconnectAttempts} in ${delay}ms`);

        this.reconnectTimer = setTimeout(() => {
            this.stats.totalReconnects++;
            this.connect();
        }, delay);
    }

    /**
     * Manually disconnect
     */
    disconnect() {
        this.reconnectAttempts = this.maxReconnectAttempts; // Prevent auto-reconnect

        this.stopPingTimer();

        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }

        if (this.socket) {
            this.socket.close(1000, 'Manual disconnect');
        }
    }

    /**
     * Get current active jobs
     */
    getActiveJobs() {
        return Array.from(this.activeJobs.values());
    }

    /**
     * Get connection statistics
     */
    getStats() {
        const uptime = this.stats.connectionStartTime
            ? Date.now() - this.stats.connectionStartTime
            : 0;

        return {
            ...this.stats,
            isConnected: this.isConnected,
            activeJobsCount: this.activeJobs.size,
            uptime: uptime,
            uptimeFormatted: this.formatDuration(Math.floor(uptime / 1000))
        };
    }
}

// Example usage with DOM manipulation for progress display
class AnimeProgressUI {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            throw new Error(`Container element with ID '${containerId}' not found`);
        }

        this.client = new AnimeProductionProgressClient({
            onConnect: () => this.onConnect(),
            onDisconnect: () => this.onDisconnect(),
            onProgressUpdate: (job) => this.onProgressUpdate(job),
            onJobComplete: (job) => this.onJobComplete(job),
            onError: (error) => this.onError(error),
            onInitialJobs: (jobs) => this.onInitialJobs(jobs),
            ...options
        });

        this.setupUI();
        this.client.connect();
    }

    setupUI() {
        this.container.innerHTML = `
            <div class="anime-progress-container">
                <div class="connection-status" id="connectionStatus">
                    <span class="status-indicator offline"></span>
                    <span class="status-text">Connecting...</span>
                </div>

                <div class="jobs-container" id="jobsContainer">
                    <h3>Active Generation Jobs</h3>
                    <div class="jobs-list" id="jobsList">
                        <div class="no-jobs">No active jobs</div>
                    </div>
                </div>

                <div class="stats-container" id="statsContainer">
                    <small class="stats-text">Messages: 0 | Reconnects: 0 | Uptime: 0s</small>
                </div>
            </div>
        `;

        // Start stats update timer
        setInterval(() => this.updateStats(), 1000);
    }

    onConnect() {
        const statusEl = document.getElementById('connectionStatus');
        statusEl.innerHTML = `
            <span class="status-indicator online"></span>
            <span class="status-text">Connected</span>
        `;
    }

    onDisconnect() {
        const statusEl = document.getElementById('connectionStatus');
        statusEl.innerHTML = `
            <span class="status-indicator offline"></span>
            <span class="status-text">Disconnected</span>
        `;
    }

    onInitialJobs(jobs) {
        this.renderJobs(jobs);
    }

    onProgressUpdate(job) {
        this.updateJobDisplay(job);
    }

    onJobComplete(job) {
        setTimeout(() => {
            this.removeJobDisplay(job.id);
        }, 3000);
    }

    onError(error) {
        console.error('Progress client error:', error);
    }

    renderJobs(jobs) {
        const jobsList = document.getElementById('jobsList');

        if (jobs.length === 0) {
            jobsList.innerHTML = '<div class="no-jobs">No active jobs</div>';
            return;
        }

        jobsList.innerHTML = jobs.map(job => this.createJobHTML(job)).join('');
    }

    updateJobDisplay(job) {
        let jobElement = document.getElementById(`job-${job.id}`);

        if (!jobElement) {
            // Create new job element
            const jobsList = document.getElementById('jobsList');
            const noJobsEl = jobsList.querySelector('.no-jobs');
            if (noJobsEl) noJobsEl.remove();

            jobElement = document.createElement('div');
            jobElement.id = `job-${job.id}`;
            jobElement.className = 'job-item';
            jobsList.appendChild(jobElement);
        }

        jobElement.innerHTML = this.createJobHTML(job);
    }

    createJobHTML(job) {
        return `
            <div class="job-header">
                <span class="job-id">${job.statusIcon} Job #${job.id}</span>
                <span class="job-time">${job.createdAgo || 'Just now'}</span>
            </div>

            <div class="job-prompt">${job.prompt || 'No prompt available'}</div>

            <div class="job-progress">
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${job.progress || 0}%; background-color: ${job.progressColor}"></div>
                </div>
                <span class="progress-text">${job.progressFormatted}</span>
            </div>

            <div class="job-details">
                <div class="job-stage">${job.current_stage || job.status || 'Unknown'}</div>
                <div class="job-eta">ETA: ${job.eta_formatted || 'Unknown'}</div>
            </div>

            ${job.frames_complete !== undefined ? `
                <div class="job-frames">
                    Frames: ${job.frames_complete}/${job.estimated_total_frames || '?'}
                </div>
            ` : ''}
        `;
    }

    removeJobDisplay(jobId) {
        const jobElement = document.getElementById(`job-${jobId}`);
        if (jobElement) {
            jobElement.remove();
        }

        // Show "no jobs" if no jobs remaining
        const jobsList = document.getElementById('jobsList');
        if (jobsList.children.length === 0) {
            jobsList.innerHTML = '<div class="no-jobs">No active jobs</div>';
        }
    }

    updateStats() {
        const stats = this.client.getStats();
        const statsEl = document.getElementById('statsContainer');
        if (statsEl) {
            statsEl.innerHTML = `
                <small class="stats-text">
                    Messages: ${stats.totalMessages} |
                    Reconnects: ${stats.totalReconnects} |
                    Uptime: ${stats.uptimeFormatted} |
                    Active Jobs: ${stats.activeJobsCount}
                </small>
            `;
        }
    }
}

// Auto-initialize if container exists
document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('animeProgressContainer');
    if (container) {
        window.animeProgressUI = new AnimeProgressUI('animeProgressContainer');
    }
});

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { AnimeProductionProgressClient, AnimeProgressUI };
}

// Global access
window.AnimeProductionProgressClient = AnimeProductionProgressClient;
window.AnimeProgressUI = AnimeProgressUI;