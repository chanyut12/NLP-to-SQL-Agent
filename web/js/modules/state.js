/**
 * State management module for Thai NLP-to-SQL Agent
 * Centralized application state with getter/setter functions
 */

// Application state
const state = {
    // The datasource is fixed server-side; the UI is always "connected".
    isConnected: true,
    currentTab: 'schema',
    // Visualization state
    currentVizConfig: null,
    currentVizData: null,
    currentChartId: null,
    // Feedback state
    currentFeedbackLogId: null
};

// Getters
export const isConnected = () => state.isConnected;
export const getCurrentTab = () => state.currentTab;
export const getVizConfig = () => state.currentVizConfig;
export const getVizData = () => state.currentVizData;
export const getChartId = () => state.currentChartId;
export const getFeedbackLogId = () => state.currentFeedbackLogId;

// Setters
export const setCurrentTab = (value) => { state.currentTab = value; };
export const setFeedbackLogId = (value) => { state.currentFeedbackLogId = value; };

/**
 * Set all visualization state at once.
 * Preferred over individual setters for atomic updates.
 * @param {Object} config - Visualization configuration
 * @param {Array} data - Chart data
 * @param {string} chartId - Canvas element ID
 */
export const setVizState = (config, data, chartId) => {
    state.currentVizConfig = config;
    state.currentVizData = data;
    state.currentChartId = chartId;
};

/**
 * Clear all visualization state.
 * Used when no chart should be displayed.
 */
export const clearVizState = () => {
    state.currentVizConfig = null;
    state.currentVizData = null;
    state.currentChartId = null;
};
