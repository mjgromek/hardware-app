<script setup>
// Inline SVG rather than an icon package: nine glyphs do not justify a dependency,
// and the bundle is served from the same Python process as the API (ADR-0001) — a
// CDN icon font would be the only cross-origin request in the app.
const paths = {
  box: 'M21 8v8l-9 5-9-5V8l9-5 9 5Zm-9 5 9-5m-9 5-9-5m9 5v9',
  list: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
  gear: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-3a7.4 7.4 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7.5 7.5 0 0 0-2-1.2L14.5 2h-4l-.4 2.6a7.5 7.5 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7.5 7.5 0 0 0 2 1.2l.4 2.6h4l.4-2.6a7.5 7.5 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.06-.4.1-.8.1-1.2Z',
  flag: 'M4 21V4m0 0h11l-1.5 4L15 12H4',
  // Tabler `tool` — the wrench that means Repair. The previous path was a loose
  // approximation that read as a paintbrush at 16px.
  wrench: 'M7 10h3v3l-3.5 3.5a2.1 2.1 0 0 1-3-3L7 10Zm0 0V7l3-3 3 3-3 3m2 5 5.5 5.5a2.1 2.1 0 0 0 3-3L15 12',
  // Tabler `pencil` — Edit.
  pencil: 'M4 20h4L18.5 9.5a2.1 2.1 0 0 0-3-3L5 17v3ZM13.5 6.5l3 3',
  // Tabler `sun` / `moon` — the theme toggle.
  sun: 'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0-14v2m0 14v2M5.6 5.6l1.4 1.4m10 10 1.4 1.4M3 12h2m14 0h2M5.6 18.4 7 17m10-10 1.4-1.4',
  moon: 'M12 3a9 9 0 1 0 9 9 6.5 6.5 0 0 1-9-9Z',
  search: 'M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14Zm11 4-6-6',
  sparkle: 'M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3Z',
  bell: 'M10 5a2 2 0 1 1 4 0 7 7 0 0 1 4 6v3a4 4 0 0 0 2 3H4a4 4 0 0 0 2-3v-3a7 7 0 0 1 4-6M9 17v1a3 3 0 0 0 6 0v-1',
  'bell-off': 'M9 7a5 5 0 0 1 8 4v3a4 4 0 0 0 2 3H8m-2.5 0H4a4 4 0 0 0 2-3v-3a7 7 0 0 1 .5-2.5M9 17v1a3 3 0 0 0 6 0v-1M3 3l18 18',
  alert: 'M12 8v5m0 3h.01M10.2 3.9 2.3 17a2 2 0 0 0 1.7 3h16a2 2 0 0 0 1.7-3L13.8 3.9a2 2 0 0 0-3.6 0Z',
  _wrench_old: 'M14.7 6.3a4 4 0 0 0 5 5L21 13l-8 8-2-2-6 2-2-2 2-6-2-2 8-8 1.7 1.3Z',
  trash: 'M4 7h16M10 11v6m4-6v6M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2l1-12M9 7V4h6v3',
  plus: 'M12 5v14M5 12h14',
  out: 'M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l-5-5 5-5M5 12h11',
  check: 'M20 6 9 17l-5-5',
  info: 'M12 8h.01M11 12h1v5h1',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-13v5l3.5 2',
}

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 16 },
})
</script>

<template>
  <svg
    :width="props.size"
    :height="props.size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <path :d="paths[props.name]" />
  </svg>
</template>
