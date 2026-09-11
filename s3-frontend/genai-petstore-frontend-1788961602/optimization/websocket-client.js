/**
 * WebSocket Client for Agent Optimization Dashboard
 * Handles real-time communication with WebSocket API Gateway
 */

class OptimizationWebSocketClient {
    constructor(websocketUrl) {
        this.websocketUrl = websocketUrl;
        this.ws = null;
        this.messageHandlers = {};
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
    }

    connect() {
        return new Promise((resolve, reject) => {
            console.log('🔌 Connecting to WebSocket:', this.websocketUrl);
            
            this.ws = new WebSocket(this.websocketUrl);
            
            this.ws.onopen = () => {
                console.log('✅ WebSocket connected');
                this.reconnectAttempts = 0;
                resolve();
            };
            
            this.ws.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    console.log('📨 Received message:', message.type);
                    
                    // Call registered handler for this message type
                    const handler = this.messageHandlers[message.type];
                    if (handler) {
                        handler(message);
                    }
                } catch (error) {
                    console.error('❌ Error parsing message:', error);
                }
            };
            
            this.ws.onerror = (error) => {
                console.error('❌ WebSocket error:', error);
                reject(error);
            };
            
            this.ws.onclose = () => {
                console.log('🔌 WebSocket disconnected');
                this.handleReconnect();
            };
        });
    }

    handleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
            
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

    on(messageType, handler) {
        this.messageHandlers[messageType] = handler;
    }

    send(action, data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            const message = {
                action: action,
                ...data
            };
            
            console.log('📤 Sending message:', action);
            this.ws.send(JSON.stringify(message));
        } else {
            console.error('❌ WebSocket not connected');
            throw new Error('WebSocket not connected');
        }
    }

    executeScenario(scenarioId, prompt, customerId) {
        return new Promise((resolve, reject) => {
            let result = null;
            
            // Set up message handlers
            this.on('acknowledgment', (message) => {
                console.log('✅ Acknowledgment:', message.message);
            });
            
            this.on('progress', (message) => {
                console.log('⏳ Progress:', message.message);
            });
            
            this.on('complete', (message) => {
                console.log('✅ Execution complete');
                result = message.data;
                resolve(result);
            });
            
            this.on('error', (message) => {
                console.error('❌ Execution error:', message.message);
                reject(new Error(message.message));
            });
            
            // Send execution request
            this.send('executeScenario', {
                scenario_id: scenarioId,
                prompt: prompt,
                customer_id: customerId
            });
        });
    }

    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}

// Export for use in performance-tuning.js
window.OptimizationWebSocketClient = OptimizationWebSocketClient;
