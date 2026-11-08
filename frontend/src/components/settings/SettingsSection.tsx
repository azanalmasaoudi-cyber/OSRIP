import { Clapperboard } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { adapterKind } from '@/api/config';
import { usePersona } from '@/components/assistant/persona';
import { PersonaImage } from '@/components/assistant/PersonaImage';
import { introAutoplay, setIntroAutoplay } from '@/components/layout/Entrance';
import { useReplayEntrance } from '@/components/layout/entranceControl';
import { LanguageSwitcher } from '@/components/layout/LanguageSwitcher';
import { ThemeSelector } from '@/components/layout/ThemeSelector';
import { Button } from '@/components/ui/button';

/** The assistant, Al Mulhim (the only one: nothing to choose), in both languages. */
function AssistantIdentity() {
  const { t } = useTranslation();
  const { persona } = usePersona();
  return (
    <p className="flex w-fit items-center gap-2.5 rounded-full border border-border-strong/50 py-1 ps-1 pe-4" data-testid="settings-assistant"
      data-persona={persona.code}>
      <PersonaImage src={persona.avatar.portrait} alt="" width={36} height={36} className="size-9 rounded-full object-cover object-top" draggable={false} />
      <span className="flex flex-col text-sm leading-tight">
        <span className="font-semibold" lang="en">{persona.name.en}</span>
        <span className="text-xs text-muted-foreground" lang="ar" dir="rtl">{persona.name.ar} · {t('assistant.aiAssistant')}</span>
      </span>
    </p>
  );
}

/** Settings (shown whether or not you are signed in): the appearance (#appearance), the language
 * (#language), the assistant, and the first-visit introduction. */
export function SettingsSection() {
  const { t } = useTranslation();
  const replay = useReplayEntrance();
  const [autoplay, setAutoplay] = useState(introAutoplay);
  return (
    <section aria-labelledby="settings-heading" className="surface-card flex flex-col gap-4 p-5" data-testid="settings">
      <h2 id="settings-heading" className="text-lg font-semibold">{t('settings.title')}</h2>
      <div id="appearance" tabIndex={-1} className="flex scroll-mt-24 flex-wrap items-center justify-between gap-3 outline-none" data-testid="settings-theme">
        <div className="min-w-0 flex-1">
          <h3 className="font-medium">{t('theme.settingsTitle')}</h3>
          <p className="text-sm text-muted-foreground">{t('theme.settingsBody')}</p>
        </div>
        <ThemeSelector className="w-full sm:w-72" />
      </div>
      <div id="language" tabIndex={-1} className="flex scroll-mt-24 flex-wrap items-center justify-between gap-3 outline-none" data-testid="settings-language">
        <div className="min-w-0 flex-1">
          <h3 className="font-medium">{t('settings.languageTitle')}</h3>
          <p className="text-sm text-muted-foreground">{t('settings.languageBody')}</p>
        </div>
        <LanguageSwitcher />
      </div>
      {adapterKind === 'http' ? (
        <div className="flex flex-col gap-2" data-testid="settings-persona">
          <div>
            <h3 className="font-medium">{t('settings.assistantTitle')}</h3>
            <p className="text-sm text-muted-foreground">{t('settings.assistantBody')}</p>
          </div>
          <AssistantIdentity />
        </div>
      ) : null}
      {replay ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 flex-1 flex-col gap-1.5">
            <h3 className="font-medium">{t('settings.introTitle')}</h3>
            <p className="text-sm text-muted-foreground">{t('settings.introBody')}</p>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={autoplay} className="size-4 accent-primary" data-testid="settings-intro-autoplay"
                onChange={(e) => { setIntroAutoplay(e.target.checked); setAutoplay(e.target.checked); }} />
              {t('settings.introAuto')}
            </label>
          </div>
          <Button variant="outline" onClick={replay} data-testid="settings-replay-entrance">
            <Clapperboard aria-hidden="true" />{t('entrance.replay')}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
