import { useEffect, useState } from 'react'
import { HomePage } from './pages/HomePage'
import { SupportPage } from './pages/SupportPage'
import { FaqPage } from './pages/FaqPage'
import { AgentPage } from './pages/AgentPage'
import { ThemeToggle } from './components/ThemeToggle'
import './App.css'
import './theme.css'

// Hash URLs support refresh and browser Back/Forward without server setup.
const routes = {
  '/': { title: 'Home', component: HomePage },
  '/faq': { title: 'Frequently asked questions', component: FaqPage },
  '/support': { title: 'Customer support', component: SupportPage },
  // Staff open this URL directly. AgentPage checks the session before loading
  // tickets; FastAPI also checks authorization on every ticket request.
  '/admin': { title: 'Administration', component: AgentPage },
  '/agent': { title: 'Agent dashboard', component: AgentPage },
}

export default function App() {
  const [path, setPath] = useState(() => location.hash.slice(1) || '/')
  useEffect(() => {
    const navigate = () => setPath(location.hash.slice(1) || '/')
    window.addEventListener('hashchange', navigate)
    return () => window.removeEventListener('hashchange', navigate)
  }, [])
  const route = routes[path as keyof typeof routes]
  const Page = route?.component
  useEffect(() => {
    document.title = `${route?.title ?? 'Page not found'} | Badi eSIM`
    document.documentElement.dataset.workspace = ['/agent', '/admin'].includes(path) ? 'staff' : 'public'
    window.scrollTo(0, 0)
    document.getElementById('content')?.focus()
  }, [path, route])
  return <div className={`app-shell ${['/agent', '/admin'].includes(path) ? 'workspace-shell' : ''}`}>
    {!['/agent', '/admin'].includes(path) && <header>
      <a className="brand" href="#/" aria-label="Badi eSIM home">badi <span>eSIM</span></a>
      <nav aria-label="Main navigation">
        <a href="#/" aria-current={path === '/' ? 'page' : undefined}>Home</a>
        <a href="#/support" aria-current={path === '/support' ? 'page' : undefined}>Support</a>
        <a href="#/faq" aria-current={path === '/faq' ? 'page' : undefined}>FAQ</a>
      </nav>
    </header>}
    <div className="appearance-tools"><ThemeToggle /></div>
    <main id="content" tabIndex={-1}>{Page ? <Page /> : <section><h1>Page not found</h1><a href="#/">Back to home</a></section>}</main>
    {!['/agent', '/admin'].includes(path) && <footer>Badi eSIM · Stay connected, wherever you go.</footer>}
  </div>
}
