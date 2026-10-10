import { useEffect, useRef, useState } from 'react'

/** Counts toward the value so a changing cost reads as a meter, not a swap. */
export function AnimatedNumber({ value, format }: { value: number; format: (n: number) => string }) {
  const [shown, setShown] = useState(value)
  const from = useRef(value)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setShown(value)
      from.current = value
      return
    }
    const start = from.current
    const began = performance.now()
    let frame = 0
    const tick = (now: number) => {
      const t = Math.max(0, Math.min(1, (now - began) / 420))
      const eased = 1 - Math.pow(1 - t, 4)
      const current = start + (value - start) * eased
      from.current = current
      setShown(current)
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [value])

  return <span className="num">{format(shown)}</span>
}
