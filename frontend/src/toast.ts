export type ToastType = 'success' | 'error' | 'info'
export type ToastItem = { id: number; message: string; type: ToastType }

type Listener = (toasts: ToastItem[]) => void

let toasts: ToastItem[] = []
let nextId = 1
const listeners = new Set<Listener>()

function emit() {
  listeners.forEach((listener) => listener(toasts))
}

function push(message: string, type: ToastType) {
  const id = nextId++
  toasts = [...toasts, { id, message, type }]
  emit()
  window.setTimeout(() => {
    toasts = toasts.filter((t) => t.id !== id)
    emit()
  }, 4000)
}

export const toast = {
  success: (message: string) => push(message, 'success'),
  error: (message: string) => push(message, 'error'),
  info: (message: string) => push(message, 'info'),
  subscribe: (listener: Listener) => {
    listeners.add(listener)
    listener(toasts)
    return () => listeners.delete(listener)
  },
  dismiss: (id: number) => {
    toasts = toasts.filter((t) => t.id !== id)
    emit()
  },
}
