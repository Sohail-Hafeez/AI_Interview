export default function Brand({ subtitle }: { subtitle?: string }) {
  return (
    <div className="brand">
      <div className="brand-mark">N</div>
      <div>
        <div className="brand-name">NLC AI Interviews</div>
        {subtitle && <div className="brand-sub">{subtitle}</div>}
      </div>
    </div>
  )
}
