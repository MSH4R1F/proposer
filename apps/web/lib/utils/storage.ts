const STORAGE_KEYS = {
  SESSION_ID: 'proposer_session_id',
  CASE_ID: 'proposer_case_id',
} as const;

/**
 * Session ID validation patterns:
 * - Full UUID v4: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx (36 chars)
 * - Short session ID from backend: first 12 chars of UUID (e.g., "7eedb1db-9d9")
 */
const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SHORT_SESSION_ID_REGEX = /^[0-9a-f-]{8,12}$/i;

/**
 * Validate if a string is a valid session ID.
 * Accepts both full UUID format and the backend's short 12-char format.
 */
export function isValidSessionId(sessionId: string | null): boolean {
  if (!sessionId) return false;
  // Accept full UUID or short session ID format from backend
  return UUID_REGEX.test(sessionId) || SHORT_SESSION_ID_REGEX.test(sessionId);
}

export function saveSessionId(sessionId: string): void {
  if (typeof window !== 'undefined' && isValidSessionId(sessionId)) {
    localStorage.setItem(STORAGE_KEYS.SESSION_ID, sessionId);
  }
}

export function getSessionId(): string | null {
  if (typeof window !== 'undefined') {
    const sessionId = localStorage.getItem(STORAGE_KEYS.SESSION_ID);
    // Return null if stored session ID is invalid
    if (sessionId && !isValidSessionId(sessionId)) {
      clearSessionId();
      return null;
    }
    return sessionId;
  }
  return null;
}

export function clearSessionId(): void {
  if (typeof window !== 'undefined') {
    localStorage.removeItem(STORAGE_KEYS.SESSION_ID);
  }
}

export function saveCaseId(caseId: string): void {
  if (typeof window !== 'undefined') {
    localStorage.setItem(STORAGE_KEYS.CASE_ID, caseId);
  }
}

export function getCaseId(): string | null {
  if (typeof window !== 'undefined') {
    return localStorage.getItem(STORAGE_KEYS.CASE_ID);
  }
  return null;
}

export function clearCaseId(): void {
  if (typeof window !== 'undefined') {
    localStorage.removeItem(STORAGE_KEYS.CASE_ID);
  }
}

export function clearAllStorage(): void {
  clearSessionId();
  clearCaseId();
}
