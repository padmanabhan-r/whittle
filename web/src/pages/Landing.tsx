import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from '../components/Icons'
import '../styles/landing.css'

type Line = [n: string, kind: string, call: string, tokens: string, usd: string, why?: string, why2?: string]

// Sample lines, written to add up: the model lines in each list sum to the total printed below it.
const BEFORE: Line[] = [
  ['01', 'model', 'classify', '4,200', '0.0290', 'oversized model', 'reverted, kept'],
  ['02', 'tool', 'search', '0', '0.0000'],
  ['03', 'model', 'plan', '6,100', '0.0345', '~changing cache prefix'],
  ['04', 'tool', 'fetch_page', '0', '0.0000'],
  ['05', 'model', 'read page', '8,000', '0.0380'],
  ['06', 'tool', 'search', '0', '0.0000', 'duplicate tool call'],
  ['07', 'model', 'read results', '9,900', '0.0535', 'duplicate tool call'],
  ['08', 'tool', 'fetch_page', '0', '0.0000'],
  ['09', 'model', 'read page', '11,800', '0.0440', '~context bloat'],
  ['10', 'tool', 'fetch_page', '0', '0.0000', 'doomed retry'],
  ['11', 'model', 'retry', '7,400', '0.0210', 'doomed retry'],
  ['12', 'tool', 'fetch_page', '0', '0.0000', 'doomed retry'],
  ['13', 'model', 'retry', '7,400', '0.0210', 'doomed retry'],
  ['14', 'tool', 'cite', '0', '0.0000'],
  ['15', 'model', 'draft', '10,600', '0.0380'],
  ['16', 'model', 'write answer', '11,200', '0.0353'],
]

const AFTER: Line[] = [
  ['01', 'model', 'classify', '4,200', '0.0290'],
  ['02', 'tool', 'search', '0', '0.0000'],
  ['03', 'model', 'plan', '6,100', '0.0118'],
  ['04', 'tool', 'fetch_page', '0', '0.0000'],
  ['05', 'model', 'read page', '5,300', '0.0196'],
  ['06', 'tool', 'fetch_page', '0', '0.0000'],
  ['07', 'model', 'read page', '6,200', '0.0212'],
  ['08', 'tool', 'cite', '0', '0.0000'],
  ['09', 'model', 'draft', '7,000', '0.0236'],
  ['10', 'model', 'write answer', '7,400', '0.0244'],
]

const FINDINGS = ['changing cache prefix', 'context bloat', 'duplicate tool call', 'oversized model', 'doomed retry']

const STEPS = [
  { title: 'Baseline', text: 'We run your agent in a clean sandbox and capture a full trace of every model and tool call.', icon: <><path d="M4 22a12 12 0 1 1 24 0" /><path d="M16 22l5-8" /><circle cx="16" cy="22" r="1.6" /><path d="M4 27h24" /></> },
  { title: 'Findings', text: 'Whittle analyzes the trace to find waste and ranks the top opportunities by impact and confidence.', icon: <><circle cx="14" cy="14" r="9" /><path d="M21 21l7 7" /></> },
  { title: 'Fix and verify', text: 'We apply precise code changes, rerun the agent, and re-measure to confirm the improvement.', icon: <><rect x="3" y="6" width="26" height="20" rx="2" /><path d="M12 12l-4 4 4 4M20 12l4 4-4 4M17 11l-2 10" /></> },
  { title: 'Proof', text: 'You get side-by-side traces and metrics that prove what was saved—without losing quality.', icon: <><path d="M3 28h26M7 28V16h4v12M14 28V8h4v20M21 28V13h4v15" /></> },
]

const KINDS = [
  { name: 'changing cache prefix', what: 'A timestamp or an id at the top of the system prompt makes every request unique, so the same instructions are paid for in full on every call.', proof: 'No cache-read tokens on any call; the first bytes of the prompt differ between calls.', fix: 'Cache the part that never changes and move the rest after it.' },
  { name: 'context bloat', what: 'Whole tool results stay in the conversation and are sent again on every turn, long after anything refers to them.', proof: 'Input tokens climb turn after turn; old results make up most of the last request.', fix: 'Keep recent results whole and shorten the older ones.' },
  { name: 'duplicate tool call', what: 'The agent calls the same tool with the same arguments twice in one run, and pays for a model turn each time.', proof: 'Two identical tool calls inside one trace.', fix: 'Remember the first answer for the rest of the run.' },
  { name: 'oversized model', what: 'A simple step, such as choosing a category, runs on the largest model.', proof: 'A few tokens of structured output from the top tier.', fix: 'Send that step to a smaller model, and keep the change only if the answers hold.' },
  { name: 'doomed retry', what: 'A request that failed is sent again unchanged, two or three times, before the agent gives up.', proof: 'Identical requests, each ending in the same error.', fix: 'Stop on errors that cannot succeed, or change the request first.' },
]

