import { FaqPanel } from '../components/FaqPanel'

export function FaqPage() {
  return <section className="faq-page">
    <div className="support-hero"><p className="eyebrow">BADI HELP & CARE</p><h1>A little help<br /><em>for your journey.</em></h1><p>Find answers about your Badi eSIM. If you still need a hand, our support team is here for you.</p><a className="button" href="#/support">Connect with Us</a></div>
    <FaqPanel />
  </section>
}
