import { Navigate, Outlet, useLocation } from 'react-router';

/**
 * Electricity and Water keep their addresses under /energy (booklet 3.14). Each is a sector
 * page of its own, with the same header, sector links and period-first selection as Food
 * Security and Trade (pages/SectionPages).
 */
export function EnergyLayout() {
  return <Outlet />;
}

/** /energy -> /energy/electricity, keeping the query string (data mode). */
export function EnergyIndexRedirect() {
  const { search } = useLocation();
  return <Navigate to={{ pathname: '/energy/electricity', search }} replace />;
}
