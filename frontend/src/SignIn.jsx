import { useEffect, useState } from 'react'
import { api } from './api'
import { Hen } from './Mascot.jsx'

const AVATAR_COLORS = ['#2563eb', '#16a34a', '#ea580c', '#9333ea', '#db2777', '#0891b2', '#ca8a04']

function avatarColor(name) {
  let hash = 0
  for (const c of name) hash = (hash * 31 + c.charCodeAt(0)) >>> 0
  return AVATAR_COLORS[hash % AVATAR_COLORS.length]
}

// "Who's studying?": the profiles on this computer. Each one (except the demo) is behind a
// password, so other people using the same computer can't open someone else's notes.
export default function SignIn({ onSignIn: finishSignIn }) {
  const [profiles, setProfiles] = useState(null)
  const [picked, setPicked] = useState(null) // a profile, or 'new'
  const [error, setError] = useState('')
  const [codeFor, setCodeFor] = useState(null) // a user just given a new recovery code

  // Setting a password (new profile, first password, or a reset) comes with a recovery code
  // the student has to see once before going in
  function onSignIn(user) {
    if (user.recovery_code) setCodeFor(user)
    else finishSignIn(user)
  }

  useEffect(() => {
    api
      .profiles()
      .then(setProfiles)
      .catch((e) => setError(`Can't reach Clutch's server: ${e.message}. Is Flask running?`))
  }, [])

  async function pick(p) {
    setError('')
    setPicked(p)
    // The demo needs no password: picking it signs straight in (and rebuilds its data)
    if (p !== 'new' && p.is_demo) {
      try {
        onSignIn(await api.signIn(p.username))
      } catch (err) {
        setError(err.message)
        setPicked(null)
      }
    }
  }

  if (codeFor) {
    const { recovery_code: code, ...user } = codeFor
    return <RecoveryCode name={user.display_name || user.username} code={code} onDone={() => finishSignIn(user)} />
  }

  return (
    <div className="signin">
      <Hen pose="wave" size={120} className="login-hen" />
      <h1 className="wordmark">Clutch</h1>
      <p className="status">Who's studying?</p>

      <div className="profile-grid">
        {(profiles || []).map((p) => (
          <button
            key={p.id}
            className={picked?.id === p.id ? 'profile-card picked' : 'profile-card'}
            onClick={() => pick(p)}
          >
            <span className="avatar" style={{ background: avatarColor(p.username) }}>
              {(p.display_name || p.username).slice(0, 1).toUpperCase()}
            </span>
            <span className="profile-name">{p.display_name || p.username}</span>
            {p.is_demo ? (
              <span className="profile-tag demo">Demo</span>
            ) : !p.has_password ? (
              <span className="profile-tag">No password yet</span>
            ) : (
              <span className="profile-tag lock" aria-label="Password protected">
                Locked
              </span>
            )}
          </button>
        ))}
        <button className={picked === 'new' ? 'profile-card new picked' : 'profile-card new'} onClick={() => pick('new')}>
          <span className="avatar plus">+</span>
          <span className="profile-name">New profile</span>
        </button>
      </div>

      {picked === 'new' && <NewProfile onSignIn={onSignIn} onError={setError} />}
      {picked && picked !== 'new' && (
        <ProfileSignIn key={picked.id} profile={picked} onSignIn={onSignIn} onError={setError} />
      )}
      {error && <p className="error">{error}</p>}
    </div>
  )
}

function ProfileSignIn({ profile, onSignIn, onError }) {
  const name = profile.display_name || profile.username
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  // Profiles made before passwords existed choose one the first time
  const [needsPassword, setNeedsPassword] = useState(!profile.has_password && !profile.is_demo)
  const [forgot, setForgot] = useState(false)

  async function submit(e) {
    e?.preventDefault()
    onError('')
    if (needsPassword && password !== confirm) {
      onError("Those passwords don't match")
      return
    }
    setBusy(true)
    try {
      const user = needsPassword
        ? await api.signIn(profile.username, undefined, password)
        : await api.signIn(profile.username, password)
      onSignIn(user)
    } catch (err) {
      if (err.data?.needs_password) setNeedsPassword(true)
      onError(err.message)
      setBusy(false)
    }
  }

  if (profile.is_demo) {
    return <p className="signin-panel status">Setting up {name}'s demo...</p>
  }

  if (forgot) {
    return <ForgotPassword profile={profile} onSignIn={onSignIn} onError={onError} onBack={() => setForgot(false)} />
  }

  return (
    <form className="signin-panel" onSubmit={submit}>
      {needsPassword ? (
        <>
          <p className="signin-note">
            <strong>{name}</strong> was made before Clutch had passwords. Choose one now so nobody else on
            this computer can open {name}'s notes.
          </p>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="New password (4+ characters)"
            autoComplete="new-password"
            autoFocus
          />
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Type it again"
            autoComplete="new-password"
          />
        </>
      ) : (
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={`${name}'s password`}
          autoComplete="current-password"
          autoFocus
        />
      )}
      <button type="submit" disabled={busy || !password}>
        {busy ? 'Signing in...' : needsPassword ? 'Save password and sign in' : 'Sign in'}
      </button>
      {!needsPassword && (
        <button
          type="button"
          className="link forgot-link"
          onClick={() => {
            onError('')
            setForgot(true)
          }}
        >
          Forgot password?
        </button>
      )}
    </form>
  )
}

