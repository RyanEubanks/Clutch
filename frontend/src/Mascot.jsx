import badge from './assets/mascot/badge.svg'
import badgeLocked from './assets/mascot/badge-locked.svg'
import egg0 from './assets/mascot/egg-0.svg'
import egg1 from './assets/mascot/egg-1.svg'
import egg2 from './assets/mascot/egg-2.svg'
import egg3 from './assets/mascot/egg-3.svg'
import egg4 from './assets/mascot/egg-4.svg'
import henAvatar from './assets/mascot/hen-avatar.svg'
import henDefault from './assets/mascot/hen-default.svg'
import henHappy from './assets/mascot/hen-happy.svg'
import henProud from './assets/mascot/hen-proud.svg'
import henThinking from './assets/mascot/hen-thinking.svg'
import henWave from './assets/mascot/hen-wave.svg'
import logo from './assets/mascot/logo.svg'

const HENS = {
  default: henDefault,
  happy: henHappy,
  proud: henProud,
  thinking: henThinking,
  wave: henWave,
  avatar: henAvatar,
}

const EGGS = [
  [egg0, 'Not started'],
  [egg1, 'Just starting'],
  [egg2, 'Getting there'],
  [egg3, 'Almost hatched'],
  [egg4, 'Hatched! Mastered'],
]

// Mother Hen in one of her poses. Decorative by default, so screen readers skip her.
export function Hen({ pose = 'default', size = 96, className = '', alt = '' }) {
  return (
    <img
      src={HENS[pose]}
      width={size}
      height={size}
      alt={alt}
      className={`hen ${pose === 'thinking' ? 'bob' : ''} ${className}`}
    />
  )
}

// An egg that hatches as mastery grows: whole until the topic is studied,
// then cracking at 0-30%, 30-55%, 55-80%, and hatched from 80%.
export function Egg({ mastery = 0, studied = false, size = 44 }) {
  const stage = !studied ? 0 : mastery >= 0.8 ? 4 : mastery >= 0.55 ? 3 : mastery >= 0.3 ? 2 : 1
  const [src, label] = EGGS[stage]
  return <img src={src} width={size} height={Math.round(size * 7 / 6)} alt={label} title={label} className="egg" />
}

// A topic badge: gold once earned by passing the topic's quiz, grey until then.
export function Badge({ earned = false, size = 40, title }) {
  const label = title || (earned ? 'Badge earned' : 'Badge not earned yet')
  return <img src={earned ? badge : badgeLocked} width={size} height={size} alt={label} title={label} className="badge" />
}

export function Logo({ height = 56 }) {
  return <img src={logo} height={height} alt="Clutch" className="logo" />
}
