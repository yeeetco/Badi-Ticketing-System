import { useEffect, useState } from 'react'
import { HomePage } from './pages/HomePage'
import { SupportPage } from './pages/PlaceholderPages'
import { AgentPage } from './pages/AgentPage'
import './App.css'

// Hash URLs support refresh and browser Back/Forward without server setup.
const routes = {
  '/': { title: 'Home', component: HomePage },
  '/support': { title: 'Customer support', component: SupportPage },
  // Staff open this URL directly. AgentPage checks the session before loading
  // tickets; FastAPI also checks authorization on every ticket request.
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
    window.scrollTo(0, 0)
    document.getElementById('content')?.focus()
  }, [path, route])
  return <div className="app-shell">
    <header>
      <a className="brand" href="#/" aria-label="Badi eSIM home">badi <span>eSIM</span></a>
      <nav aria-label="Main navigation">
        <a href="#/" aria-current={path === '/' ? 'page' : undefined}>Home</a>
        <a href="#/support" aria-current={path === '/support' ? 'page' : undefined}>Contact Support</a>
      </nav>
    </header>
    <main id="content" tabIndex={-1}>{Page ? <Page /> : <section><h1>Page not found</h1><a href="#/">Back to home</a></section>}</main>
    <footer>Badi eSIM · Stay connected, wherever you go.</footer>
  </div>
}
