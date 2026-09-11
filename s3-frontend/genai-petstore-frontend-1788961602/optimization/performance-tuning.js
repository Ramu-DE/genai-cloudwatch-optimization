// Performance Tuning Dashboard - Main JavaScript

// Configuration
const POLLING_INTERVAL = 2000; // 2 second polling interval
const MAX_HISTORY_ITEMS = 10;

// Scenario data will be loaded from scenarios.json
let scenariosData = [];
let currentExecution = null;

// ===== X-RAY TRACE PROPAGATION =====
// Generate X-Ray trace ID for distributed tracing
function generateXRayTraceId() {
    const timestamp = Math.floor(Date.now() / 1000).toString(16);
    const randomHex = Array.from({length: 24}, () => 
        Math.floor(Math.random() * 16).toString(16)
    ).join('');
    return `1-${timestamp}-${randomHex}`;
}

// Generate span ID for trace propagation
function generateSpanId() {
    return Array.from({length: 16}, () => 
        Math.floor(Math.random() * 16).toString(16)
    ).join('');
}

// Initialize dashboard on page load
document.addEventListener('DOMContentLoaded', async () => {
    await loadScenarios();
    initializeEventListeners();
    loadExecutionHistory();
});

// Load scenarios from configuration
async function loadScenarios() {
    try {
        console.log('Loading scenarios from:', CONFIG.OPTIMIZATION_API_URL);
        
        // Fetch scenarios from the backend API
        const response = await fetch(`${CONFIG.OPTIMIZATION_API_URL}/scenarios`);
        console.log('Scenarios response status:', response.status);
        
        if (!response.ok) {
            throw new Error(`Failed to load scenarios: ${response.status}`);
        }
        const data = await response.json();
        console.log('Loaded scenarios:', data.scenarios?.length || 0);
        
        scenariosData = data.scenarios || [];
        populateScenarioDropdown();
        
        console.log('✅ Successfully loaded', scenariosData.length, 'scenarios');
    } catch (error) {
        console.error('❌ Error loading scenarios:', error);
        console.error('Falling back to minimal scenario list');
        
        // Fallback: create minimal scenario list
        scenariosData = [
            { id: 1, name: 'Optimized Base Case', type: 'baseline', description: 'Baseline scenario' },
            { id: 10, name: 'DynamoDB Latency Spike', type: 'fault_injection', description: 'Database latency test' }
        ];
        populateScenarioDropdown();
    }
}

// Populate scenario dropdown - Only show fault_injection and optimization scenarios
function populateScenarioDropdown() {
    const select = document.getElementById('scenarioSelect');
    select.innerHTML = '<option value="">-- Choose a fault scenario --</option>';
    
    // Filter out baseline scenarios - they run automatically
    const testableScenarios = scenariosData.filter(s => s.type !== 'baseline');
    
    // Renumber sequentially for better UX (1, 2, 3, 4...)
    testableScenarios.forEach((scenario, index) => {
        const option = document.createElement('option');
        option.value = scenario.id;  // Keep original ID for API calls
        option.textContent = `${index + 1}. ${scenario.name}`;  // Display sequential number
        option.dataset.scenario = JSON.stringify(scenario);
        select.appendChild(option);
    });
}

// Initialize event listeners
function initializeEventListeners() {
    // Scenario selection
    document.getElementById('scenarioSelect').addEventListener('change', handleScenarioSelection);
    
    // Run scenario button
    document.getElementById('runScenarioBtn').addEventListener('click', handleRunScenario);
    
    // Clear history button
    document.getElementById('clearHistoryBtn').addEventListener('click', handleClearHistory);
    
    // Export buttons
    document.getElementById('exportJsonBtn').addEventListener('click', handleExportJson);
    document.getElementById('generateReportBtn').addEventListener('click', handleGenerateReport);
    
    // History table sorting
    document.querySelectorAll('.history-table th.sortable').forEach(th => {
        th.addEventListener('click', () => handleSort(th.dataset.sort));
    });
}

// Handle scenario selection
function handleScenarioSelection(event) {
    const select = event.target;
    const selectedOption = select.options[select.selectedIndex];
    
    if (!selectedOption.dataset.scenario) {
        document.getElementById('scenarioDescription').classList.add('hidden');
        document.getElementById('runScenarioBtn').disabled = true;
        return;
    }
    
    const scenario = JSON.parse(selectedOption.dataset.scenario);
    displayScenarioDescription(scenario);
    document.getElementById('runScenarioBtn').disabled = false;
}

// Display scenario description with educational content first
function displayScenarioDescription(scenario) {
    const descSection = document.getElementById('scenarioDescription');
    const nameEl = document.getElementById('scenarioName');
    
    // Get scenario details for educational content
    const scenarioInfo = getScenarioDetails(scenario);
    
    // Set title
    nameEl.textContent = `Scenario ${scenario.id}: ${scenario.name}`;
    
    // Populate educational content (shown first)
    document.getElementById('scenarioExplanation').textContent = scenarioInfo.explanation;
    document.getElementById('whyMatters').textContent = scenarioInfo.whyMatters;
    document.getElementById('architecturalInsight').textContent = scenarioInfo.architecturalInsight;
    document.getElementById('keyTakeaway').textContent = scenarioInfo.keyTakeaway;
    document.getElementById('faultMechanism').textContent = scenarioInfo.faultMechanism;
    
    // Display expected impact
    const impactList = document.getElementById('expectedImpactList');
    impactList.innerHTML = '';
    if (scenario.expected_impact) {
        Object.entries(scenario.expected_impact).forEach(([key, value]) => {
            const li = document.createElement('li');
            li.textContent = `${key.replace('_', ' ')}: ${value}`;
            impactList.appendChild(li);
        });
    }
    
    descSection.classList.remove('hidden');
}

