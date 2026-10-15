import { FlaskConical } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';

/** Marks content that exists only to demonstrate the interface. */
export function DemoLabel({ kind = 'content' }: { kind?: 'content' | 'artwork' }) {
  const { t } = useTranslation();
  return (
    <Badge variant="synthetic" data-testid="demo-label">
      <FlaskConical aria-hidden="true" />
      {kind === 'artwork' ? t('demo.temporaryArtwork') : t('demo.label')}
    </Badge>
  );
}
