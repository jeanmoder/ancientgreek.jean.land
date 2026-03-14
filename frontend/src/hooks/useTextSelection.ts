import { useState, useEffect, useCallback } from 'react'
import type { PerseusParseContext } from '../api/client'

interface TextSelection {
  text: string
  x: number
  y: number
  parseContext?: PerseusParseContext
}

const GREEK_WORD_RE = /[\u0370-\u03FF\u1F00-\u1FFF]+/g

function extractLastGreekToken(text: string): string | undefined {
  const matches = text.match(GREEK_WORD_RE)
  if (!matches || matches.length === 0) return undefined
  return matches[matches.length - 1]
}

export function useTextSelection() {
  const [selection, setSelection] = useState<TextSelection | null>(null)

  const handleMouseUp = useCallback(() => {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || !sel.toString().trim()) {
      // Don't clear immediately - let the popup click handler fire first
      return
    }

    const text = sel.toString().trim()

    // Check if selection is within or near a lang="grc" element
    const anchorNode = sel.anchorNode
    if (!anchorNode) return

    const element =
      anchorNode.nodeType === Node.ELEMENT_NODE
        ? (anchorNode as Element)
        : anchorNode.parentElement

    if (!element) return

    // Check if the element or any ancestor has lang="grc"
    const greekParent = element.closest('[lang="grc"]')
    // Also check if the text contains Greek characters (Unicode range)
    const hasGreek = /[\u0370-\u03FF\u1F00-\u1FFF]/.test(text)

    if (!greekParent && !hasGreek) return

    const range = sel.getRangeAt(0)
    const rect = range.getBoundingClientRect()
    const parseContext: PerseusParseContext = {}

    const greekLine = element.closest('[data-greek-line]')
    if (greekLine) {
      try {
        const prefixRange = document.createRange()
        prefixRange.selectNodeContents(greekLine)
        prefixRange.setEnd(range.startContainer, range.startOffset)
        const prior = extractLastGreekToken(prefixRange.toString())
        if (prior) parseContext.prior = prior
      } catch {
        // Ignore range failures and proceed without prior.
      }

      const docRef = greekLine.getAttribute('data-perseus-d')
      if (docRef) parseContext.d = docRef

      const canRef = greekLine.getAttribute('data-perseus-can')
      if (canRef) parseContext.can = canRef

      const indexRaw = greekLine.getAttribute('data-perseus-i')
      if (indexRaw && !Number.isNaN(Number(indexRaw))) {
        parseContext.i = Number(indexRaw)
      }
    }

    setSelection({
      text,
      x: rect.left + rect.width / 2,
      y: rect.top - 10,
      parseContext: Object.keys(parseContext).length > 0 ? parseContext : undefined,
    })
  }, [])

  const clearSelection = useCallback(() => {
    setSelection(null)
  }, [])

  useEffect(() => {
    document.addEventListener('mouseup', handleMouseUp)

    // Clear selection when clicking outside the popup
    const handleMouseDown = (e: MouseEvent) => {
      const target = e.target as Element
      if (!target.closest('[data-highlight-popup]')) {
        setSelection(null)
      }
    }
    document.addEventListener('mousedown', handleMouseDown)

    return () => {
      document.removeEventListener('mouseup', handleMouseUp)
      document.removeEventListener('mousedown', handleMouseDown)
    }
  }, [handleMouseUp])

  return { selection, clearSelection }
}
