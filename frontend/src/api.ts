export interface Info {
  event_name: string; event_date: string; payment_deadline: string; price: number
  qr_open: boolean; contact: string; form_token: string; remaining: null | { '14h': number; '16h': number }
}
export interface Reservation {
  number: string; token: string; status: 'pending' | 'paid' | 'onsite' | 'cancelled'
  created_at: string; last_name: string; first_name: string; street: string; house_num: string; pcode: string
  city: string; email: string; phone: string; qty_14h: number; qty_16h: number; players_14h: number; players_16h: number
  amount: number; reference: string; paid_at: string | null; note: string
}
export const STATUS: Record<Reservation['status'], string> = {
  pending: 'En attente de paiement', paid: 'Payé', onsite: 'À payer sur place', cancelled: 'Annulé',
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...init })
  // session admin absente/expirée : on part se connecter via Authentik puis on revient ici
  if (r.status === 401 && url.startsWith('/api/admin/')) {
    location.href = `/api/auth/login?next=${encodeURIComponent(location.pathname + location.search)}`
    return new Promise<T>(() => {})
  }
  if (!r.ok) {
    let msg = `Erreur ${r.status}`
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : msg } catch {}
    throw new Error(msg)
  }
  return r.json()
}
export const api = {
  info: () => req<Info>('/api/info'),
  create: (data: object) => req<Reservation>('/api/reservations', { method: 'POST', body: JSON.stringify(data) }),
  get: (token: string) => req<Reservation>(`/api/reservations/${token}`),
  me: () => req<{ authenticated: boolean; username: string | null; allowed: boolean }>('/api/auth/me'),
  logout: () => req<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),
  adminList: () => req<{ reservations: Reservation[]; totals: Record<string, number> }>('/api/admin/reservations'),
  adminUpdate: (token: string, data: object) =>
    req<Reservation>(`/api/admin/reservations/${token}`, { method: 'PATCH', body: JSON.stringify(data) }),
}
export const fmtDate = (iso: string) => new Date(iso).toLocaleDateString('fr-CH', { day: 'numeric', month: 'long', year: 'numeric' }).replace(/^1 /, '1er ')
export const fmtRef = (ref: string) => ref.replace(/(.{4})/g, '$1 ').trim()
