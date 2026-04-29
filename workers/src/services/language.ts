const LANG_PATTERNS = [
  { name: 'German', words: ['der', 'die', 'das', 'und', 'ist', 'von', 'den', 'des', 'dem', 'ein', 'eine', 'ich', 'du', 'er', 'sie', 'es', 'nicht', 'mit', 'auf', 'für', 'auch', 'als', 'nach', 'bei', 'oder', 'dass', 'wird', 'nur', 'wenn', 'aber', 'wie', 'zum', 'noch', 'über', 'dieser', 'diese', 'dieses'] },
  { name: 'English', words: ['the', 'and', 'is', 'of', 'to', 'a', 'in', 'that', 'it', 'for', 'on', 'with', 'as', 'this', 'was', 'are', 'be', 'at', 'or', 'an', 'but', 'by', 'from', 'not', 'you', 'have', 'we', 'they', 'will', 'would', 'could', 'should'] },
  { name: 'Spanish', words: ['el', 'la', 'de', 'que', 'y', 'en', 'un', 'es', 'se', 'no', 'lo', 'le', 'los', 'del', 'las', 'por', 'para', 'con', 'su', 'una', 'al', 'como', 'más', 'este', 'si', 'sobre', 'entre'] },
  { name: 'French', words: ['le', 'de', 'et', 'les', 'des', 'un', 'est', 'que', 'la', 'du', 'en', 'une', 'se', 'pas', 'pour', 'dans', 'par', 'son', 'au', 'ce', 'qui', 'il', 'sont', 'comme', 'avec', 'sur', 'mais', 'cette', 'nous'] },
];

export function detectLanguage(text: string): string {
  const words = text.toLowerCase().split(/\s+/);
  if (words.length < 3) return 'English';

  let bestLang = 'English';
  let bestScore = 0;

  for (const lang of LANG_PATTERNS) {
    const matches = words.filter(w => lang.words.includes(w)).length;
    const score = matches / words.length;
    if (score > bestScore) {
      bestScore = score;
      bestLang = lang.name;
    }
  }

  return bestScore > 0.05 ? bestLang : 'English';
}
