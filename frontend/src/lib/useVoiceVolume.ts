import { useSyncExternalStore } from 'react';

import { getVoiceVolume, onVoiceVolumeChange, setVoiceVolume } from './voicePlayer';

/** The shared voice volume as a percentage (0-100), and its setter. */
export function useVoiceVolume(): [number, (percent: number) => void] {
  const volume = useSyncExternalStore(onVoiceVolumeChange, getVoiceVolume, () => 0.8);
  return [Math.round(volume * 100), (percent: number) => setVoiceVolume(percent / 100)];
}
