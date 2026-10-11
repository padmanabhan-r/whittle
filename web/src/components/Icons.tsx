import type { ReactNode } from 'react'

function Icon({ children, size = 16 }: { children: ReactNode; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  )
}

export const ArrowRight = () => <Icon><path d="M2.5 8h11M9 3.5 13.5 8 9 12.5" /></Icon>
export const Download = () => <Icon><path d="M8 2v8.5M4.5 7 8 10.5 11.5 7M2.5 13.5h11" /></Icon>
export const Branch = () => (
  <Icon>
    <circle cx="4" cy="3.5" r="1.5" /><circle cx="4" cy="12.5" r="1.5" /><circle cx="12" cy="5.5" r="1.5" />
    <path d="M4 5v6M12 7c0 3-8 1.5-8 4" />
  </Icon>
)
export const External = () => <Icon size={13}><path d="M6 3H3v10h10v-3M9 3h4v4M13 3 7.5 8.5" /></Icon>
export const Undo = () => <Icon size={18}><path d="M3 6.5h6.5a3.5 3.5 0 0 1 0 7H6M3 6.5 6 3.5M3 6.5l3 3" /></Icon>
export const Warn = () => <Icon size={18}><path d="M8 2 1.5 13.5h13L8 2ZM8 6.5v3.2M8 11.6v.1" /></Icon>

/** The Whittle mark: one shaving curling off the cut. Takes the text colour around it. */
export function Mark({ size = 22 }: { size?: number }) {
  return (
    <svg className="mark" width={size} height={size} viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 26h11a8 8 0 1 0-8-8a4 4 0 1 0 4-4" />
    </svg>
  )
}
