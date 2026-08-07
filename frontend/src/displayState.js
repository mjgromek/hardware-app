/** The one place that turns a row into the state a person sees. "In Review" exists
 * only in the display layer — the stored enum stays closed (ADR-0002). Two distinct
 * orderings: PRECEDENCE resolves which state wins on a row; SORT_ORDER is the order
 * down the page. Chip and table both read this, so they cannot disagree.
 */

//: Resolution precedence. First match wins.
const PRECEDENCE = [
  (item) => (item.status === 'Repair' ? 'In Repair' : null),
  (item) => (item.status === 'In Use' ? 'Rented' : null),
  (item) => (item.needs_review ? 'In Review' : null),
]

/** The state to show for a row: `Available` | `Rented` | `In Repair` | `In Review`. */
export function displayState(item) {
  for (const test of PRECEDENCE) {
    const hit = test(item)
    if (hit) return hit
  }
  return item.status === 'Available' ? 'Available' : item.status
}

//: Top-to-bottom order on first load.
const SORT_ORDER = ['Available', 'Rented', 'In Repair', 'In Review']

/** Sort rank for a row's display state. Unknown states sort last rather than first, so a
 *  status this file has not been taught about cannot silently take the top of the table. */
export function displayRank(item) {
  const position = SORT_ORDER.indexOf(displayState(item))
  return position === -1 ? SORT_ORDER.length : position
}
