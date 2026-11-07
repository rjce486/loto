<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, fmtRef, STATUS, type Reservation } from '../api'

const rows = ref<Reservation[]>([])
const totals = ref<Record<string, number>>({})
const error = ref('')
const filter = ref<'all' | Reservation['status']>('all')
const q = ref('')
const username = ref('')

const LOGIN_ERRORS: Record<string, string> = {
  forbidden: "Votre compte n'est pas autorisé à accéder à l'administration.",
  access_denied: 'Connexion refusée.',
}
const loginError = new URLSearchParams(location.search).get('login_error')

async function load() {
  if (loginError) { error.value = LOGIN_ERRORS[loginError] ?? `Échec de la connexion (${loginError}).`; return }
  try { const d = await api.adminList(); rows.value = d.reservations; totals.value = d.totals }
  catch (e) { error.value = (e as Error).message }
}
onMounted(async () => {
  await load()
  if (!loginError) username.value = (await api.me()).username ?? ''
})
async function logout() {
  await api.logout()
  location.href = '/'
}

const shown = computed(() => rows.value.filter(r =>
  (filter.value === 'all' || r.status === filter.value) &&
  (q.value === '' || `${r.number} ${r.last_name} ${r.first_name} ${r.email} ${r.reference}`.toLowerCase().includes(q.value.toLowerCase()))))

async function setStatus(r: Reservation, status: Reservation['status']) {
  if (status === 'cancelled' && !confirm(`Annuler la réservation ${r.number} ?`)) return
  Object.assign(r, await api.adminUpdate(r.token, { status }))
  await load()
}
async function saveNote(r: Reservation, e: Event) {
  Object.assign(r, await api.adminUpdate(r.token, { status: r.status, note: (e.target as HTMLInputElement).value }))
}
const fmt = (iso: string) => new Date(iso).toLocaleString('fr-CH', { dateStyle: 'short', timeStyle: 'short' })
</script>

<template>
  <div class="admin-head">
    <h1>Réservations</h1>
    <span v-if="username" class="help">{{ username }} · <button class="link" type="button" @click="logout">Se déconnecter</button></span>
  </div>
  <div class="error" v-if="error">
    {{ error }}
    <template v-if="loginError"><br><a href="/api/auth/login?next=/admin">Réessayer</a></template>
  </div>
  <template v-if="!loginError">
  <div class="kpis">
    <div class="kpi"><span>Abonnements 14h</span><strong>{{ totals.qty_14h ?? 0 }}</strong></div>
    <div class="kpi"><span>Abonnements 16h</span><strong>{{ totals.qty_16h ?? 0 }}</strong></div>
    <div class="kpi"><span>Joueurs 14h</span><strong>{{ totals.players_14h ?? 0 }}</strong></div>
    <div class="kpi"><span>Joueurs 16h</span><strong>{{ totals.players_16h ?? 0 }}</strong></div>
    <div class="kpi"><span>Encaissé</span><strong>CHF {{ totals.paid_chf ?? 0 }}</strong></div>
    <div class="kpi"><span>En attente</span><strong>CHF {{ totals.pending_chf ?? 0 }}</strong></div>
    <div class="kpi"><span>Sur place</span><strong>CHF {{ totals.onsite_chf ?? 0 }}</strong></div>
  </div>
  <div class="toolbar">
    <select v-model="filter" aria-label="Filtrer par statut">
      <option value="all">Tous les statuts</option>
      <option v-for="(label, k) in STATUS" :key="k" :value="k">{{ label }}</option>
    </select>
    <input type="search" v-model="q" placeholder="Nom, n°, référence…" aria-label="Rechercher">
    <a class="btn secondary small" href="/api/admin/export.csv">Exporter CSV</a>
    <button class="btn secondary small" type="button" @click="load">Actualiser</button>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>N°</th><th>Date</th><th>Nom</th><th>Contact</th><th>14h</th><th>16h</th><th>J. 14h</th><th>J. 16h</th><th>CHF</th><th>Référence</th><th>Statut</th><th>Note</th><th></th></tr></thead>
      <tbody>
        <tr v-for="r in shown" :key="r.token" :class="r.status">
          <td><a :href="`/r/${r.token}`" target="_blank">{{ r.number }}</a></td>
          <td>{{ fmt(r.created_at) }}</td>
          <td>{{ r.last_name }} {{ r.first_name }}<br><small>{{ r.pcode }} {{ r.city }}</small></td>
          <td><a :href="`mailto:${r.email}`">{{ r.email }}</a><br><small>{{ r.phone }}</small></td>
          <td class="num">{{ r.qty_14h || '' }}</td>
          <td class="num">{{ r.qty_16h || '' }}</td>
          <td class="num">{{ r.players_14h || '' }}</td>
          <td class="num">{{ r.players_16h || '' }}</td>
          <td class="num">{{ r.amount }}</td>
          <td><small>{{ fmtRef(r.reference) }}</small></td>
          <td><span class="badge" :class="r.status">{{ STATUS[r.status] }}</span></td>
          <td><input type="text" :value="r.note" @change="saveNote(r, $event)" size="14" aria-label="Note"></td>
          <td>
            <button v-if="r.status !== 'paid' && r.status !== 'cancelled'" class="btn small" type="button" @click="setStatus(r, 'paid')">Payé</button>
            <button v-if="r.status === 'paid'" class="btn secondary small" type="button" @click="setStatus(r, 'pending')">Annuler paiement</button>
            <button v-if="r.status !== 'cancelled'" class="btn secondary small" type="button" @click="setStatus(r, 'cancelled')">Annuler</button>
            <button v-else class="btn secondary small" type="button" @click="setStatus(r, 'pending')">Réactiver</button>
          </td>
        </tr>
      </tbody>
    </table>
    <p class="help" v-if="!shown.length">Aucune réservation à afficher.</p>
  </div>
  </template>
</template>
