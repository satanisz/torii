import { useCallback, useEffect, useReducer, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { api, asApiError } from './api/client';
import type { ApiError } from './api/client';
import { isUuid } from './api/types';
import type { Session } from './api/types';
import { ErrorPanel, Loading } from './components';
import { text } from './i18n/pl';
import { ProjectPage } from './ProjectPage';
import { Projects } from './Projects';
import { confirmDiscard, SessionContext } from './state';

type AuthState = { status: 'loading' | 'anonymous' | 'expired' | 'logging-out' } |
  { status: 'ready'; session: Session } | { status: 'error'; error: ApiError } |
  { status: 'logout-failed'; csrf: string; error: ApiError };

export function App() {
  const [auth, setAuth] = useState<AuthState>({ status: 'loading' });
  const [revision, reload] = useReducer((n: number) => n + 1, 0);
  const location = useLocation();
  const expire = useCallback(() => setAuth({ status: 'expired' }), []);
  useEffect(() => {
    const controller = new AbortController();
    setAuth({ status: 'loading' });
    void api.session(controller.signal).then(({ data }) => {
      if (!controller.signal.aborted) setAuth({ status: 'ready', session: data });
    }).catch((error: unknown) => {
      if (controller.signal.aborted) return;
      const problem = asApiError(error);
      setAuth(problem.status === 401 ? { status: 'anonymous' } : { status: 'error', error: problem });
    });
    return () => controller.abort();
  }, [revision]);
  async function logout(csrf: string) {
    if (!confirmDiscard()) return;
    setAuth({ status: 'logging-out' });
    try { await api.logout(csrf); setAuth({ status: 'anonymous' }); }
    catch (error) {
      const problem = asApiError(error);
      setAuth(problem.status === 401 ? { status: 'anonymous' } : { status: 'logout-failed', csrf, error: problem });
    }
  }
  const authenticated = auth.status === 'ready';
  return <div className={authenticated ? 'app-shell' : 'guest-shell'}>
    <a className="skip-link" href="#main-content">{text.skip}</a>
    {authenticated && <aside className="sidebar"><Link className="brand" to="/projects" aria-label={`${text.product} — ${text.projects}`}><img src="/torii-logo.jpg" alt="" width="144" height="80" /><span>{text.product}</span></Link><p className="sidebar-caption">{text.workspace}</p><nav aria-label={text.navigation}><Link to="/projects" className="nav-link" aria-current={location.pathname === '/projects' ? 'page' : undefined}><span aria-hidden="true">▦</span>{text.projects}</Link></nav><p className="sidebar-foot">{text.tagline}</p></aside>}
    <div className="workspace"><header className="topbar">{!authenticated && <span className="guest-brand">{text.product}</span>}<span className="environment"><span aria-hidden="true">◆</span> {text.environment}</span>{authenticated && <div className="account"><span>{auth.session.display_name}</span><button className="text-button" onClick={() => auth.session.csrf_token ? logout(auth.session.csrf_token) : expire()}>{text.logout}</button></div>}</header>
      <main id="main-content" tabIndex={-1}>
        {(auth.status === 'loading' || auth.status === 'logging-out') && <Loading />}
        {auth.status === 'error' && <ErrorPanel error={auth.error} onRetry={reload} />}
        {auth.status === 'logout-failed' && <><p className="notice warning">{text.logoutFailed}</p><ErrorPanel error={auth.error} onRetry={() => { void logout(auth.csrf); }} /></>}
        {(auth.status === 'anonymous' || auth.status === 'expired') && <Login expired={auth.status === 'expired'} failed={new URLSearchParams(location.search).has('error')} />}
        {authenticated && <SessionContext.Provider value={{ session: auth.session, expire }}><AuthenticatedRoutes pathname={location.pathname} /></SessionContext.Provider>}
      </main>
    </div>
  </div>;
}

function Login({ expired, failed }: { expired: boolean; failed: boolean }) {
  return <section className="login-layout"><div className="login-art"><img src="/torii-logo.jpg" alt="Torii — znak bramy z połączeniami danych" /></div><div className="login-copy"><p className="eyebrow">{text.workspace}</p><h1>{text.loginTitle}</h1><p>{text.loginIntro}</p>{expired && <p className="notice warning" role="alert">{text.sessionExpired}</p>}{failed && <p className="notice danger" role="alert">{text.loginError}</p>}<a className="button" href="/auth/login">{text.login}<span aria-hidden="true"> →</span></a><p className="hint">{text.loginNote}</p></div></section>;
}

function AuthenticatedRoutes({ pathname }: { pathname: string }) {
  if (['/', '/login', '/projects'].includes(pathname)) return <Projects />;
  const match = /^\/projects\/([^/]+)(?:\/(access|audit))?\/?$/.exec(pathname);
  if (match && isUuid(match[1])) return <ProjectPage key={`${match[1]}:${match[2] ?? 'details'}`} id={match[1]} section={match[2] === 'access' ? 'access' : match[2] === 'audit' ? 'audit' : 'details'} />;
  return <section className="empty-state"><h1>{text.unknownRoute}</h1><Link to="/projects">{text.backProjects}</Link></section>;
}
