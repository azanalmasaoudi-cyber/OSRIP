import { createContext, useContext } from 'react';

/** Replays the first-visit entrance (provided by the app shell; used by the footer and Settings). */
export const EntranceReplayContext = createContext<(() => void) | null>(null);

export function useReplayEntrance(): (() => void) | null {
  return useContext(EntranceReplayContext);
}