// Handle run scenario
async function handleRunScenario() {
    const scenarioId = document.getElementById('scenarioSelect').value;
    const userPrompt = document.getElementById('userPrompt').value;
    
    if (!scenarioId || !userPrompt) {
        alert('Please select a scenario and enter a prompt');
        return;
    }
    
    const scenario = scenariosData.find(s => s.id == scenarioId);
    if (!scenario) return;
    
    // Disable button during execution
    const runBtn = document.getElementById('runScenarioBtn');
    runBtn.disabled = true;
    runBtn.textContent = 'Running...';
    
    // Show execution panels and hide scenario description
    document.getElementById('executionPanelsSection').classList.remove('hidden');
    document.getElementById('scenarioDescription').classList.add('hidden');
    
    // Reset panels
    resetExecutionPanels();
    
    // Show progress indicators
    showProgressIndicators();
    
    // Create execution context
    currentExecution = {
        scenarioId: scenarioId,
        scenario: scenario,
        userPrompt: userPrompt,
        startTime: Date.now(),
        faultResult: null,
        baselineResult: null
    };
    
    // Start parallel execution
    try {
        await executeParallelScenarios(scenarioId, userPrompt);
    } catch (error) {
        console.error('Execution error:', error);
        
        // Determine error type and handle appropriately
        const errorType = error.errorType || 'unknown';
        const partialData = error.partialData || null;
        
        // Display error for both panels if both failed
        if (!error.faultSuccess) {
            displayError('fault', error.message, errorType, partialData?.fault);
        }
        if (!error.baselineSuccess) {
            displayError('baseline', error.message, errorType, partialData?.baseline);
        }
        
        // If one succeeded, show comparison with partial data
        if (error.faultSuccess || error.baselineSuccess) {
            displayPartialComparison(error.faultResult, error.baselineResult);
        }
    } finally {
        runBtn.disabled = false;
        runBtn.textContent = 'Run Scenario';
    }
}

// Global WebSocket client
let wsClient = null;

// Initialize WebSocket connection
async function initializeWebSocket() {
    if (wsClient && wsClient.ws && wsClient.ws.readyState === WebSocket.OPEN) {
        return wsClient; // Already connected
    }
    
    console.log('🔌 Initializing WebSocket connection...');
    wsClient = new OptimizationWebSocketClient(CONFIG.WEBSOCKET_URL);
    await wsClient.connect();
    console.log('✅ WebSocket connected');
    return wsClient;
}

// Execute parallel scenarios using WebSocket
async function executeParallelScenarios(scenarioId, userPrompt) {
    const startTime = Date.now();
    
    // Update status for both panels
    updateStatus('fault', 'running', 'Executing...');
    updateStatus('baseline', 'running', 'Executing...');
    
    // Start elapsed time counters
    const faultTimerInterval = startElapsedTimer('fault', startTime);
    const baselineTimerInterval = startElapsedTimer('baseline', startTime);
    
    try {
        // Connect WebSocket if not already connected
        await initializeWebSocket();
        
        console.log('📤 Sending scenario execution request via WebSocket...');
        
        // Execute via WebSocket (no timeout limits!)
        const result = await wsClient.executeScenario(
            parseInt(scenarioId),
            userPrompt,
            'cust_matthewnguyen22'  // Use proper customer ID for testing
        );
        
        console.log('✅ Received execution result');
        
        // Stop timers
        clearInterval(faultTimerInterval);
        clearInterval(baselineTimerInterval);
        
        // Process WebSocket result (same format as REST API)
        const data = result;
        
        // Transform API response to match expected format
        const faultResult = {
            type: 'fault',
            scenarioId: scenarioId,
            response: data.fault_result?.response || 'No response available',
            metrics: data.fault_result?.metrics || {},
            activity: data.fault_result?.activity || []
        };
        
        const baselineResult = {
            type: 'baseline',
            scenarioId: data.baseline_result?.scenario_id || 1,
            response: data.baseline_result?.response || 'No response available',
            metrics: data.baseline_result?.metrics || {},
            activity: data.baseline_result?.activity || []
        };
        
        // Store results
        currentExecution.faultResult = faultResult;
        currentExecution.baselineResult = baselineResult;
        currentExecution.endTime = Date.now();
        currentExecution.comparison = data.comparison;
        currentExecution.rootCauseAnalysis = data.root_cause_analysis;
        
        // Update status
        updateStatus('fault', 'completed', 'Completed');
        updateStatus('baseline', 'completed', 'Completed');
        
        // Display results
        displayExecutionResults(faultResult, baselineResult);
        displayResponse('fault', faultResult.response);
        displayResponse('baseline', baselineResult.response);
        displayActivityLog('fault', faultResult.activity);
        displayActivityLog('baseline', baselineResult.activity);
        
        // Calculate and display comparison
        displayMetricsComparison(faultResult, baselineResult);
        
        // Display root cause analysis
        const scenario = scenariosData.find(s => s.id === parseInt(scenarioId));
        if (scenario) {
            displayRootCauseAnalysis(faultResult, baselineResult, scenario);
        } else {
            console.warn('Scenario not found for ID:', scenarioId, 'Available scenarios:', scenariosData.map(s => s.id));
        }
        
        // Add to history
        addToExecutionHistory(currentExecution);
        
        // Enable export buttons
        document.getElementById('exportJsonBtn').disabled = false;
        document.getElementById('generateReportBtn').disabled = false;
        
    } catch (error) {
        clearInterval(faultTimerInterval);
        clearInterval(baselineTimerInterval);
        updateStatus('fault', 'error', 'Error');
        updateStatus('baseline', 'error', 'Error');
        throw error;
    }
}

