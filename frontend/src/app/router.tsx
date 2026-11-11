import { createBrowserRouter, Navigate, useLocation } from 'react-router';

import { AuthLayout } from '@/components/layout/AuthLayout';
import { AppShell } from '@/components/layout/AppShell';
import { talkRedirectSearch } from '@/lib/talkRedirect';
import { DesignReferencePage } from '@/pages/DesignReferencePage';
import { EnergyIndexRedirect, EnergyLayout } from '@/pages/EnergyLayout';
import { HomePage } from '@/pages/HomePage';
import { DataManagementPage } from '@/pages/DataManagementPage';
import { DatasetsPage } from '@/pages/DatasetsPage';
import { AnalysisReportPage } from '@/pages/AnalysisReportPage';
import { AssistantPage } from '@/pages/AssistantPage';
import { ForecastPage } from '@/pages/ForecastPage';
import { AuditPage } from '@/pages/AuditPage';
import { HealthPage } from '@/pages/HealthPage';
import { GeographyPage } from '@/pages/GeographyPage';
import { LibraryPage } from '@/pages/LibraryPage';
import { NotFoundPage, SourcesPage } from '@/pages/InfoPages';
import { OverviewPage } from '@/pages/OverviewPage';
import { WorkspacePage } from '@/pages/WorkspacePage';
import { ReportPage, ReportsPage } from '@/pages/ReportsPages';
import { SettingsPage } from '@/pages/SettingsPage';
import { StudiesPage } from '@/pages/StudiesPage';
import { ElectricityPage, FoodSecurityPage, TradePage, WaterPage } from '@/pages/SectionPages';
import { AccountPage, AdminUsersPage, ForgotPasswordPage, RegisterPage, SignInPage } from '@/pages/SignInPage';

/** Old /forecast links land on Forecasts and Scenarios, keeping the query string. */
function ForecastRedirect() {
  const { search } = useLocation();
  return <Navigate to={{ pathname: '/forecasts', search }} replace />;
}

/** Old /methodology links land on Sources and Methodology, keeping the query string. */
function MethodologyRedirect() {
  const { search } = useLocation();
  return <Navigate to={{ pathname: '/sources', search }} replace />;
}

/** Retired sign-in pages (e-mail links, e-mail verification and reset, phone and other
 * providers, the development mailbox): old links land on the username sign-in. Only the data
 * mode is kept; tokens in old links are dropped and never sent anywhere. */
function RetiredSignInRedirect() {
  const { search } = useLocation();
  const mode = new URLSearchParams(search).get('mode');
  const keep = mode === 'synthetic' || mode === 'verified' ? `?mode=${mode}` : '';
  return <Navigate to={{ pathname: '/sign-in', search: keep }} replace />;
}

/** The old Talk screen: /talk opens the one Al Mulhim conversation (lib/talkRedirect). */
function TalkRedirect() {
  const { search } = useLocation();
  return <Navigate to={{ pathname: '/assistant', search: talkRedirectSearch(search) }} replace />;
}

export const router = createBrowserRouter([
  {
    // Sign-in, registration and a forgotten password: the full-screen glass design.
    element: <AuthLayout />,
    children: [
      { path: '/sign-in', element: <SignInPage /> },
      { path: '/register', element: <RegisterPage /> },
      { path: '/forgot-password', element: <ForgotPasswordPage /> },
    ],
  },
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'overview', element: <OverviewPage /> },
      { path: 'workspace', element: <WorkspacePage /> },
      {
        path: 'energy',
        element: <EnergyLayout />,
        children: [
          { index: true, element: <EnergyIndexRedirect /> },
          { path: 'electricity', element: <ElectricityPage /> },
          { path: 'water', element: <WaterPage /> },
        ],
      },
      { path: 'food-security', element: <FoodSecurityPage /> },
      { path: 'trade', element: <TradePage /> },
      { path: 'geography', element: <GeographyPage /> },
      { path: 'forecasts', element: <ForecastPage /> },
      { path: 'forecast', element: <ForecastRedirect /> },
      { path: 'assistant', element: <AssistantPage /> },
      { path: 'talk', element: <TalkRedirect /> },
      { path: 'library', element: <LibraryPage /> },
      { path: 'studies', element: <StudiesPage /> },
      { path: 'studies/:studyId', element: <StudiesPage /> },
      { path: 'datasets', element: <DatasetsPage /> },
      { path: 'datasets/:datasetId', element: <DatasetsPage /> },
      { path: 'reports', element: <ReportsPage /> },
      { path: 'reports/:reportId', element: <ReportPage /> },
      { path: 'reports/analysis/:reportId', element: <AnalysisReportPage /> },
      { path: 'sources', element: <SourcesPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: 'methodology', element: <MethodologyRedirect /> },
      { path: 'data-management', element: <DataManagementPage /> },
      // Retired: e-mail, phone, Google and Microsoft sign-in and their pages.
      ...['sign-in/other', 'verify-email', 'forgot-password/email', 'reset-password', 'magic-link', 'link-email', 'dev/mail']
        .map((path) => ({ path, element: <RetiredSignInRedirect /> })),
      { path: 'account', element: <AccountPage /> },
      { path: 'admin/users', element: <AdminUsersPage /> },
      { path: 'admin/health', element: <HealthPage /> },
      { path: 'admin/audit', element: <AuditPage /> },
      { path: 'design-reference', element: <DesignReferencePage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);
