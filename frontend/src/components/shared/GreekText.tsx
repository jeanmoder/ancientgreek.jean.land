import type { ReactNode } from 'react'

interface GreekTextProps {
  children: ReactNode
  className?: string
}

/**
 * NFC-normalizes any string children and renders them in a Greek-appropriate
 * serif font with generous line-height for diacritics.
 */
export function GreekText({ children, className = '' }: GreekTextProps) {
  const normalized = typeof children === 'string' ? children.normalize('NFC') : children

  return (
    <span
      lang="grc"
      className={`font-greek ${className}`.trim()}
      style={{
        lineHeight: 2,
        fontSize: '1.25em',
      }}
    >
      {normalized}
    </span>
  )
}
