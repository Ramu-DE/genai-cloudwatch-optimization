// Configuration loaded from config.js
// Ensure config.js is included before this file


// AgentCore API Client
class AgentCoreAPI {
    constructor() {
        // Replace with your actual API Gateway endpoint
        this.apiEndpoint = window.PETSTORE_CONFIG?.API_ENDPOINT || window.CONFIG?.AGENTS_ENDPOINT;
        this.agents = ['bella', 'oliver', 'luna', 'max'];
    }
    
    async invokeAgent(agentName, message, sessionId = null) {
        if (!this.agents.includes(agentName)) {
            throw new Error(`Invalid agent: ${agentName}`);
        }
        
        const url = `${this.apiEndpoint}/agent/${agentName}`;
        const payload = {
            message: message,
            session_id: sessionId || `session-${Date.now()}`
        };
        
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload)
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP ${response.status}`);
            }
            
            const result = await response.json();
            return result;
            
        } catch (error) {
            console.error('AgentCore API error:', error);
            throw error;
        }
    }
    
    // Test connection
    async testConnection() {
        try {
            const result = await this.invokeAgent('bella', 'Hello, this is a test message');
            return { success: true, result };
        } catch (error) {
            return { success: false, error: error.message };
        }
    }
}

// Global instance
window.agentCoreAPI = new AgentCoreAPI();
