/**
 * WebSocket Client for GenAI Pet Store
 * Handles real-time communication with agents
 */

class WebSocketClient {
    constructor(wsUrl) {
        this.wsUrl = wsUrl;
        this.ws = null;
        this.connected = false;
        this.messageHandlers = [];
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
    }

    connect() {
        return new Promise((resolve, reject) => {
            console.log('🔌 Connecting to WebSocket:', this.wsUrl);

            this.ws = new WebSocket(this.wsUrl);

            this.ws.onopen = () => {
                console.log('✅ WebSocket connected');
                this.connected = true;
                this.reconnectAttempts = 0;
                resolve();
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    console.log('📨 WebSocket message:', data);
                    this.handleMessage(data);
                } catch (error) {
                    console.error('❌ Error parsing WebSocket message:', error);
                }
            };

            this.ws.onerror = (error) => {
                console.error('❌ WebSocket error:', error);
                reject(error);
            };

            this.ws.onclose = () => {
                console.log('🔌 WebSocket disconnected');
                this.connected = false;
                this.attemptReconnect();
            };
        });
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * this.reconnectAttempts;
            
            console.log(`🔄 Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
            
            setTimeout(() => {
                this.connect().catch(error => {
                    console.error('❌ Reconnection failed:', error);
                });
            }, delay);
        } else {
            console.error('❌ Max reconnection attempts reached');
        }
    }

    sendMessage(agent, message, customerId, sessionId) {
        if (!this.connected) {
            console.error('❌ WebSocket not connected');
            return Promise.reject(new Error('WebSocket not connected'));
        }

        const payload = {
            action: 'sendMessage',
            agent: agent,
            message: message,
            customer_id: customerId,
            session_id: sessionId
        };

        console.log('📤 Sending message:', payload);
        this.ws.send(JSON.stringify(payload));

        return Promise.resolve();
    }

    handleMessage(data) {
        // Notify all registered handlers
        this.messageHandlers.forEach(handler => {
            try {
                handler(data);
            } catch (error) {
                console.error('❌ Error in message handler:', error);
            }
        });
    }

    onMessage(handler) {
        this.messageHandlers.push(handler);
    }

    disconnect() {
        if (this.ws) {
            console.log('🔌 Disconnecting WebSocket');
            this.ws.close();
            this.ws = null;
            this.connected = false;
        }
    }

    isConnected() {
        return this.connected;
    }
}

// Global WebSocket client instance
window.wsClient = null;

// Initialize WebSocket client
async function initializeWebSocket() {
    const wsUrl = window.PETSTORE_CONFIG?.WEBSOCKET_URL || window.CONFIG?.WEBSOCKET_URL;
    
    if (!wsUrl) {
        console.error('❌ WebSocket URL not configured');
        return null;
    }

    try {
        window.wsClient = new WebSocketClient(wsUrl);
        await window.wsClient.connect();
        console.log('✅ WebSocket client initialized');
        return window.wsClient;
    } catch (error) {
        console.error('❌ Failed to initialize WebSocket:', error);
        return null;
    }
}

// Auto-initialize on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeWebSocket);
} else {
    initializeWebSocket();
}
