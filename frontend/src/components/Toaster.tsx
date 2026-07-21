import { useEffect, useState } from 'react'
import { toast, type ToastItem } from '../toast'

export default function Toaster() {
  const [items, setItems] = useState<ToastItem[]>([])

  useEffect(() => toast.subscribe(setItems), [])

  if (items.length === 0) return null

  return (
    <div className="toast-stack">
      {items.map((item) => (
        <div key={item.id} className={`toast toast-${item.type}`} onClick={() => toast.dismiss(item.id)}>
          {item.message}
        </div>
      ))}
    </div>
  )
}
