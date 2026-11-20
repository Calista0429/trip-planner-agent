/** One nearby place from the comic service's points-of-interest text. */
export interface PointOfInterest {
  name: string
  note: string
}

/**
 * Parses the model's Markdown list of nearby places ("- **Name**: why it's worth it")
 * into plain strings. The result is rendered with text interpolation, never as HTML,
 * so model output can't inject markup. Lines that aren't list items are skipped.
 */
export function parsePointsOfInterest(text: string): PointOfInterest[] {
  return (text || '')
    .split('\n')
    .map(line => line.trim())
    .filter(line => /^[-*•]\s+/.test(line))
    .map(line => {
      const item = line.replace(/^[-*•]\s+/, '')
      const bold = item.match(/^\*\*(.+?)\*\*\s*[:：-]?\s*(.*)$/)
      if (bold) return { name: bold[1].trim(), note: stripMarkdown(bold[2]) }
      const colon = item.match(/^([^:：]+)[:：]\s*(.*)$/)
      if (colon) return { name: stripMarkdown(colon[1]), note: stripMarkdown(colon[2]) }
      return { name: stripMarkdown(item), note: '' }
    })
    .filter(poi => poi.name)
}

function stripMarkdown(text: string): string {
  return text
    .replace(/\[([^\]]*)\]\((?:[^()]|\([^()]*\))*\)/g, '$1') // [label](url) -> label
    .replace(/[*_`]+/g, '')
    .trim()
}
