/**
 * WealthAI Copilot — WebSocket Client
 * Real-time communication with AI agents
 */
class WealthWSClient {
    constructor(wsUrl) {
        this.wsUrl = wsUrl;
        this.ws = null;
        this.connected = false;
        this.messageHandlers = [];
        this.statusHandlers = [];
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.clientId = '';
    }

    connect(clientId) {
        this.clientId = clientId || '';
        const url = this.clientId
            ? `${this.wsUrl}?client_id=${encodeURIComponent(this.clientId)}`
            : this.wsUrl;

        return new Promise((resolve, reject) => {
            console.log('[WS] Connecting:', url);
            this.ws = new WebSocket(url);

            this.ws.onopen = () => {
                console.log('[WS] Connected');
                this.connected = true;
                this.reconnectAttempts = 0;
                this._notifyStatus('connected');
                resolve();
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this._handleMessage(data);
                } catch (err) {
                    console.error('[WS] Parse error:', err);
                }
            };

            this.ws.onerror = (error) => {
                console.error('[WS] Error:', error);
                reject(error);
            };

            this.ws.onclose = (event) => {
                console.log('[WS] Disconnected, code:', event.code);
                this.connected = false;
                this._notifyStatus('disconnected');
                this._attemptReconnect();
            };
        });
    }

    disconnect() {
        this.maxReconnectAttempts = 0;
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.connected = false;
        this._notifyStatus('disconnected');
    }

    sendMessage(agent, message, sessionId) {
        if (!this.connected || !this.ws) {
            return Promise.reject(new Error('Not connected'));
        }

        const payload = {
            action: 'sendMessage',
            agent: agent,
            message: message,
            client_id: this.clientId,
            session_id: sessionId || ''
        };

        try {
            this.ws.send(JSON.stringify(payload));
            console.log('[WS] Sent:', agent, message.substring(0, 60));
            return Promise.resolve();
        } catch (err) {
            console.error('[WS] Send error:', err);
            return Promise.reject(err);
        }
    }

    onMessage(handler) {
        this.messageHandlers.push(handler);
    }

    onStatus(handler) {
        this.statusHandlers.push(handler);
    }

    _handleMessage(data) {
        for (const handler of this.messageHandlers) {
            try { handler(data); } catch (e) { console.error('[WS] Handler error:', e); }
        }
    }

    _notifyStatus(status) {
        for (const handler of this.statusHandlers) {
            try { handler(status); } catch (e) { console.error('[WS] Status handler error:', e); }
        }
    }

    _attemptReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('[WS] Max reconnect attempts reached');
            this._notifyStatus('failed');
            return;
        }
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * this.reconnectAttempts;
        console.log(`[WS] Reconnecting in ${delay}ms (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        this._notifyStatus('reconnecting');
        setTimeout(() => {
            this.connect(this.clientId).catch(() => {});
        }, delay);
    }
}