// A waste name with a leading "~" marks a call that stays and gets cheaper: named, not struck.
function Rows({ lines, offset }: { lines: Line[]; offset: number }) {
  return (
    <>
      {lines.map(([n, kind, call, tokens, usd, why, why2], i) => (
        <div className={`rline ${why ? (why.startsWith('~') ? 'noted' : 'cut') : ''}`} key={n} style={{ '--i': offset + i } as React.CSSProperties}>
          <span className="cells">
            <span>{n}</span><span>{kind}</span><span>{call}</span><span className="r">{tokens}</span><span className="r">{usd}</span>
          </span>
          {why && <span className="why">{why.replace('~', '')}{why2 && <><br />{why2}</>}</span>}
        </div>
      ))}
    </>
  )
}

export function Landing() {
  // The print animation runs under a class that is always removed, so the receipt can never stay hidden.
  const [printing, setPrinting] = useState(true)
  useEffect(() => {
    const timer = window.setTimeout(() => setPrinting(false), 4200)
    return () => window.clearTimeout(timer)
  }, [])

  return (
    <div className={`landing ${printing ? 'printing' : ''}`}>
      <div className="frame">
        <header className="nav">
          <Link className="r-logo logo" to="/">Whittle</Link>
          <nav aria-label="Main">
            <a className="r-nav-how" href="#how">How it works</a>
            <a className="r-nav-findings" href="#findings">Findings</a>
            <a className="r-nav-github" href="https://github.com/padmanabhan-r/whittle">GitHub</a>
          </nav>
          <Link className="r-nav-open open" to="/app">Open the app</Link>
        </header>

        <main className="hero">
          <h1>
            <span className="r-headline-black">Cut what your agent wastes.</span>{' '}
            <span className="r-headline-blue">Prove what you saved.</span>
          </h1>
          <p className="r-lede lede">
            Point Whittle at your agent&rsquo;s repo. It finds the waste, fixes the code, and shows the before and after.
          </p>
          <Link className="r-cta cta" to="/app">Run a sample agent <ArrowRight /></Link>
          <Link className="r-cta-link cta-link" to="/app">Paste your own repo</Link>

          <div className="receipt" role="img" aria-label="Sample run receipt: 16 calls before, 10 after. Wasted calls are struck through. Total before $0.3143, total after $0.1296.">
            <img className="r-receipt-paper paper" src="/plates/receipt-paper.png" alt="" />
            <div className="r-receipt-head rblock" aria-hidden="true">
              <div className="rtitle">WHITTLE SAMPLE RUN</div>
              <div className="rule" />
              <div className="rline head"><span className="cells"><span>STEP</span><span>CALL</span><span /><span className="r">TOKENS</span><span className="r">COST (USD)</span></span></div>
              <div className="rule" />
            </div>
            <div className="r-receipt-before rblock" aria-hidden="true">
              <div className="rline label" style={{ '--i': 0 } as React.CSSProperties}>INITIAL RUN (BEFORE)</div>
              <Rows lines={BEFORE} offset={1} />
              <div className="rule" />
            </div>
            <div className="r-receipt-after rblock" aria-hidden="true">
              <div className="rline label" style={{ '--i': 18 } as React.CSSProperties}>OPTIMIZED RUN (AFTER)</div>
              <Rows lines={AFTER} offset={19} />
              <div className="rule" />
            </div>
            <div className="r-receipt-totals rblock totals" aria-hidden="true">
              <div className="rline" style={{ '--i': 30 } as React.CSSProperties}><span>TOTAL BEFORE</span><s>$0.3143</s></div>
              <div className="rline" style={{ '--i': 31 } as React.CSSProperties}><span>TOTAL AFTER</span><mark>$0.1296</mark></div>
            </div>
          </div>

          <h2 className="r-sample-title sample-title">Sample run</h2>
          <section className="r-card-cost card cost" aria-label="Cost per run">
            <h3>Cost per run (USD)</h3>
            <div className="trio">
              <div><span className="k">BEFORE</span><span className="v">$0.3143</span></div>
              <div className="chip"><span className="pc"><svg viewBox="0 0 12 14" aria-hidden="true"><path d="M6 1v11M1.5 8 6 12.5 10.5 8" /></svg>58.8%</span><span>LOWER</span></div>
              <div><span className="k">AFTER</span><span className="v">$0.1296</span></div>
            </div>
          </section>
          <section className="r-card-quality card quality" aria-label="Answer quality">
            <h3>Answer quality <span>(score)</span></h3>
            <div className="trio">
              <div><span className="k">BEFORE</span><span className="v">0.92</span></div>
              <svg className="arrow" viewBox="0 0 24 16" aria-hidden="true"><path d="M2 8h19M15 2.5 21 8l-6 5.5" /></svg>
              <div><span className="k">AFTER</span><span className="v">0.91</span></div>
            </div>
          </section>
          <section className="r-card-findings card findings" id="findings-list" aria-label="Waste findings">
            <h3>5 waste findings</h3>
            <ol>
              {FINDINGS.map((name, i) => (
                <li key={name}><span className="n">{i + 1}</span>{name}{name === 'oversized model' && <span className="rev">reverted</span>}</li>
              ))}
            </ol>
          </section>
        </main>
      </div>

      <section className="how" id="how">
        <h2 className="how-title">How it works</h2>
        <ol className="steps4">
          {STEPS.map((step, i) => (
            <li key={step.title}>
              <span className="n">{i + 1}</span>
              <svg className="ico" viewBox="0 0 32 32" aria-hidden="true">{step.icon}</svg>
              <div><h3>{step.title}</h3><p>{step.text}</p></div>
            </li>
          ))}
        </ol>
      </section>

      <section className="lower kinds" id="findings">
        <h2>The waste it looks for</h2>
        <p className="intro">
          Five kinds so far, with more to come. Whittle reports only what the traces show: every finding links to the
          calls behind it and to the place in your code.
        </p>
        <div className="ktable" role="table" aria-label="Kinds of waste">
          <div className="krow khead" role="row">
            <span role="columnheader">Waste</span><span role="columnheader">What happens</span>
            <span role="columnheader">How it is proven</span><span role="columnheader">The fix</span>
          </div>
          {KINDS.map((kind, i) => (
            <div className="krow" role="row" key={kind.name}>
              <span role="cell" className="kname"><span className="n">{i + 1}</span>{kind.name}</span>
              <span role="cell">{kind.what}</span>
              <span role="cell">{kind.proof}</span>
              <span role="cell">{kind.fix}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="lower revert">
        <div>
          <h2>A fix that hurts the answers is taken back out</h2>
          <p>
            After each patch, Whittle reruns the same tasks and scores the answers against the baseline. A fix that
            saves money and lowers quality is reverted, and you watch it happen. In the sample run, moving one step to
            a smaller model failed that check, so the line was struck and then kept.
          </p>
        </div>
        <div className="slip" aria-hidden="true">
          <div><s>01  model  classify     4,200  0.0290</s></div>
          <div className="note">oversized model: quality 0.92 → 0.71</div>
          <div className="note">below 0.85. reverted, kept.</div>
          <div><mark>01  model  classify     4,200  0.0290</mark></div>
        </div>
      </section>

      <section className="lower leave">
        <h2>What you leave with</h2>
        <dl>
          <div><dt>Two traces per task</dt><dd>Before and after, recorded in neatlogs, with tokens, cache use and cost on every call.</dd></div>
          <div><dt>The diff</dt><dd>Only the fixes that passed. Whittle finds the call sites with Entire and checks what each change touches.</dd></div>
          <div><dt>A patch or a pull request</dt><dd>Download the patch, or have Whittle open a pull request with the numbers in its description.</dd></div>
          <div><dt>The monthly figure</dt><dd>Your runs per month turn the saving per run into a number for the budget, ready for a cfo.ai plan.</dd></div>
        </dl>
      </section>

      <section className="closing">
        <h2>See a run cut down, line by line.</h2>
        <Link className="cta2" to="/app">Run a sample agent <ArrowRight /></Link>
        <p>The sample is a scripted run with invented figures. It shows how Whittle works, not a measured result.</p>
      </section>

      <footer className="foot">
        <span className="logo2">Whittle</span>
        <span>Built for neatHack 2026 by team Attention Heads</span>
        <a href="https://github.com/padmanabhan-r/whittle">GitHub</a>
      </footer>
    </div>
  )
}
