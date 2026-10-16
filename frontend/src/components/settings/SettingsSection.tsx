import { Clapperboard } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { adapterKind } from '@/api/config';
import { PersonaPicker } from '@/components/assistant/persona';
import { useReplayEntrance } from '@/components/layout/entranceControl';
import { ThemeSelector } from '@/components/layout/ThemeSelector';
import { Button } from '@/components/ui/button';

/** Settings (shown on the Account page whether or not you are signed in): the appearance, who
 * answers as the assistant, and the first-visit introduction. */
export function SettingsSection() {
  const { t } = useTranslation();
  const replay = useReplayEntrance();
  return (
    <section aria-labelledby="settings-heading" className="surface-card flex flex-col gap-4 p-5" data-testid="settings">
      <h2 id="settings-heading" className="text-lg font-semibold">{t('settings.title')}</h2>
      <div className="flex flex-wrap items-center justify-between gap-3" data-testid="settings-theme">
        <div className="min-w-0 flex-1">
          <h3 className="font-medium">{t('theme.settingsTitle')}</h3>
          <p className="text-sm text-muted-foreground">{t('theme.settingsBody')}</p>
        </div>
        <ThemeSelector className="w-full sm:w-72" />
      </div>
      {adapterKind === 'http' ? (
        <div className="flex flex-col gap-2" data-testid="settings-persona">
          <div>
            <h3 className="font-medium">{t('settings.assistantTitle')}</h3>
            <p className="text-sm text-muted-foreground">{t('settings.assistantBody')}</p>
          </div>
          <PersonaPicker />
        </div>
      ) : null}
      {replay ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="font-medium">{t('settings.introTitle')}</h3>
            <p className="text-sm text-muted-foreground">{t('settings.introBody')}</p>
          </div>
          <Button variant="outline" onClick={replay} data-testid="settings-replay-entrance">
            <Clapperboard aria-hidden="true" />{t('entrance.replay')}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
