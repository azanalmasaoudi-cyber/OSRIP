import type { BilingualText } from '@/domain/types';

/**
 * Photographs used on the landing page. Every entry is a Wikimedia Commons file
 * whose location was checked against its description, categories and (where
 * recorded) GPS coordinates. Keep in sync with docs/assets.md.
 * Files were only resized; no other edits.
 */
export interface PhotoCredit {
  id: string;
  /** Path under /public. */
  src: string;
  width: number;
  height: number;
  alt: BilingualText;
  location: BilingualText;
  creator: string;
  license: string;
  licenseUrl: string;
  sourceUrl: string;
}

export const PHOTOS = {
  misfat: {
    id: 'misfat',
    src: '/images/photos/misfat-al-abriyeen-village.jpg',
    width: 2000,
    height: 1601,
    alt: {
      en: 'Stone houses of Misfat al Abriyeen above terraced date-palm gardens, with the Hajar mountains behind.',
      ar: 'بيوت حجرية في مسفاة العبريين فوق مدرجات نخيل التمر، وخلفها جبال الحجر.',
    },
    location: { en: 'Misfat al Abriyeen, Al Hamra, Ad Dakhiliyah', ar: 'مسفاة العبريين، الحمراء، الداخلية' },
    creator: 'Broc',
    license: 'CC0 1.0',
    licenseUrl: 'https://creativecommons.org/publicdomain/zero/1.0/',
    sourceUrl: 'https://commons.wikimedia.org/wiki/File:Misfat_Al_Abriyeen_Village,_Oman.jpg',
  },
  falaj: {
    id: 'falaj',
    src: '/images/photos/falaj-misfah.jpg',
    width: 1400,
    height: 1050,
    alt: {
      en: 'A narrow falaj channel carrying water between palm trunks and stone terrace walls.',
      ar: 'قناة فلج ضيقة تحمل الماء بين جذوع النخيل وجدران المدرجات الحجرية.',
    },
    location: { en: 'Falaj in Misfat al Abriyeen, Ad Dakhiliyah', ar: 'فلج في مسفاة العبريين، الداخلية' },
    creator: 'Ji-Elle',
    license: 'CC BY-SA 3.0',
    licenseUrl: 'https://creativecommons.org/licenses/by-sa/3.0/',
    sourceUrl: 'https://commons.wikimedia.org/wiki/File:Misfah_(6).jpg',
  },
  bahla: {
    id: 'bahla',
    src: '/images/photos/bahla-fort.jpg',
    width: 1600,
    height: 682,
    alt: {
      en: 'The mud-brick walls and towers of Bahla Fort under a clear sky.',
      ar: 'أسوار قلعة بهلاء وأبراجها المبنية من الطين تحت سماء صافية.',
    },
    location: { en: 'Bahla Fort, Ad Dakhiliyah (UNESCO World Heritage Site)', ar: 'قلعة بهلاء، الداخلية (موقع تراث عالمي لليونسكو)' },
    creator: 'Ekrem Canli',
    license: 'CC BY-SA 4.0',
    licenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
    sourceUrl: 'https://commons.wikimedia.org/wiki/File:Bahla_Fort_2019_(04).jpg',
  },
  duqm: {
    id: 'duqm',
    src: '/images/photos/duqm-port.jpg',
    width: 1400,
    height: 685,
    alt: {
      en: 'Breakwater and quays of the Port of Duqm on the Arabian Sea.',
      ar: 'حاجز الأمواج وأرصفة ميناء الدقم على بحر العرب.',
    },
    location: { en: 'Port of Duqm, Al Wusta', ar: 'ميناء الدقم، الوسطى' },
    creator: 'AbdullahAlMaani',
    license: 'CC BY-SA 4.0',
    licenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
    sourceUrl:
      'https://commons.wikimedia.org/wiki/File:%D9%85%D9%8A%D9%86%D8%A7%D8%A1_%D8%A7%D9%84%D8%AF%D9%82%D9%85_%D8%A7%D9%84%D8%AC%D8%AF%D9%8A%D8%AF.jpg',
  },
  wahiba: {
    id: 'wahiba',
    src: '/images/photos/wahiba-sands.jpg',
    width: 1600,
    height: 900,
    alt: {
      en: 'Rippled dunes of the Sharqiya (Wahiba) Sands in low evening light.',
      ar: 'كثبان رمال الشرقية (وهيبة) المتموجة في ضوء المساء.',
    },
    location: { en: 'Sharqiya (Wahiba) Sands, near Al Raka', ar: 'رمال الشرقية (وهيبة)، قرب الركة' },
    creator: 'Francesco Bini',
    license: 'CC BY-SA 4.0',
    licenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
    sourceUrl: 'https://commons.wikimedia.org/wiki/File:Al-raka,_dune_del_deserto_Sharqiya_01.jpg',
  },
  desalination: {
    id: 'desalination',
    src: '/images/photos/desalination-al-khaluf.jpg',
    width: 1400,
    height: 1050,
    alt: {
      en: 'A small containerised desalination plant with white storage tanks on a sandy coastal site.',
      ar: 'محطة تحلية صغيرة في حاويات مع خزانات بيضاء في موقع ساحلي رملي.',
    },
    location: { en: 'Al Khaluf, Al Wusta', ar: 'الخلوف، الوسطى' },
    creator: 'Starsend (English Wikipedia)',
    license: 'CC BY-SA 3.0',
    licenseUrl: 'https://creativecommons.org/licenses/by-sa/3.0/',
    sourceUrl: 'https://commons.wikimedia.org/wiki/File:Modern_Water_FO_Plant_Al_Khaluf_Oman.jpg',
  },
} as const satisfies Record<string, PhotoCredit>;

export const ALL_PHOTOS: readonly PhotoCredit[] = Object.values(PHOTOS);