// Poll for execution results
async function pollForResults(executionId, timeout = 120000) {
    const startTime = Date.now();
    const maxAttempts = Math.floor(timeout / POLLING_INTERVAL);
    let attempts = 0;
    
    while (attempts < maxAttempts) {
        try {
            const response = await fetch(`${CONFIG.OPTIMIZATION_API_URL}/results/${executionId}`);
            
            if (!response.ok) {
                if (response.status === 404) {
                    // Not ready yet, continue polling
                    attempts++;
                    await sleep(POLLING_INTERVAL);
                    continue;
                }
                throw new Error(`Failed to fetch results: ${response.status}`);
            }
            
            const data = await response.json();
            
            // Check if execution is complete
            if (data.status === 'completed') {
                return data;
            } else if (data.status === 'failed') {
                throw new Error(data.error || 'Execution failed');
            } else if (data.status === 'running' || data.status === 'pending') {
                // Still running, continue polling
                attempts++;
                await sleep(POLLING_INTERVAL);
                continue;
            }
            
        } catch (error) {
            if (error.message.includes('Failed to fetch results')) {
                throw error;
            }
            // Network error or other issue, retry
            attempts++;
            await sleep(POLLING_INTERVAL);
        }
    }
    
    throw new Error('Execution timeout - results not available within timeout period');
}

// Helper function for delays
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Note: executeScenario and simulateScenarioExecution functions removed
// Now using /parallel endpoint directly in executeParallelScenarios()

// Reset execution panels
function resetExecutionPanels() {
    ['fault', 'baseline'].forEach(type => {
        document.getElementById(`${type}Progress`).classList.add('hidden');
        document.getElementById(`${type}Response`).classList.add('hidden');
        document.getElementById(`${type}Activity`).classList.add('hidden');
        updateStatus(type, 'ready', 'Ready');
    });
    
    document.getElementById('metricsSection').classList.add('hidden');
    document.getElementById('rootCauseSection').classList.add('hidden');
}

// Show progress indicators
function showProgressIndicators() {
    ['fault', 'baseline'].forEach(type => {
        document.getElementById(`${type}Progress`).classList.remove('hidden');
    });
}

// Update status badge and text
function updateStatus(type, status, text) {
    const badge = document.getElementById(`${type}Status`);
    const statusText = document.getElementById(`${type}StatusText`);
    
    badge.className = `status-badge ${status}`;
    badge.textContent = status.charAt(0).toUpperCase() + status.slice(1);
    
    if (statusText) {
        statusText.textContent = text;
    }
}

// Start elapsed time counter
function startElapsedTimer(type, startTime) {
    const elapsedEl = document.getElementById(`${type}Elapsed`);
    
    return setInterval(() => {
        const elapsed = (Date.now() - startTime) / 1000;
        elapsedEl.textContent = `${elapsed.toFixed(1)}s`;
    }, 100);
}

// Display response
function displayResponse(type, response) {
    const container = document.getElementById(`${type}Response`);
    const textEl = container.querySelector('.response-text');
    
    // Debug: Log the raw response
    console.log(`📝 Raw ${type} response:`, response);
    console.log(`📝 Response type:`, typeof response);
    console.log(`📝 First 100 chars:`, response?.substring(0, 100));
    
    // Format response with proper line breaks and HTML formatting
    const formatted = window.formatResponseText(response);
    console.log(`✨ Formatted ${type} response (first 200 chars):`, formatted?.substring(0, 200));
    
    textEl.innerHTML = formatted;
    container.classList.remove('hidden');
    
    // Hide progress indicator
    document.getElementById(`${type}Progress`).classList.add('hidden');
}

// Display activity log
function displayActivityLog(type, activities) {
    const container = document.getElementById(`${type}Activity`);
    const listEl = container.querySelector('.activity-list');
    
    listEl.innerHTML = '';
    activities.forEach(activity => {
        const li = document.createElement('li');
        const time = new Date(activity.timestamp).toLocaleTimeString();
        li.textContent = `[${time}] ${activity.message}`;
        listEl.appendChild(li);
    });
    
    container.classList.remove('hidden');
}

// Display error with enhanced categorization
function displayError(type, message, errorType = 'unknown', partialData = null) {
    const container = document.getElementById(`${type}Response`);
    const textEl = container.querySelector('.response-text');
    
    // Categorize error and provide user-friendly message
    const errorInfo = categorizeError(errorType, message);
    
    let errorHtml = `
        <div class="error-container">
            <div class="error-header">
                <span class="error-icon">${errorInfo.icon}</span>
                <span class="error-title">${errorInfo.title}</span>
            </div>
            <div class="error-message">${errorInfo.userMessage}</div>
    `;
    
    // Show partial results if available
    if (partialData) {
        errorHtml += `
            <div class="partial-results">
                <h4>Partial Results Available:</h4>
                <p>${partialData.message || 'Some data was collected before the error occurred.'}</p>
                ${partialData.metrics ? displayPartialMetrics(partialData.metrics) : ''}
            </div>
        `;
    }
    
    // Add technical details (collapsible)
    errorHtml += `
            <details class="error-details">
                <summary>Technical Details</summary>
                <pre>${message}</pre>
            </details>
        </div>
    `;
    
    textEl.innerHTML = errorHtml;
    container.classList.remove('hidden');
    
    document.getElementById(`${type}Progress`).classList.add('hidden');
}

