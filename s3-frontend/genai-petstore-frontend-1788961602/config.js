
// Auto-generated configuration - Updated by post_deployment_config_update.py
// =============================================================================
// CONFIGURATION BOUNDARIES - DO NOT MIX ACROSS USE CASES
// =============================================================================

// -----------------------------------------------------------------------------
// 1. NORMAL OPERATIONS CONFIG (customer.html, auth.html)
// Purpose: Customer agent conversations, authentication, appointments
// API Gateway: Main REST + WebSocket for normal operations
// Lambda: websocket-lambda, agent-lambda, auth-lambda
// -----------------------------------------------------------------------------
window.NORMAL_OPERATIONS_CONFIG = {
    API_BASE_URL: 'https://ifgodmr2u6.execute-api.us-west-2.amazonaws.com/prod',
    AUTH_ENDPOINT: 'https://ifgodmr2u6.execute-api.us-west-2.amazonaws.com/prod/auth',
    AGENTS_ENDPOINT: 'https://ifgodmr2u6.execute-api.us-west-2.amazonaws.com/prod/agents',
    WEBSOCKET_URL: 'wss://m9l2tzo45a.execute-api.us-west-2.amazonaws.com/prod',
    
    AGENT_ARNS: {
        luna: 'arn:aws:bedrock-agentcore:us-west-2:438327931823:runtime/genai_petstore_luna_nutrition_agent-KR72xTHy6A',
        bella: 'arn:aws:bedrock-agentcore:us-west-2:438327931823:runtime/genai_petstore_bella_grooming_agent-FsKTLB4zQe'
    },
    
    MAX_FARGATE_URL: 'https://69sv2qhm96.execute-api.us-west-2.amazonaws.com/prod/invoke',
    
    REGION: 'us-west-2',
    USE_CASE: 'NORMAL_OPERATIONS'
};

// -----------------------------------------------------------------------------
// 2. LOAD TESTING CONFIG (loadtest-ws.html, loadtest.html)
// Purpose: Agent performance testing, load generation
// API Gateway: Separate Load Test REST + WebSocket
// Lambda: load-tester-lambda/websocket_handler.py
// -----------------------------------------------------------------------------
window.LOAD_TESTING_CONFIG = {
    WEBSOCKET_URL: 'wss://8qtkidezia.execute-api.us-west-2.amazonaws.com/prod',
    REST_API_URL: '',
    REGION: 'us-west-2',
    USE_CASE: 'LOAD_TESTING'
};

// -----------------------------------------------------------------------------
// 3. OPTIMIZATION CONFIG (performance-tuning-compare.html)
// Purpose: Fault injection, performance comparison
// API Gateway: Separate Optimization REST + WebSocket
// Lambda: agent_optimization/websocket_handler.py
// -----------------------------------------------------------------------------
window.OPTIMIZATION_CONFIG = {
    WEBSOCKET_URL: 'wss://[OPTIMIZATION_WEBSOCKET_URL]',
    REST_API_URL: 'https://cwl1xrric5.execute-api.us-west-2.amazonaws.com/prod',
    REGION: 'us-west-2',
    USE_CASE: 'OPTIMIZATION'
};

// -----------------------------------------------------------------------------
// LEGACY COMPATIBILITY
// -----------------------------------------------------------------------------
window.CONFIG = {
    ...window.NORMAL_OPERATIONS_CONFIG,
    APP_NAME: 'GenAI Pet Store',
    VERSION: '1.0.0',
    DEPLOYMENT_ID: 'genai_petstore',
    CLOUDFRONT_URL: 'https://dlxg3syfg1279.cloudfront.net',
    DEBUG: false,
    LOG_LEVEL: 'info',
    LOADTEST_WEBSOCKET_URL: window.LOAD_TESTING_CONFIG.WEBSOCKET_URL,
    LOADTEST_API_URL: window.LOAD_TESTING_CONFIG.REST_API_URL,
    OPTIMIZATION_WEBSOCKET_URL: window.OPTIMIZATION_CONFIG.WEBSOCKET_URL,
    OPTIMIZATION_API_URL: window.OPTIMIZATION_CONFIG.REST_API_URL
};

window.PETSTORE_CONFIG = {
    ...window.CONFIG,
    API_ENDPOINT: window.CONFIG.AGENTS_ENDPOINT
};

// Config boundary verification
window.verifyConfigBoundaries = function(useCase, configUsed) {
    const validMappings = {
        'customer.html': 'NORMAL_OPERATIONS',
        'auth.html': 'NORMAL_OPERATIONS',
        'loadtest-ws.html': 'LOAD_TESTING',
        'loadtest.html': 'LOAD_TESTING',
        'performance-tuning-compare.html': 'OPTIMIZATION'
    };
    const currentPage = window.location.pathname.split('/').pop();
    const expectedUseCase = validMappings[currentPage];
    if (expectedUseCase && useCase !== expectedUseCase) {
        console.error('❌ CONFIG BOUNDARY VIOLATION!');
        console.error('   Page:', currentPage, 'Expected:', expectedUseCase, 'Actual:', useCase);
        return false;
    }
    console.log('✅ Config boundary verified:', {page: currentPage, useCase: useCase});
    return true;
};

console.log('='.repeat(60));
console.log('GenAI Pet Store Configuration Loaded');
console.log('='.repeat(60));
console.log('1. Normal Operations:', {WEBSOCKET: window.NORMAL_OPERATIONS_CONFIG.WEBSOCKET_URL});
console.log('2. Load Testing:', {WEBSOCKET: window.LOAD_TESTING_CONFIG.WEBSOCKET_URL});
console.log('3. Optimization:', {WEBSOCKET: window.OPTIMIZATION_CONFIG.WEBSOCKET_URL});
console.log('Updated:', new Date().toISOString());
console.log('='.repeat(60));
