import { Outlet, NavLink } from 'react-router-dom'
import { useProfile } from './ProfileContext'
import './Layout.css'

export default function Layout() {
  const { currentProfile } = useProfile()
  return (
    <div className="layout">
      <header className="header">
        <NavLink to="/" className="logo">mantracker v3.0</NavLink>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/accounts">Accounts</NavLink>
          <span className="profile-name">{currentProfile?.name}</span>
          <NavLink to="/profiles" className="nav-link">Manage profiles</NavLink>
        </nav>
      </header>
      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