// Categorize error and provide user-friendly information
function categorizeError(errorType, message) {
    const errorCategories = {
        'timeout': {
            icon: '⏱️',
            title: 'Request Timeout',
            userMessage: 'The scenario execution took too long and timed out. This may be due to high latency in the fault injection scenario. Try reducing the complexity or increasing timeout limits.'
        },
        'tool_failure': {
            icon: '🔧',
            title: 'Tool Execution Failed',
            userMessage: 'A tool invocation failed during execution. This is expected behavior for fault injection scenarios testing error handling. Check the activity log for details.'
        },
        'token_limit': {
            icon: '📊',
            title: 'Token Limit Exceeded',
            userMessage: 'The request exceeded the maximum token limit. This demonstrates the impact of context bloat. Consider implementing token budgets or context pruning.'
        },
        'llm_error': {
            icon: '🤖',
            title: 'LLM Service Error',
            userMessage: 'The language model service encountered an error. This may be due to rate limiting, throttling, or service unavailability. Retry logic should handle this automatically.'
        },
        'memory_error': {
            icon: '💾',
            title: 'Memory Service Error',
            userMessage: 'The AgentCore Memory service is unavailable or returned an error. The agent should gracefully degrade to cached responses or simplified functionality.'
        },
        'database_error': {
            icon: '🗄️',
            title: 'Database Error',
            userMessage: 'Failed to query the database. This may be due to connection issues, latency injection, or data unavailability. Check database connectivity and retry logic.'
        },
        'network_error': {
            icon: '🌐',
            title: 'Network Error',
            userMessage: 'A network error occurred while communicating with backend services. Check your connection and try again.'
        },
        'fault_injection': {
            icon: '⚠️',
            title: 'Fault Injection Active',
            userMessage: 'This error is intentionally injected as part of the fault injection scenario. It demonstrates how the system behaves under adverse conditions.'
        },
        'unknown': {
            icon: '❌',
            title: 'Unexpected Error',
            userMessage: 'An unexpected error occurred. Please check the technical details below and try again.'
        }
    };
    
    // Try to auto-detect error type from message if not provided
    if (errorType === 'unknown') {
        const messageLower = message.toLowerCase();
        if (messageLower.includes('timeout') || messageLower.includes('timed out')) {
            errorType = 'timeout';
        } else if (messageLower.includes('token') || messageLower.includes('context length')) {
            errorType = 'token_limit';
        } else if (messageLower.includes('tool') || messageLower.includes('function')) {
            errorType = 'tool_failure';
        } else if (messageLower.includes('bedrock') || messageLower.includes('model') || messageLower.includes('throttl')) {
            errorType = 'llm_error';
        } else if (messageLower.includes('memory')) {
            errorType = 'memory_error';
        } else if (messageLower.includes('database') || messageLower.includes('dynamodb')) {
            errorType = 'database_error';
        } else if (messageLower.includes('network') || messageLower.includes('connection')) {
            errorType = 'network_error';
        }
    }
    
    return errorCategories[errorType] || errorCategories['unknown'];
}

// Display partial metrics when available
function displayPartialMetrics(metrics) {
    return `
        <div class="partial-metrics">
            ${metrics.latency_ms ? `<p>Latency: ${metrics.latency_ms.toFixed(0)}ms</p>` : ''}
            ${metrics.input_tokens ? `<p>Input Tokens: ${metrics.input_tokens}</p>` : ''}
            ${metrics.tool_calls ? `<p>Tool Calls: ${metrics.tool_calls}</p>` : ''}
        </div>
    `;
}

// Display execution results
function displayExecutionResults(faultResult, baselineResult) {
    // Results are already displayed via displayResponse
    // This function can be used for additional processing if needed
}

// Display partial comparison when one scenario fails
function displayPartialComparison(faultResult, baselineResult) {
    if (!faultResult && !baselineResult) {
        return; // Both failed, nothing to compare
    }
    
    const section = document.getElementById('metricsSection');
    const tbody = document.getElementById('metricsTableBody');
    
    // Show what we have
    tbody.innerHTML = '';
    
    const successResult = faultResult || baselineResult;
    const failedType = faultResult ? 'baseline' : 'fault';
    
    // Add note about partial results
    const noteRow = tbody.insertRow();
    noteRow.innerHTML = `
        <td colspan="5" style="background-color: var(--warning-bg); color: var(--warning-color); text-align: center; padding: 10px;">
            ⚠️ Partial Results: ${failedType} execution failed. Showing available metrics from successful execution.
        </td>
    `;
    
    // Display available metrics
    if (successResult && successResult.metrics) {
        const metrics = successResult.metrics;
        const metricsToShow = [
            { name: 'Latency', value: `${metrics.latency_ms?.toFixed(0) || 'N/A'}ms`, unit: 'ms' },
            { name: 'Input Tokens', value: metrics.input_tokens || 'N/A', unit: 'tokens' },
            { name: 'Output Tokens', value: metrics.output_tokens || 'N/A', unit: 'tokens' },
            { name: 'Tool Calls', value: metrics.tool_calls || 'N/A', unit: 'calls' },
            { name: 'Estimated Cost', value: `$${metrics.estimated_cost_usd?.toFixed(4) || 'N/A'}`, unit: 'USD' }
        ];
        
        metricsToShow.forEach(metric => {
            const row = tbody.insertRow();
            row.innerHTML = `
                <td>${metric.name}</td>
                <td>${faultResult ? metric.value : 'Failed'}</td>
                <td>${baselineResult ? metric.value : 'Failed'}</td>
                <td>N/A</td>
                <td>N/A</td>
            `;
        });
    }
    
    section.classList.remove('hidden');
    
    // Add explanation in root cause section
    const rootCauseSection = document.getElementById('rootCauseSection');
    const analysisEl = document.getElementById('rootCauseAnalysis');
    
    analysisEl.innerHTML = `
        <div class="partial-results-notice">
            <h4>⚠️ Partial Execution Results</h4>
            <p>The ${failedType} execution failed, preventing full comparison. This may indicate:</p>
            <ul>
                <li>The fault injection scenario caused a critical failure (expected behavior for some scenarios)</li>
                <li>A timeout occurred due to excessive latency</li>
                <li>A service dependency is unavailable</li>
            </ul>
            <p><strong>Recommendation:</strong> Review the error details above and check if this is expected behavior for the selected scenario.</p>
        </div>
    `;
    
    rootCauseSection.classList.remove('hidden');
}

