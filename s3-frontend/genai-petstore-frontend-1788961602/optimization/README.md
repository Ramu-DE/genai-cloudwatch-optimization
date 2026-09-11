# Performance Tuning Dashboard

## Overview

The Performance Tuning Dashboard is an interactive web interface for executing and visualizing Luna Nutrition Agent optimization scenarios. It enables side-by-side comparison of fault-injected scenarios against optimized baselines to demonstrate the impact of architectural decisions on performance and cost.

## Files

- **performance-tuning.html** - Main dashboard HTML structure
- **performance-tuning.css** - Styling and responsive design
- **performance-tuning.js** - JavaScript logic for scenario execution and visualization

## Features

### 1. Scenario Selection
- Dropdown selector with all 39 performance testing scenarios
- Scenario descriptions and expected impact display
- Support for fault injection, optimization, baseline, and validation scenarios

### 2. Dual Execution Panels
- Side-by-side comparison of fault-injected vs optimized baseline
- Real-time status updates with elapsed time counters
- Independent progress indicators for each execution
- Activity logs showing tool invocations and processing steps

### 3. Metrics Comparison
- Comprehensive metrics table with:
  - Latency (ms)
  - Input/Output/Total tokens
  - Tool call counts
  - Estimated costs
- Delta calculations with percentage changes
- Color-coded impact indicators (🟢 🟡 🟠 🔴)

### 4. Root Cause Analysis
- Automated analysis of performance differences
- Scenario-specific explanations
- Educational content:
  - Key Takeaways
  - Why This Matters
  - AWS Documentation Links

### 5. Execution History
- Last 10 scenario executions stored in session storage
- Sortable table by timestamp, scenario, latency, tokens, cost, status
- Clear history functionality
- Performance status indicators (FAST/NORMAL/SLOW)

### 6. Export & Reporting
- Export results as JSON for programmatic analysis
- Generate HTML reports with executive summary
- Includes metrics comparison and recommendations

## Usage

### Opening the Dashboard

1. Open `performance-tuning.html` in a web browser
2. The dashboard will automatically load scenario configurations from `../config/scenarios.json`

### Running a Scenario

1. Select a scenario from the dropdown
2. Review the scenario description and expected impact
3. Optionally modify the test prompt
4. Click "Run Scenario"
5. Watch real-time execution in both panels
6. Review metrics comparison and root cause analysis
7. Export results if needed

### API Integration

The dashboard currently uses simulated API calls for demonstration purposes. To integrate with the actual backend:

1. Update `API_BASE_URL` in `performance-tuning.js` to point to your backend endpoint
2. Replace `simulateScenarioExecution()` with actual API calls to:
   - `POST /execute-scenario` - Execute fault-injected scenario
   - `POST /execute-baseline` - Execute optimized baseline
   - `GET /scenario-status/{id}` - Poll for execution status (if async)

### Expected API Response Format

```json
{
  "type": "fault" | "baseline",
  "scenarioId": 10,
  "response": "Agent response text",
  "metrics": {
    "latency_ms": 4523.5,
    "input_tokens": 8456,
    "output_tokens": 456,
    "total_tokens": 8912,
    "tool_calls": 2,
    "estimated_cost_usd": 0.0234
  },
  "activity": [
    {
      "timestamp": 1699456789000,
      "message": "Invoking tool: get_user_nutrition_data"
    }
  ]
}
```

## Responsive Design

The dashboard is fully responsive and works on:
- Desktop (1400px+ optimal)
- Tablet (768px - 1024px)
- Mobile (480px - 768px)

## Browser Compatibility

- Chrome/Edge (recommended)
- Firefox
- Safari
- Requires ES6+ support for modern JavaScript features

## Session Storage

The dashboard uses browser session storage for:
- Execution history (last 10 runs)
- Current execution state

Data persists within the browser session but is cleared when the tab is closed.

## Customization

### Adding New Scenarios

1. Add scenario definition to `../config/scenarios.json`
2. The dashboard will automatically load and display it
3. Update `generateRootCauseText()` and `generateKeyTakeaway()` in JS for custom educational content

### Styling

Modify CSS variables in `:root` to customize colors:
```css
--primary-color: #7FA876;
--success-color: #1E8449;
--danger-color: #E74C3C;
--warning-color: #F39C12;
```

### Polling Interval

Adjust `POLLING_INTERVAL` constant in JS (default: 500ms) for status update frequency.

## Development

### Testing Locally

1. Ensure `scenarios.json` is accessible at `../config/scenarios.json`
2. Open `performance-tuning.html` in a browser
3. Use browser DevTools to inspect network calls and console logs

### Debugging

- Open browser console (F12) to view logs
- Check Network tab for API call details
- Session storage can be inspected in Application/Storage tab

## Next Steps

1. Integrate with actual backend API endpoints
2. Add authentication if required
3. Implement WebSocket for real-time streaming updates
4. Add chart visualizations for metrics trends
5. Implement advanced filtering and search in history table
6. Add export to CSV/PDF formats
7. Implement comparison across multiple scenario runs

## Requirements Mapping

This dashboard fulfills the following requirements:
- **Req 25**: Parallel scenario execution with dual panels
- **Req 26**: Real-time performance metrics display
- **Req 27**: Scenario comparison matrix with history
- **Req 28**: Optimized vs baseline visualization
- **Req 29**: Live execution status and progress tracking
- **Req 30**: Scenario metadata and educational content
- **Req 39**: Export and reporting capabilities
