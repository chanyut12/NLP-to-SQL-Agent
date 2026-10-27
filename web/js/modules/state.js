/**
 * State management module for Thai NLP-to-SQL Agent
 * Centralized application state with getter/setter functions
 */

// Application state
const state = {
    // The datasource is fixed server-side; the UI is always "connected".
    isConnected: true,
    // Demo mode opens on the Connection tab, which is where a user starts
    // when they want to point the demo at their own database (ADR 0013).
    currentTab: 'connection',
    // Feedback state
    currentFeedbackLogId: null,
    // Conversational session (ADR 0006): completed Turns replayed to the
    // service with each question; the service itself holds no memory.
    sessionTurns: []
};

// Getters
export const isConnected = () => state.isConnected;
export const getCurrentTab = () => state.currentTab;
export const getFeedbackLogId = () => state.currentFeedbackLogId;
export const getSessionTurns = () => state.sessionTurns;

// Setters
export const setCurrentTab = (value) => { state.currentTab = value; };
export const setFeedbackLogId = (value) => { state.currentFeedbackLogId = value; };
export const resetSession = () => { state.sessionTurns = []; };
export const addSessionTurn = (turn) => { state.sessionTurns.push(turn); };