// Display metrics comparison - Card Layout
function displayMetricsComparison(faultResult, baselineResult) {
    const section = document.getElementById('metricsSection');
    
    // Get metrics
    const faultMetrics = faultResult.metrics;
    const baselineMetrics = baselineResult.metrics;
    
    // Latency
    const latencyBaseline = baselineMetrics.latency_ms || 0;
    const latencyFault = faultMetrics.latency_ms || 0;
    const latencyDelta = latencyFault - latencyBaseline;
    const latencyPercent = latencyBaseline !== 0 ? ((latencyDelta / latencyBaseline) * 100).toFixed(1) : 0;
    
    document.getElementById('latencyBaseline').textContent = `${latencyBaseline.toFixed(0)}ms`;
    document.getElementById('latencyFault').textContent = `${latencyFault.toFixed(0)}ms`;
    document.getElementById('latencyDelta').textContent = `${latencyDelta > 0 ? '+' : ''}${latencyDelta.toFixed(0)}ms (${latencyPercent > 0 ? '+' : ''}${latencyPercent}%)`;
    document.getElementById('latencyDelta').parentElement.className = `metric-delta ${latencyDelta > 0 ? 'positive' : latencyDelta < 0 ? 'negative' : 'neutral'}`;
    
    // Tokens
    const tokensBaseline = (baselineMetrics.input_tokens || 0) + (baselineMetrics.output_tokens || 0);
    const tokensFault = (faultMetrics.input_tokens || 0) + (faultMetrics.output_tokens || 0);
    const tokensDelta = tokensFault - tokensBaseline;
    const tokensPercent = tokensBaseline !== 0 ? ((tokensDelta / tokensBaseline) * 100).toFixed(1) : 0;
    
    document.getElementById('tokensBaseline').textContent = tokensBaseline.toFixed(0);
    document.getElementById('tokensFault').textContent = tokensFault.toFixed(0);
    document.getElementById('tokensDelta').textContent = `${tokensDelta > 0 ? '+' : ''}${tokensDelta.toFixed(0)} (${tokensPercent > 0 ? '+' : ''}${tokensPercent}%)`;
    document.getElementById('tokensDelta').parentElement.className = `metric-delta ${tokensDelta > 0 ? 'positive' : tokensDelta < 0 ? 'negative' : 'neutral'}`;
    
    // Cost
    const costBaseline = baselineMetrics.estimated_cost_usd || 0;
    const costFault = faultMetrics.estimated_cost_usd || 0;
    const costDelta = costFault - costBaseline;
    const costPercent = costBaseline !== 0 ? ((costDelta / costBaseline) * 100).toFixed(1) : 0;
    
    document.getElementById('costBaseline').textContent = `$${costBaseline.toFixed(4)}`;
    document.getElementById('costFault').textContent = `$${costFault.toFixed(4)}`;
    document.getElementById('costDelta').textContent = `${costDelta > 0 ? '+' : ''}$${costDelta.toFixed(4)} (${costPercent > 0 ? '+' : ''}${costPercent}%)`;
    document.getElementById('costDelta').parentElement.className = `metric-delta ${costDelta > 0 ? 'positive' : costDelta < 0 ? 'negative' : 'neutral'}`;
    
    // Tool Calls
    const toolsBaseline = baselineMetrics.tool_calls || 0;
    const toolsFault = faultMetrics.tool_calls || 0;
    const toolsDelta = toolsFault - toolsBaseline;
    const toolsPercent = toolsBaseline !== 0 ? ((toolsDelta / toolsBaseline) * 100).toFixed(1) : 0;
    
    document.getElementById('toolsBaseline').textContent = toolsBaseline;
    document.getElementById('toolsFault').textContent = toolsFault;
    document.getElementById('toolsDelta').textContent = `${toolsDelta > 0 ? '+' : ''}${toolsDelta} (${toolsPercent > 0 ? '+' : ''}${toolsPercent}%)`;
    document.getElementById('toolsDelta').parentElement.className = `metric-delta ${toolsDelta > 0 ? 'positive' : toolsDelta < 0 ? 'negative' : 'neutral'}`;
    
    section.classList.remove('hidden');
}

// Get impact indicator emoji
function getImpactIndicator(deltaPercent) {
    if (Math.abs(deltaPercent) < 5) return '🟢';
    if (Math.abs(deltaPercent) < 50) return '🟡';
    if (Math.abs(deltaPercent) < 200) return '🟠';
    return '🔴';
}

// Display root cause analysis
function displayRootCauseAnalysis(faultResult, baselineResult, scenario) {
    const section = document.getElementById('rootCauseSection');
    const content = document.getElementById('rootCauseContent');
    const takeaway = document.getElementById('keyTakeaway');
    const matters = document.getElementById('whyMatters');
    const docsList = document.getElementById('awsDocsList');
    
    // Generate root cause analysis based on scenario type
    const latencyDelta = faultResult.metrics.latency_ms - baselineResult.metrics.latency_ms;
    const tokenDelta = faultResult.metrics.total_tokens - baselineResult.metrics.total_tokens;
    const costDelta = faultResult.metrics.estimated_cost_usd - baselineResult.metrics.estimated_cost_usd;
    const latencyPercent = ((latencyDelta / baselineResult.metrics.latency_ms) * 100).toFixed(0);
    const tokenPercent = ((tokenDelta / baselineResult.metrics.total_tokens) * 100).toFixed(0);
    
    // Get detailed scenario information
    const scenarioInfo = getScenarioDetails(scenario);
    
    content.innerHTML = `
        <div class="root-cause-detailed">
            <div class="scenario-explanation">
                <h4>🔬 What This Scenario Tests</h4>
                <p>${scenarioInfo.explanation}</p>
            </div>
            
            <div class="fault-injection-details">
                <h4>⚙️ Fault Injection Mechanism</h4>
                <p>${scenarioInfo.faultMechanism}</p>
                <div class="technical-details">
                    <strong>Technical Implementation:</strong>
                    <ul>
                        ${scenarioInfo.technicalDetails.map(detail => `<li>${detail}</li>`).join('')}
                    </ul>
                </div>
            </div>
            
            <div class="performance-impact">
                <h4>📊 Performance Impact Analysis</h4>
                <ul>
                    <li><strong>Latency:</strong> +${latencyDelta.toFixed(0)}ms (${latencyPercent}% increase) - ${classifyImpact(latencyPercent, 'latency')}</li>
                    <li><strong>Tokens:</strong> +${tokenDelta} tokens (${tokenPercent}% increase) - ${classifyImpact(tokenPercent, 'tokens')}</li>
                    <li><strong>Cost:</strong> +$${costDelta.toFixed(4)} (${((costDelta/baselineResult.metrics.estimated_cost_usd)*100).toFixed(0)}% increase)</li>
                    <li><strong>Tool Calls:</strong> ${faultResult.metrics.tool_calls} vs ${baselineResult.metrics.tool_calls} baseline</li>
                </ul>
            </div>
            
            <div class="root-cause-explanation">
                <h4>🎯 Root Cause</h4>
                <p>${scenarioInfo.rootCause}</p>
            </div>
            
            <div class="architectural-insight">
                <h4>🏗️ Architectural Insight</h4>
                <p>${scenarioInfo.architecturalInsight}</p>
            </div>
        </div>
    `;
    
    // Educational content
    takeaway.textContent = scenarioInfo.keyTakeaway;
    matters.textContent = scenarioInfo.whyMatters;
    
    // AWS documentation links
    docsList.innerHTML = '';
    const docs = getAwsDocLinks(scenario);
    docs.forEach(doc => {
        const li = document.createElement('li');
        li.innerHTML = `<a href="${doc.url}" target="_blank">${doc.title}</a>`;
        docsList.appendChild(li);
    });
    
    section.classList.remove('hidden');
}

