/**
 * State management module for Thai NLP-to-SQL Agent
 * Centralized application state with getter/setter functions
 */

// Application state
const state = {
    // The datasource is fixed server-side; the UI is always "connected".
    isConnected: true,
    currentTab: 'schema',
    // Feedback state
    currentFeedbackLogId: null
};

// Getters
export const isConnected = () => state.isConnected;
export const getCurrentTab = () => state.currentTab;
export const getFeedbackLogId = () => state.currentFeedbackLogId;

// Setters
export const setCurrentTab = (value) => { state.currentTab = value; };
export const setFeedbackLogId = (value) => { state.currentFeedbackLogId = value; };
