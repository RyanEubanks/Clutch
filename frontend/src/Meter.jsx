export default function Meter({ label, value, className = '' }) {
  const pct = Math.round(value * 100)
  return (
    <div className={`meter ${className}`} title={`${label}: ${pct}%`}>
      <div className="meter-fill" style={{ width: `${pct}%` }} />
      <span>
        {label}: {pct}%
      </span>
    </div>
  )
}