// Classify impact severity
function classifyImpact(percent, type) {
    const absPercent = Math.abs(percent);
    if (type === 'latency') {
        if (absPercent > 300) return '🔴 Critical Impact';
        if (absPercent > 100) return '🟠 High Impact';
        if (absPercent > 50) return '🟡 Moderate Impact';
        return '🟢 Low Impact';
    } else {
        if (absPercent > 200) return '🔴 Critical Impact';
        if (absPercent > 100) return '🟠 High Impact';
        if (absPercent > 50) return '🟡 Moderate Impact';
        return '🟢 Low Impact';
    }
}

// Get detailed scenario information
function getScenarioDetails(scenario) {
    if (!scenario) {
        return {
            explanation: 'Scenario information not available.',
            faultMechanism: 'Unable to load scenario details.',
            technicalDetails: ['Scenario data not found'],
            rootCause: 'Scenario information could not be retrieved.',
            architecturalInsight: 'Please ensure scenarios are loaded correctly.',
            keyTakeaway: 'Check scenario configuration.',
            whyMatters: 'Proper scenario configuration is essential for accurate testing.'
        };
    }
    const scenarioId = scenario.id;
    
    // Detailed information for each scenario
    const scenarioDatabase = {
        2: {
            explanation: 'This scenario tests the impact of context bloat on agent performance. It simulates what happens when you include too much irrelevant information in your prompts, such as dumping entire database records or documents without summarization.',
            faultMechanism: 'The fault injector adds 500 tokens of irrelevant "Lorem ipsum" text to the user prompt before sending it to the agent. This bloat increases both input token count and processing time.',
            technicalDetails: [
                'Appends 100 repetitions of "Lorem ipsum dolor sit amet" to the prompt',
                'Increases input tokens by approximately 500 tokens',
                'Forces the LLM to process unnecessary context',
                'Demonstrates the cost of poor RAG (Retrieval Augmented Generation) implementations'
            ],
            rootCause: 'The token increase is caused by injecting excessive context into the prompt. When you include irrelevant data, the LLM must process all of it, increasing both latency and cost without improving response quality.',
            architecturalInsight: 'This demonstrates why RAG systems must implement smart chunking and relevance filtering. Simply dumping all retrieved documents into the context window is expensive and inefficient. Always pre-process, summarize, and filter retrieved data before including it in prompts.',
            keyTakeaway: 'Only include relevant context in prompts. Pre-process and summarize data before sending to the LLM to minimize token costs. A good RAG system returns focused, relevant information, not raw data dumps.',
            whyMatters: 'Context bloat directly impacts operational costs. At scale, unnecessary tokens can increase your AWS bill by 50-200%. Additionally, excessive context increases latency and may hit token limits, degrading user experience. Smart context management is essential for cost-effective AI applications.'
        },
        10: {
            explanation: 'This scenario tests the impact of slow database queries on agent performance. It simulates what happens when your DynamoDB table has high latency due to throttling, hot partitions, or network issues.',
            faultMechanism: 'The fault injector adds a real 4-second delay (time.sleep(4.0)) before the agent processes the request, simulating a slow database query or external API call.',
            technicalDetails: [
                'Injects a 4000ms delay using time.sleep(4.0)',
                'Simulates DynamoDB throttling or hot partition issues',
                'Demonstrates cascading latency from dependent services',
                'Shows the importance of timeout and retry strategies'
            ],
            rootCause: 'The latency increase is caused by an artificial 4-second delay injected into the database query path. This simulates real-world scenarios like DynamoDB throttling, hot partitions, or network congestion affecting external service calls.',
            architecturalInsight: 'This demonstrates why agent architectures must handle slow dependencies gracefully. Strategies include: implementing caching layers, using connection pooling, setting appropriate timeouts, and designing for graceful degradation when services are slow.',
            keyTakeaway: 'Monitor and optimize external service dependencies. Implement caching, connection pooling, and timeout strategies. Consider using DynamoDB on-demand mode or provisioned capacity with auto-scaling to prevent throttling.',
            whyMatters: 'Database latency directly impacts user experience. A 4-second delay makes your application feel unresponsive and frustrating. At scale, slow queries can cause cascading failures, increased costs from retries, and poor customer satisfaction. Optimizing database performance is critical for production AI agents.'
        },
        4: {
            explanation: 'This scenario tests how agents handle tool failures and implement retry logic. It simulates what happens when a tool call fails due to invalid parameters, service unavailability, or data issues.',
            faultMechanism: 'The fault injector passes an invalid customer_id to the tool, causing it to fail. The agent must detect the error, analyze what went wrong, and retry with corrected parameters.',
            technicalDetails: [
                'Passes invalid customer_id to trigger tool failure',
                'Agent must parse error message and identify the issue',
                'Implements retry logic with corrected parameters',
                'Adds ~2000ms latency from error handling and retry',
                'Increases token usage from error analysis'
            ],
            rootCause: 'The latency increase is caused by tool failure and retry logic. When a tool fails, the agent must: 1) Receive and parse the error, 2) Analyze what went wrong, 3) Formulate a corrected request, 4) Retry the tool call. This multi-step process adds significant overhead.',
            architecturalInsight: 'This demonstrates the importance of robust error handling and clear error messages. Tools should fail fast with actionable error messages. Agents should implement exponential backoff for retries and have clear retry limits to prevent infinite loops.',
            keyTakeaway: 'Design tools to fail fast with clear, actionable error messages. Implement retry logic with exponential backoff and maximum retry limits. Validate inputs before making expensive tool calls.',
            whyMatters: 'Poor error handling leads to wasted resources and poor user experience. Retries consume tokens and add latency. At scale, cascading failures from poor error handling can bring down entire systems. Robust error handling is essential for production reliability.'
        },
        1: {
            explanation: 'This is the baseline scenario representing optimal agent performance. It shows how the agent performs when everything is working correctly with no faults injected.',
            faultMechanism: 'No fault injection is applied. This scenario executes the agent with optimal configuration: efficient prompts, fast database queries, proper error handling, and smart tool orchestration.',
            technicalDetails: [
                'No artificial delays or bloat added',
                'Optimal prompt engineering with minimal context',
                'Efficient tool calls with proper error handling',
                'Represents production-ready agent architecture'
            ],
            rootCause: 'This is the baseline scenario - both sides show the same optimal execution. No fault is injected, so there is no performance degradation to analyze.',
            architecturalInsight: 'This baseline represents best practices: concise prompts, efficient tool design, proper error handling, and fast external service calls. Use this as your target performance when optimizing other scenarios.',
            keyTakeaway: 'This baseline shows what optimal agent performance looks like. Use it as a reference point when comparing fault injection scenarios to understand the impact of architectural decisions.',
            whyMatters: 'Understanding baseline performance is essential for setting SLOs (Service Level Objectives) and identifying performance regressions. This baseline helps you quantify the cost of architectural anti-patterns.'
        }
    };
    
    // Return scenario details or default
    return scenarioDatabase[scenarioId] || {
        explanation: `This scenario tests ${scenario.name} to demonstrate its impact on agent performance.`,
        faultMechanism: 'This scenario applies specific fault injection to simulate real-world performance issues.',
        technicalDetails: ['Fault injection applied based on scenario configuration'],
        rootCause: 'This scenario demonstrates the impact of architectural decisions on agent performance. Optimized implementations can significantly reduce latency and token costs.',
        architecturalInsight: 'Understanding performance trade-offs enables informed architectural decisions for production AI agents.',
        keyTakeaway: 'Optimize agent architecture by measuring and comparing different implementation strategies. Small changes can have significant cost and performance impacts.',
        whyMatters: 'Performance optimization directly impacts user experience and operational costs. Understanding these trade-offs enables informed architectural decisions.'
    };
}

