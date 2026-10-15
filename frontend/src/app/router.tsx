import { createBrowserRouter, Navigate, useLocation } from 'react-router';

import { AppShell } from '@/components/layout/AppShell';
import { DesignReferencePage } from '@/pages/DesignReferencePage';
import { EnergyIndexRedirect, EnergyLayout } from '@/pages/EnergyLayout';
import { HomePage } from '@/pages/HomePage';
import { DataManagementPage } from '@/pages/DataManagementPage';
import { AssistantPage } from '@/pages/AssistantPage';
import { ForecastPage } from '@/pages/ForecastPage';
import { HealthPage } from '@/pages/HealthPage';
import { GeographyPage } from '@/pages/GeographyPage';
import { LibraryPage } from '@/pages/LibraryPage';
import { NotFoundPage, SourcesPage } from '@/pages/InfoPages';
import { OverviewPage } from '@/pages/OverviewPage';
import { ReportPage, ReportsPage } from '@/pages/ReportsPages';
import { StudiesPage } from '@/pages/StudiesPage';
import { TalkPage } from '@/pages/TalkPage';
import { ElectricityPage, FoodSecurityPage, TradePage, WaterPage } from '@/pages/SectionPages';
import {
  AccountPage,
  AdminUsersPage,
  DevMailPage,
  ForgotPasswordPage,
  LinkEmailPage,
  MagicLinkPage,
  RegisterPage,
  ResetPasswordPage,
  SignInPage,
  VerifyEmailPage,
} from '@/pages/SignInPage';

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

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'overview', element: <OverviewPage /> },
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
      { path: 'talk', element: <TalkPage /> },
      { path: 'library', element: <LibraryPage /> },
      { path: 'studies', element: <StudiesPage /> },
      { path: 'studies/:studyId', element: <StudiesPage /> },
      { path: 'reports', element: <ReportsPage /> },
      { path: 'reports/:reportId', element: <ReportPage /> },
      { path: 'sources', element: <SourcesPage /> },
      { path: 'methodology', element: <MethodologyRedirect /> },
      { path: 'data-management', element: <DataManagementPage /> },
      { path: 'sign-in', element: <SignInPage /> },
      { path: 'register', element: <RegisterPage /> },
      { path: 'verify-email', element: <VerifyEmailPage /> },
      { path: 'forgot-password', element: <ForgotPasswordPage /> },
      { path: 'reset-password', element: <ResetPasswordPage /> },
      { path: 'magic-link', element: <MagicLinkPage /> },
      { path: 'link-email', element: <LinkEmailPage /> },
      { path: 'account', element: <AccountPage /> },
      { path: 'admin/users', element: <AdminUsersPage /> },
      { path: 'admin/health', element: <HealthPage /> },
      { path: 'dev/mail', element: <DevMailPage /> },
      { path: 'design-reference', element: <DesignReferencePage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);
