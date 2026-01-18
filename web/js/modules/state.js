/**
 * State management module for Thai NLP-to-SQL Agent
 * Centralized application state with getter/setter functions
 */

// Application state
const state = {
    isConnected: false,
    currentTab: 'connection',
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
export const setConnected = (value) => { state.isConnected = value; };
export const setCurrentTab = (value) => { state.currentTab = value; };
export const setVizConfig = (value) => { state.currentVizConfig = value; };
export const setVizData = (value) => { state.currentVizData = value; };
export const setChartId = (value) => { state.currentChartId = value; };
export const setFeedbackLogId = (value) => { state.currentFeedbackLogId = value; };

// Bulk setter for visualization state
export const setVizState = (config, data, chartId) => {
    state.currentVizConfig = config;
    state.currentVizData = data;
    state.currentChartId = chartId;
};

// Clear visualization state
export const clearVizState = () => {
    state.currentVizConfig = null;
    state.currentVizData = null;
    state.currentChartId = null;
};