function ForgotPassword({ profile, onSignIn, onError, onBack }) {
  const name = profile.display_name || profile.username
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    onError('')
    if (password !== confirm) {
      onError("Those passwords don't match")
      return
    }
    setBusy(true)
    try {
      onSignIn(await api.recoverPassword(profile.username, code, password))
    } catch (err) {
      onError(err.message)
      setBusy(false)
    }
  }

  // Profiles that set a password before recovery codes existed: only the terminal can help
  if (!profile.has_recovery) {
    return (
      <div className="signin-panel">
        <p className="signin-note">
          {name} doesn't have a recovery code yet. Someone with access to this computer can reset the
          password from a terminal in the backend folder:
        </p>
        <pre className="command">flask --app app reset-password {profile.username}</pre>
        <button type="button" className="link forgot-link" onClick={onBack}>
          Back to sign in
        </button>
      </div>
    )
  }

  return (
    <form className="signin-panel" onSubmit={submit}>
      <p className="signin-note">
        Enter the recovery code you saved when you set {name}'s password, then choose a new password.
      </p>
      <input
        value={code}
        onChange={(e) => setCode(e.target.value)}
        placeholder="Recovery code (XXXX-XXXX-XXXX)"
        autoComplete="off"
        spellCheck={false}
        className="code-input"
        autoFocus
      />
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="New password (4+ characters)"
        autoComplete="new-password"
      />
      <input
        type="password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        placeholder="Type it again"
        autoComplete="new-password"
      />
      <button type="submit" disabled={busy || !code.trim() || !password}>
        {busy ? 'Resetting...' : 'Reset password and sign in'}
      </button>
      <button type="button" className="link forgot-link" onClick={onBack}>
        Back to sign in
      </button>
      <p className="status">
        Lost the code too? Someone with access to this computer can run{' '}
        <code>flask --app app reset-password {profile.username}</code> in the backend folder.
      </p>
    </form>
  )
}

function RecoveryCode({ name, code, onDone }) {
  const [saved, setSaved] = useState(false)
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
    } catch {
      setCopied(false) // clipboard blocked: they can still write it down
    }
  }

  return (
    <div className="signin">
      <Hen pose="proud" size={110} className="login-hen" />
      <h2>Save your recovery code</h2>
      <p className="signin-note">
        If you ever forget {name}'s password, this code lets you set a new one. It's shown only now, and
        works once. Write it down or keep it somewhere safe.
      </p>
      <div className="recovery-code" aria-label="Recovery code">
        {code}
      </div>
      <button type="button" className="secondary" onClick={copy}>
        {copied ? 'Copied' : 'Copy code'}
      </button>
      <label className="check saved-check">
        <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} />
        I've saved my recovery code
      </label>
      <button onClick={onDone} disabled={!saved}>
        Continue to Clutch
      </button>
    </div>
  )
}

function NewProfile({ onSignIn, onError }) {
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    onError('')
    if (password !== confirm) {
      onError("Those passwords don't match")
      return
    }
    setBusy(true)
    try {
      onSignIn(await api.signUp(name.trim(), password))
    } catch (err) {
      onError(err.message)
      setBusy(false)
    }
  }

  return (
    <form className="signin-panel" onSubmit={submit}>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" autoFocus />
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password (4+ characters)"
        autoComplete="new-password"
      />
      <input
        type="password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        placeholder="Type it again"
        autoComplete="new-password"
      />
      <p className="status">The password keeps others on this computer out of your notes.</p>
      <button type="submit" disabled={busy || !name.trim() || !password}>
        {busy ? 'Creating...' : 'Create profile'}
      </button>
    </form>
  )
}
