/** The one place that turns a row into the state a person sees.
 *
 * `needs_review` is a flag, orthogonal to the status enum, and the enum stays exactly
 * `Available | In Use | Repair` — the brief fixes it and ADR-0002 depends on it staying
 * closed. "In Review" therefore exists only in the display layer, which means it has no
 * natural position in a sort over stored statuses and cannot get one by adding a value.
 *
 * Two different orderings live here and they are not the same list:
 *
 * - `displayState` resolves **which state wins** when more than one is true of a row —
 *   `In Repair > Rented > In Review > Available`. A rented item that is also flagged
 *   shows as Rented, because who holds it is the more actionable fact.
 * - `SORT_ORDER` is the order those resolved states appear **down the page** on first
 *   load — `Available → Rented → In Repair → In Review`, working from what an employee
 *   can act on toward what an admin has to deal with.
 *
 * Both the chip and the table read `displayState`, so the label a row shows and the group
 * it sorts into cannot disagree. That was the actual risk: a second copy of this rule in
 * the table would have drifted the first time either list changed.
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
