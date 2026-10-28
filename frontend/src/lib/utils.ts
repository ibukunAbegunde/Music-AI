import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function shortId(id: string | undefined | null, n = 8): string {
  if (!id) return '—'
  return id.slice(0, n)
}
