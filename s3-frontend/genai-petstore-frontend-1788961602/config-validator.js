/**
 * Configuration Boundary Validator
 * Ensures each use case uses the correct configuration
 */

class ConfigValidator {
    constructor() {
        this.useCaseMapping = {
            'customer.html': {
                useCase: 'NORMAL_OPERATIONS',
                config: 'NORMAL_OPERATIONS_CONFIG',
                requiredFields: ['WEBSOCKET_URL', 'AGENTS_ENDPOINT', 'AUTH_ENDPOINT']
            },
            'auth.html': {
                useCase: 'NORMAL_OPERATIONS',
                config: 'NORMAL_OPERATIONS_CONFIG',
                requiredFields: ['AUTH_ENDPOINT', 'API_BASE_URL']
            },
            'loadtest-ws.html': {
                useCase: 'LOAD_TESTING',
                config: 'LOAD_TESTING_CONFIG',
                requiredFields: ['WEBSOCKET_URL']
            },
            'loadtest.html': {
                useCase: 'LOAD_TESTING',
                config: 'LOAD_TESTING_CONFIG',
                requiredFields: ['REST_API_URL']
            },
            'performance-tuning-compare.html': {
                useCase: 'OPTIMIZATION',
                config: 'OPTIMIZATION_CONFIG',
                requiredFields: ['WEBSOCKET_URL']
            }
        };
    }

    getCurrentPage() {
        return window.location.pathname.split('/').pop() || 'index.html';
    }

    getExpectedConfig() {
        const page = this.getCurrentPage();
        return this.useCaseMapping[page];
    }

    validateConfig(configName) {
        const page = this.getCurrentPage();
        const expected = this.useCaseMapping[page];

        if (!expected) {
            console.warn(`⚠️  No validation rules for page: ${page}`);
            return true;
        }

        // Check if correct config is being used
        if (configName !== expected.config) {
            console.error('❌ CONFIG BOUNDARY VIOLATION!');
            console.error(`   Page: ${page}`);
            console.error(`   Expected Config: ${expected.config}`);
            console.error(`   Actual Config: ${configName}`);
            console.error('   ⚠️  This will cause incorrect API calls!');
            
            // Show helpful message
            console.error(`\n   💡 Fix: Use window.${expected.config} instead`);
            return false;
        }

        // Verify required fields exist
        const config = window[configName];
        const missingFields = expected.requiredFields.filter(field => !config[field]);

        if (missingFields.length > 0) {
            console.error('❌ CONFIG INCOMPLETE!');
            console.error(`   Missing fields: ${missingFields.join(', ')}`);
            return false;
        }

        console.log('✅ Configuration validated successfully');
        console.log(`   Page: ${page}`);
        console.log(`   Use Case: ${expected.useCase}`);
        console.log(`   Config: ${configName}`);
        
        return true;
    }

    getConfig() {
        const expected = this.getExpectedConfig();
        if (!expected) {
            console.warn(`⚠️  No config mapping for current page, using default`);
            return window.CONFIG;
        }

        const config = window[expected.config];
        
        if (!config) {
            console.error(`❌ Config not found: ${expected.config}`);
            return null;
        }

        // Validate before returning
        this.validateConfig(expected.config);
        
        return config;
    }

    // Helper method to verify WebSocket URL is correct
    verifyWebSocketURL(wsUrl) {
        const expected = this.getExpectedConfig();
        if (!expected) return true;

        const config = window[expected.config];
        const expectedUrl = config.WEBSOCKET_URL;

        if (wsUrl !== expectedUrl) {
            console.error('❌ WEBSOCKET URL MISMATCH!');
            console.error(`   Expected: ${expectedUrl}`);
            console.error(`   Actual: ${wsUrl}`);
            console.error(`   Use Case: ${expected.useCase}`);
            return false;
        }

        console.log('✅ WebSocket URL verified:', wsUrl);
        return true;
    }

    // Helper method to verify API endpoint is correct
    verifyAPIEndpoint(apiUrl) {
        const expected = this.getExpectedConfig();
        if (!expected) return true;

        const config = window[expected.config];
        const page = this.getCurrentPage();

        let expectedUrl;
        if (page === 'customer.html') {
            expectedUrl = config.AGENTS_ENDPOINT;
        } else if (page === 'auth.html') {
            expectedUrl = config.AUTH_ENDPOINT;
        } else if (page.includes('loadtest')) {
            expectedUrl = config.REST_API_URL || config.WEBSOCKET_URL;
        }

        if (expectedUrl && apiUrl !== expectedUrl) {
            console.error('❌ API ENDPOINT MISMATCH!');
            console.error(`   Expected: ${expectedUrl}`);
            console.error(`   Actual: ${apiUrl}`);
            return false;
        }

        console.log('✅ API endpoint verified:', apiUrl);
        return true;
    }

    // Display configuration summary
    showConfigSummary() {
        const expected = this.getExpectedConfig();
        if (!expected) return;

        const config = window[expected.config];

        console.log('\n' + '='.repeat(60));
        console.log('CONFIGURATION SUMMARY');
        console.log('='.repeat(60));
        console.log(`Page: ${this.getCurrentPage()}`);
        console.log(`Use Case: ${expected.useCase}`);
        console.log(`Config Object: window.${expected.config}`);
        console.log('\nEndpoints:');
        
        Object.keys(config).forEach(key => {
            if (key.includes('URL') || key.includes('ENDPOINT')) {
                console.log(`  ${key}: ${config[key]}`);
            }
        });
        
        console.log('='.repeat(60) + '\n');
    }
}

// Create global validator instance
window.configValidator = new ConfigValidator();

// Auto-validate on load
document.addEventListener('DOMContentLoaded', () => {
    window.configValidator.showConfigSummary();
});
