import type { ReactNode } from 'react'

const shapes = {
  chart: <><path d="M4 4v16h16M8 15l4-5 4 3 4-7" /></>,
  robot: <><rect x="4" y="7" width="16" height="13" rx="4" /><path d="M12 3v4M1 12v4m22-4v4M9 16h6" /><circle cx="8" cy="12" r=".7" /><circle cx="16" cy="12" r=".7" /></>,
  sliders: <><path d="M4 6h5m4 0h7M4 12h10m4 0h2M4 18h3m4 0h9" /><circle cx="11" cy="6" r="2" /><circle cx="16" cy="12" r="2" /><circle cx="9" cy="18" r="2" /></>,
  model: <><path d="m12 3 9 5-9 5-9-5 9-5Zm-9 5v9l9 5 9-5V8M12 13v9" /></>,
  feedback: <><path d="M20 11V5a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v14l4-3h5m2-1 2 2 5-5M8 7h8M8 11h4" /></>,
  panel: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></>,
  arrow: <><path d="M4 12h16m-6-6 6 6-6 6" /></>,
  chevron: <path d="m9 5 7 7-7 7" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10v1" /></>,
  history: <><path d="M3 11a9 9 0 1 1 3 8M3 4v7h7m2-4v6l4 2" /></>,
  star: <path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9L12 3Z" />,
} satisfies Record<string, ReactNode>

export type IconName = keyof typeof shapes

export function Icon({ name }: { name: IconName }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {shapes[name]}
    </svg>
  )
}
