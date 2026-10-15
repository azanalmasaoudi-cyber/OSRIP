import type { DomainCode, SectionCode } from './types';

/** Booklet 3.14: exactly three primary domains; electricity and water are tabs of the first. */
export interface DomainDefinition {
  code: DomainCode;
  path: string;
  sections: readonly SectionCode[];
}

export const DOMAINS: readonly DomainDefinition[] = [
  { code: 'energy_essential_services', path: '/energy', sections: ['electricity', 'water'] },
  { code: 'food_security', path: '/food-security', sections: ['food_security'] },
  { code: 'trade', path: '/trade', sections: ['trade'] },
] as const;

export const SECTION_PATHS: Record<SectionCode, string> = {
  electricity: '/energy/electricity',
  water: '/energy/water',
  food_security: '/food-security',
  trade: '/trade',
};
