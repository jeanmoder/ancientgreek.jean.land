const GREEK_CHAR_RE = /[\u0370-\u03FF\u1F00-\u1FFF]/

function hasGreek(text: string): boolean {
  return GREEK_CHAR_RE.test(text)
}

function normalizeTitle(text: string | null | undefined): string {
  return (text ?? '').trim()
}

export function formatTextDisplayTitle(title: string, teiTitle?: string | null): string {
  const primary = normalizeTitle(title)
  const secondary = normalizeTitle(teiTitle)

  const candidates = [primary, secondary].filter((value, idx, arr) => {
    if (!value) return false
    return arr.indexOf(value) === idx
  })

  if (candidates.length === 0) return 'Untitled'
  if (candidates.length === 1) return candidates[0]

  const nonGreek = candidates.find((candidate) => !hasGreek(candidate))
  const greek = candidates.find((candidate) => hasGreek(candidate))

  if (nonGreek && greek && nonGreek !== greek) {
    return `${nonGreek} [${greek}]`
  }

  return `${candidates[0]} [${candidates[1]}]`
}
