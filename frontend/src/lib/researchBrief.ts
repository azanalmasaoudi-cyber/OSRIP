// No imports: Node's unit test and the browser tests load this file directly.
export type BriefLanguage = 'ar' | 'en';
export const BRIEF_DOMAINS = ['electricity', 'water', 'food', 'trade'] as const;
export type BriefDomain = typeof BRIEF_DOMAINS[number];
export const BRIEF_GOALS = ['trend', 'drivers', 'scenario', 'research'] as const;
export type BriefGoal = typeof BRIEF_GOALS[number];
export const briefDomains = {
  en: { electricity: 'Electricity', water: 'Water', food: 'Food security', trade: 'Trade' },
  ar: { electricity: 'الكهرباء', water: 'المياه', food: 'الأمن الغذائي', trade: 'التجارة' },
};
export const briefGoals = {
  en: { trend: 'Explain trends', drivers: 'Study contributing factors', scenario: 'Explore a scenario', research: 'Find recent evidence' },
  ar: { trend: 'تفسير الاتجاهات', drivers: 'دراسة العوامل المؤثرة', scenario: 'استكشاف سيناريو', research: 'البحث عن أدلة حديثة' },
};
/** The existing answer mode for each goal: Research searches the web, Scenario keeps what-if
 * arithmetic apart from forecasts, and trends and contributing factors are analyses. (The
 * builder hands these to the panel as AssistantMode, so tsc checks they are real modes.) */
export const BRIEF_MODE = {
  trend: 'analyze', drivers: 'analyze', scenario: 'scenario', research: 'research',
} as const satisfies Record<BriefGoal, string>;
/** Draft only: submitting still uses the existing permissions, provider and guest quota. */
export function buildResearchBrief(language: BriefLanguage, domain: BriefDomain, goal: BriefGoal): string {
  if (language === 'ar') return `أعد دراسة عن ${briefDomains.ar[domain]} في عُمان من ٢٠٢٢ إلى أحدث فترة متاحة. الهدف: ${briefGoals.ar[goal]}. استخدم البيانات المعتمدة المتاحة، وبيّن النقص بدلاً من اختلاق أرقام. ميّز فترة الإحصاء عن تاريخ النشر. اعرض ملخصاً وجدولاً بالمؤشر والقيمة والوحدة والفترة والمصدر، ورسم اتجاه عند توفر بيانات قابلة للمقارنة. ناقش عوامل البيئة العُمانية مثل المناخ والسكان والموسمية والتجارة والسياسات، دون اعتبار الارتباط سبباً. افصل المشاهدات والحسابات والافتراضات والتوقعات؛ إذا كانت السلسلة غير كافية فلا تتنبأ. اختم بتوصيات قابلة للدراسة وحدود التحليل وروابط المراجع.`;
  return `Prepare a study of ${briefDomains.en[domain]} in Oman from 2022 to the latest available period. Goal: ${briefGoals.en[goal]}. Use available approved data; identify gaps instead of inventing figures. Distinguish reference period from publication date. Provide a summary, a table with indicator, value, unit, period and source, and a trend chart only for comparable data. Assess relevant Omani factors: climate, population, seasonality, trade and policy, without treating correlation as causation. Separate observations, calculations, assumptions and forecasts; do not forecast an insufficient series. End with actionable research recommendations, limitations and source links.`;
}