// Note: generateKeyTakeaway and generateWhyMatters functions removed
// Now using getScenarioDetails() which provides comprehensive scenario information

// Get AWS documentation links
function getAwsDocLinks(scenario) {
    const baseLinks = [
        { title: 'Amazon Bedrock Best Practices', url: 'https://docs.aws.amazon.com/bedrock/latest/userguide/best-practices.html' },
        { title: 'Optimizing LLM Performance', url: 'https://docs.aws.amazon.com/bedrock/latest/userguide/performance.html' }
    ];
    
    if (scenario.fault_type === 'latency_injection') {
        baseLinks.push({ title: 'DynamoDB Performance Optimization', url: 'https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html' });
    }
    
    return baseLinks;
}

// Add to execution history
function addToExecutionHistory(execution) {
    // Guard against missing data
    if (!execution || !execution.faultResult || !execution.faultResult.metrics) {
        console.warn('Cannot add to history: missing execution data');
        return;
    }
    
    const history = getExecutionHistory();
    
    const latency = execution.faultResult.metrics.latency_ms || 0;
    const historyItem = {
        timestamp: execution.endTime,
        scenarioId: execution.scenarioId,
        scenarioName: execution.scenario.name,
        latency: latency,
        tokens: execution.faultResult.metrics.total_tokens || 0,
        cost: execution.faultResult.metrics.estimated_cost_usd || 0,
        status: latency > 3000 ? 'slow' : latency < 1500 ? 'fast' : 'normal'
    };
    
    history.unshift(historyItem);
    
    // Keep only last 10 items
    if (history.length > MAX_HISTORY_ITEMS) {
        history.splice(MAX_HISTORY_ITEMS);
    }
    
    saveExecutionHistory(history);
    renderExecutionHistory();
}

// Get execution history from session storage
function getExecutionHistory() {
    const stored = sessionStorage.getItem('executionHistory');
    return stored ? JSON.parse(stored) : [];
}

// Save execution history to session storage
function saveExecutionHistory(history) {
    sessionStorage.setItem('executionHistory', JSON.stringify(history));
}

// Load and render execution history
function loadExecutionHistory() {
    renderExecutionHistory();
}

