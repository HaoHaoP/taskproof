/**
 * Inline SVG icons, copied verbatim from the prototype's `ICONS` map
 * (taskproof-work/prototypes/desktop-app-v3.html). Apple-style thin strokes;
 * every path keeps its own `stroke="currentColor"` so the caller's colour wins.
 *
 * Only the six icons the app shell needs live here -- the other prototype icons
 * are introduced by the sections that first use them.
 */
export const ICONS = {
  matrix:
    '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3"><rect x="1.6" y="1.6" width="5.2" height="5.2" rx="1.4"/><rect x="9.2" y="1.6" width="5.2" height="5.2" rx="1.4"/><rect x="1.6" y="9.2" width="5.2" height="5.2" rx="1.4"/><rect x="9.2" y="9.2" width="5.2" height="5.2" rx="1.4"/></svg>',
  projects:
    '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3"><path d="M1.8 4.6c0-.8.6-1.4 1.4-1.4h2.3l1.3 1.5h6c.8 0 1.4.6 1.4 1.4v5.3c0 .8-.6 1.4-1.4 1.4H3.2c-.8 0-1.4-.6-1.4-1.4V4.6z"/></svg>',
  tasks:
    '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"><path d="M5.2 4.2h9M5.2 8h9M5.2 11.8h9"/><circle cx="2.4" cy="4.2" r="1"/><circle cx="2.4" cy="8" r="1"/><circle cx="2.4" cy="11.8" r="1"/></svg>',
  settings:
    '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3"><circle cx="8" cy="8" r="2.3"/><path d="M8 1.6v1.7M8 12.7v1.7M14.4 8h-1.7M3.3 8H1.6M12.5 3.5l-1.2 1.2M4.7 11.3l-1.2 1.2M12.5 12.5l-1.2-1.2M4.7 4.7L3.5 3.5" stroke-linecap="round"/></svg>',
  collapse:
    '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3"><rect x="1.6" y="2.4" width="12.8" height="11.2" rx="2.2"/><path d="M6.4 2.4v11.2"/><path d="M10.6 6.4L8.9 8l1.7 1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  expand:
    '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3"><rect x="1.6" y="2.4" width="12.8" height="11.2" rx="2.2"/><path d="M6.4 2.4v11.2"/><path d="M9 6.4L10.7 8L9 9.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
} as const

export type IconName = keyof typeof ICONS
