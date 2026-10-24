import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { adapterKind } from '@/api/config';
import { PageHeader } from '@/components/common/PageHeader';
import { ReferencePackSources } from '@/components/common/ReferencePackSources';
import { PublicFeedStatus } from '@/components/sources/SourceFeeds';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { ALL_PHOTOS } from '@/content/photos';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { usePreservedSearch } from '@/state/usePreservedSearch';

const METHOD_RULES = [
  'pages.sources.rules.provenance',
  'pages.sources.rules.missing',
  'pages.sources.rules.modes',
  'pages.sources.rules.comparison',
  'pages.sources.rules.rounding',
  'pages.sources.rules.recommendations',
] as const;

export function SourcesPage() {
  const { t } = useTranslation();
  const language = useAppLanguage();

  return (
    <>
      <PageHeader title={t('pages.sources.title')} intro={t('pages.sources.intro')} />
      <div className="flex flex-col gap-10">
        <section aria-labelledby="method-heading">
          <h2 id="method-heading" className="mb-4 text-xl font-semibold">{t('pages.sources.rulesHeading')}</h2>
          <ol className="grid gap-3 md:grid-cols-2">
            {METHOD_RULES.map((key, i) => (
              <li key={key} className="flex gap-3 rounded-lg border border-border bg-card p-4 text-sm">
                <span aria-hidden="true" className="flex size-7 shrink-0 items-center justify-center rounded-full bg-sand-subtle text-xs font-semibold text-sand-foreground">
                  {i + 1}
                </span>
                <span className="pt-0.5">{t(key)}</span>
              </li>
            ))}
          </ol>
        </section>

        {adapterKind === 'http' ? (
          <section aria-labelledby="feeds-public-heading" data-testid="sources-feeds">
            <h2 id="feeds-public-heading" className="mb-2 text-xl font-semibold">{t('feeds.heading')}</h2>
            <p className="mb-4 max-w-3xl text-sm text-muted-foreground">{t('feeds.intro')}</p>
            <PublicFeedStatus />
          </section>
        ) : null}

        <section aria-labelledby="data-sources-heading">
          <h2 id="data-sources-heading" className="mb-4 text-xl font-semibold">{t('pages.sources.sourcesHeading')}</h2>
          <div className="grid gap-4 md:grid-cols-2">
            <Card className="p-5 text-sm">
              <Badge variant="verified" className="mb-2">{t('dataMode.verified_source')}</Badge>
              <p>{t('pages.sources.sourcesVerified')}</p>
            </Card>
            <Card className="p-5 text-sm">
              <Badge variant="synthetic" className="mb-2">{t('dataMode.synthetic')}</Badge>
              <p>{t('pages.sources.sourcesSynthetic')}</p>
            </Card>
          </div>
        </section>

        <ReferencePackSources />

        <section aria-labelledby="image-credits-heading" id="image-credits" tabIndex={-1} className="scroll-mt-6 outline-none">
          <h2 id="image-credits-heading" className="mb-2 text-xl font-semibold">{t('pages.sources.imagesHeading')}</h2>
          <p className="mb-4 max-w-3xl text-sm text-muted-foreground">
            {t('pages.sources.imagesIntro')} {t('pages.sources.imageChanges')}
          </p>
          <ul className="grid gap-4 md:grid-cols-2" data-testid="image-credits">
            {ALL_PHOTOS.map((photo) => (
              <li key={photo.id} className="flex gap-4 rounded-lg border border-border bg-card p-4">
                <img src={photo.src} alt="" width={96} height={72} loading="lazy" className="h-18 w-24 shrink-0 rounded-md object-cover" />
                <dl className="grid min-w-0 grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
                  <dt className="text-muted-foreground">{t('pages.sources.imageLocation')}</dt>
                  <dd className="font-medium">{photo.location[language]}</dd>
                  <dt className="text-muted-foreground">{t('pages.sources.imageCreator')}</dt>
                  <dd>{photo.creator}</dd>
                  <dt className="text-muted-foreground">{t('pages.sources.imageLicense')}</dt>
                  <dd>
                    <a href={photo.licenseUrl} target="_blank" rel="noreferrer" className="text-primary underline underline-offset-2">
                      {photo.license}
                    </a>
                  </dd>
                  <dt className="text-muted-foreground">{t('pages.sources.imageFile')}</dt>
                  <dd className="min-w-0">
                    <a href={photo.sourceUrl} target="_blank" rel="noreferrer" className="break-all text-primary underline underline-offset-2">
                      Wikimedia Commons
                    </a>
                  </dd>
                </dl>
              </li>
            ))}
          </ul>
        </section>

        <div className="grid gap-4 md:grid-cols-2">
          <section aria-labelledby="type-heading" className="rounded-lg border border-border bg-card p-5">
            <h2 id="type-heading" className="mb-2 font-semibold">{t('pages.sources.typeHeading')}</h2>
            <p className="text-sm text-muted-foreground">{t('pages.sources.type')}</p>
          </section>
          <section aria-labelledby="identity-heading" className="rounded-lg border border-border bg-card p-5">
            <h2 id="identity-heading" className="mb-2 font-semibold">{t('pages.sources.identityHeading')}</h2>
            <p className="text-sm text-muted-foreground">{t('pages.sources.identity')}</p>
          </section>
        </div>
      </div>
    </>
  );
}

export function NotFoundPage() {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  return (
    <>
      <PageHeader title={t('pages.notFound.title')} />
      <Link to={to('/')} className="text-sm font-medium text-primary underline underline-offset-4 hover:no-underline">
        {t('pages.notFound.back')}
      </Link>
    </>
  );
}