// Render execution history table
function renderExecutionHistory() {
    const tbody = document.getElementById('historyTableBody');
    const history = getExecutionHistory();
    
    if (history.length === 0) {
        tbody.innerHTML = '<tr class="empty-state"><td colspan="6">No execution history yet. Run a scenario to get started.</td></tr>';
        return;
    }
    
    tbody.innerHTML = '';
    history.forEach(item => {
        const tr = document.createElement('tr');
        const time = new Date(item.timestamp).toLocaleTimeString();
        tr.innerHTML = `
            <td>${time}</td>
            <td>S${item.scenarioId}</td>
            <td>${item.latency.toFixed(0)}ms</td>
            <td>${item.tokens.toFixed(0)}</td>
            <td>$${item.cost.toFixed(4)}</td>
            <td class="status-${item.status}">${item.status.toUpperCase()}</td>
        `;
        tbody.appendChild(tr);
    });
}

// Handle clear history
function handleClearHistory() {
    if (confirm('Are you sure you want to clear execution history?')) {
        sessionStorage.removeItem('executionHistory');
        renderExecutionHistory();
    }
}

// Handle sort
let currentSort = { column: 'timestamp', direction: 'desc' };

function handleSort(column) {
    const history = getExecutionHistory();
    
    // Toggle direction if same column
    if (currentSort.column === column) {
        currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
    } else {
        currentSort.column = column;
        currentSort.direction = 'desc';
    }
    
    // Sort history
    history.sort((a, b) => {
        let aVal = a[column];
        let bVal = b[column];
        
        if (typeof aVal === 'string') {
            aVal = aVal.toLowerCase();
            bVal = bVal.toLowerCase();
        }
        
        if (currentSort.direction === 'asc') {
            return aVal > bVal ? 1 : -1;
        } else {
            return aVal < bVal ? 1 : -1;
        }
    });
    
    saveExecutionHistory(history);
    renderExecutionHistory();
    
    // Update sort indicators
    document.querySelectorAll('.history-table th.sortable').forEach(th => {
        th.classList.remove('sorted-asc', 'sorted-desc');
    });
    
    const sortedTh = document.querySelector(`.history-table th[data-sort="${column}"]`);
    sortedTh.classList.add(`sorted-${currentSort.direction}`);
}

// Handle export JSON
function handleExportJson() {
    if (!currentExecution) {
        alert('No execution data to export');
        return;
    }
    
    const exportData = {
        scenario: currentExecution.scenario,
        userPrompt: currentExecution.userPrompt,
        timestamp: currentExecution.endTime,
        faultResult: currentExecution.faultResult,
        baselineResult: currentExecution.baselineResult,
        comparison: {
            latency_delta: currentExecution.faultResult.metrics.latency_ms - currentExecution.baselineResult.metrics.latency_ms,
            token_delta: currentExecution.faultResult.metrics.total_tokens - currentExecution.baselineResult.metrics.total_tokens,
            cost_delta: currentExecution.faultResult.metrics.estimated_cost_usd - currentExecution.baselineResult.metrics.estimated_cost_usd
        }
    };
    
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `performance-test-${currentExecution.scenarioId}-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

// Handle generate report
function handleGenerateReport() {
    if (!currentExecution) {
        alert('No execution data to generate report');
        return;
    }
    
    const reportHtml = generateHtmlReport(currentExecution);
    const blob = new Blob([reportHtml], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `performance-report-${currentExecution.scenarioId}-${Date.now()}.html`;
    a.click();
    URL.revokeObjectURL(url);
}

// Generate HTML report
function generateHtmlReport(execution) {
    const latencyDelta = execution.faultResult.metrics.latency_ms - execution.baselineResult.metrics.latency_ms;
    const tokenDelta = execution.faultResult.metrics.total_tokens - execution.baselineResult.metrics.total_tokens;
    
    return `
<!DOCTYPE html>
<html>
<head>
    <title>Performance Test Report - Scenario ${execution.scenarioId}</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }
        h1 { color: #7FA876; }
        .summary { background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #7FA876; color: white; }
        .metric-positive { color: #E74C3C; }
        .metric-negative { color: #1E8449; }
    </style>
</head>
<body>
    <h1>Performance Test Report</h1>
    <div class="summary">
        <h2>Executive Summary</h2>
        <p><strong>Scenario:</strong> ${execution.scenario.name}</p>
        <p><strong>Test Date:</strong> ${new Date(execution.endTime).toLocaleString()}</p>
        <p><strong>Prompt:</strong> ${execution.userPrompt}</p>
        <p><strong>Key Finding:</strong> Fault injection resulted in ${latencyDelta.toFixed(0)}ms latency increase and ${tokenDelta.toFixed(0)} additional tokens.</p>
    </div>
    
    <h2>Metrics Comparison</h2>
    <table>
        <tr>
            <th>Metric</th>
            <th>Fault Injected</th>
            <th>Optimized Baseline</th>
            <th>Delta</th>
        </tr>
        <tr>
            <td>Latency</td>
            <td>${execution.faultResult.metrics.latency_ms.toFixed(0)}ms</td>
            <td>${execution.baselineResult.metrics.latency_ms.toFixed(0)}ms</td>
            <td class="metric-positive">+${latencyDelta.toFixed(0)}ms</td>
        </tr>
        <tr>
            <td>Total Tokens</td>
            <td>${execution.faultResult.metrics.total_tokens}</td>
            <td>${execution.baselineResult.metrics.total_tokens}</td>
            <td class="metric-positive">+${tokenDelta}</td>
        </tr>
        <tr>
            <td>Estimated Cost</td>
            <td>$${execution.faultResult.metrics.estimated_cost_usd.toFixed(4)}</td>
            <td>$${execution.baselineResult.metrics.estimated_cost_usd.toFixed(4)}</td>
            <td class="metric-positive">+$${(execution.faultResult.metrics.estimated_cost_usd - execution.baselineResult.metrics.estimated_cost_usd).toFixed(4)}</td>
        </tr>
    </table>
    
    <h2>Recommendations</h2>
    <p>${generateKeyTakeaway(execution.scenario)}</p>
</body>
</html>
    `;
}
