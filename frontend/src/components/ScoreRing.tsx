export default function ScoreRing({ score, max = 10 }: { score: number; max?: number }) {
  const radius = 65
  const circumference = 2 * Math.PI * radius
  const fraction = Math.max(0, Math.min(1, score / max))
  const offset = circumference * (1 - fraction)

  return (
    <div className="score-ring-wrap">
      <svg width="150" height="150" viewBox="0 0 150 150">
        <defs>
          <linearGradient id="score-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#6366f1" />
            <stop offset="50%" stopColor="#8b5cf6" />
            <stop offset="100%" stopColor="#d946ef" />
          </linearGradient>
        </defs>
        <circle className="score-ring-track" cx="75" cy="75" r={radius} />
        <circle
          className="score-ring-fill"
          cx="75"
          cy="75"
          r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="score-ring-label">
        <div className="score-ring-value">{score}</div>
        <div className="score-ring-max">out of {max}</div>
      </div>
    </div>
  )
}
