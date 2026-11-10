export function HomePage() {
  return <section className="hero">
    <div>
      <p className="eyebrow">HELLO, WORLD. HELLO, BADI.</p>
      <h1>Your next adventure.<br /><span>Stay connected.</span></h1>
      <p className="intro">Welcome to Badi eSIM. A little connection goes a long way, wherever your travels take you.</p>
      <a className="button" href="#/support">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M4 13v-1a8 8 0 0 1 16 0v1M3 12h4v6H3zM17 12h4v6h-4zM20 18v1a2 2 0 0 1-2 2h-5" /></svg>
        Contact Support
      </a>
      <p className="helper">Need a hand with your eSIM? Start here.</p>
    </div>
    <aside className="support-card">
      <span className="symbol" aria-hidden="true">↗</span>
      <h2>A helping hand,<br />wherever you land.</h2>
      <p>Get help with your connection and keep your support conversations in one place.</p>
      <a href="#/support">Visit customer support →</a>
    </aside>
  </section>
}
