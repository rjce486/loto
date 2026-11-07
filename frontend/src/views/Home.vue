<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, fmtDate, type Info } from '../api'

const router = useRouter()
const info = ref<Info | null>(null)
const busy = ref(false)
const error = ref('')
const invalid = ref<Set<string>>(new Set())
const form = reactive({
  last_name: '', first_name: '', street: '', house_num: '', pcode: '', city: '',
  email: '', phone: '', qty_14h: 0, qty_16h: 0, players_14h: 0, players_16h: 0, accept_terms: false,
  website: '',   // champ piège : reste vide pour un humain
})
onMounted(async () => { info.value = await api.info() })

const total = computed(() => form.qty_14h + form.qty_16h)
const amount = computed(() => total.value * (info.value?.price ?? 50))
const max = (s: '14h' | '16h') => Math.min(20, info.value?.remaining?.[s] ?? 20)
const soldOut = (s: '14h' | '16h') => info.value?.remaining != null && info.value.remaining[s] === 0
// joueurs par session : 1 dès qu'on réserve la session, 0 si on la retire
for (const s of ['14h', '16h'] as const) {
  watch(() => form[`qty_${s}`], (qty) => {
    if (!qty) form[`players_${s}`] = 0
    else if (!form[`players_${s}`]) form[`players_${s}`] = 1
  })
}

// Safari/iPadOS n'avance pas le focus au TAB clavier physique : on le gère nous-mêmes.
function handleTab(e: KeyboardEvent) {
  const form = e.currentTarget as HTMLFormElement
  const fields = Array.from(
    form.querySelectorAll<HTMLElement>('input:not([disabled]), select, textarea, button:not([disabled])'),
  ).filter((el) => el.tabIndex !== -1 && el.offsetParent !== null)
  const i = fields.indexOf(document.activeElement as HTMLElement)
  if (i === -1) return
  const next = e.shiftKey ? i - 1 : i + 1
  if (next < 0 || next >= fields.length) return
  e.preventDefault()
  fields[next].focus()
}

// champs obligatoires : clé du formulaire → [id du champ, libellé affiché]
const REQUIRED = {
  first_name: ['fn', 'Prénom'], last_name: ['ln', 'Nom'], street: ['st', 'Rue'],
  pcode: ['pc', 'NPA'], city: ['ci', 'Localité'], email: ['em', 'E-mail'],
} as const
type Req = keyof typeof REQUIRED
// numéro national (0 + 9 chiffres) ou international +41 / +33, même règle que le backend
const PHONE = /^(0\d{9}|(\+|00)(41|33)[1-9]\d{8})$/
// ni balisage, ni lien ou adresse dans les champs texte, même règle que le backend
const FORBIDDEN = /[<>{}\\\x00-\x1f\x7f]|:\/\/|www\.|@|\b[\w-]+\.(com|net|org|info|biz|io|xyz|top|ru|cn|ch|fr|de|co|me|ly|online|site|link)\b/i
const TEXT = { first_name: 'Prénom', last_name: 'Nom', street: 'Rue', house_num: 'N°', city: 'Localité' } as const

function checkFields(): string {
  const bad = new Set<string>()
  const missing: Req[] = []
  for (const k of Object.keys(REQUIRED) as Req[]) {
    if (!form[k].trim()) { missing.push(k); bad.add(k) }
  }
  const wrong: string[] = []
  for (const [k, label] of Object.entries(TEXT) as [keyof typeof TEXT, string][]) {
    if (FORBIDDEN.test(form[k])) { wrong.push(`le champ ${label} contient des caractères ou un lien non autorisés`); bad.add(k) }
    else if ((k === 'first_name' || k === 'last_name') && /\d/.test(form[k])) { wrong.push(`le champ ${label} ne doit pas contenir de chiffres`); bad.add(k) }
  }
  if (form.pcode.trim() && !/^\d{4,5}$/.test(form.pcode.trim())) { wrong.push('le NPA doit compter 4 chiffres (5 pour la France)'); bad.add('pcode') }
  if (form.email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) { wrong.push('l’adresse e-mail n’est pas valide'); bad.add('email') }
  if (form.phone.trim() && !PHONE.test(form.phone.replace(/\(0\)|[\s.\-/()]/g, ''))) {
    wrong.push('le téléphone doit être un numéro suisse ou français (ex. 079 123 45 67 ou +33 6 12 34 56 78)'); bad.add('phone')
  }
  invalid.value = bad
  const first = (Object.keys(REQUIRED) as Req[]).find((k) => bad.has(k))
  document.getElementById(first ? REQUIRED[first][0] : bad.has('house_num') ? 'hn' : bad.has('phone') ? 'ph' : '')?.focus()

  const parts: string[] = []
  if (missing.length) {
    const names = missing.map((k) => REQUIRED[k][1]).join(', ')
    parts.push(missing.length === 1 ? `Merci de remplir le champ ${names}.` : `Merci de remplir les champs suivants : ${names}.`)
  }
  if (wrong.length) parts.push(wrong.map((w) => w[0].toUpperCase() + w.slice(1)).join(' ; ') + '.')
  return parts.join(' ')
}
const isBad = (k: string) => invalid.value.has(k)
function touch(k: string) {
  if (!invalid.value.has(k)) return
  const next = new Set(invalid.value); next.delete(k); invalid.value = next
}

async function submit() {
  error.value = ''
  if (total.value === 0) { error.value = 'Choisissez au moins un abonnement.'; return }
  const fieldError = checkFields()
  if (fieldError) { error.value = fieldError; return }
  if (!form.accept_terms) { error.value = 'Merci d’accepter les conditions générales.'; return }
  busy.value = true
  try {
    const r = await api.create({ ...form, form_token: info.value?.form_token ?? '' })
    router.push(`/r/${r.token}`)
  } catch (e) {
    error.value = (e as Error).message
  } finally { busy.value = false }
}
</script>

<template>
  <h1>Loto 2026</h1>
  <p class="lede" v-if="info">
    Société de tir de Tartegnin — <b>dimanche {{ fmtDate(info.event_date) }}</b>, salle communale de <b>Gilly</b>.
    La capacité de la salle est limitée à 150 personnes.
    Réservez vos abonnements à l’avance, à CHF {{ info.price }}.- l’abonnement, et
    <template v-if="info.qr_open">réglez-les par facture QR : la réservation est effective dès réception du paiement.</template>
    <template v-else>réglez-les sur place à l’entrée.</template>
  </p>

  <form @submit.prevent="submit" @keydown.tab="handleTab" novalidate>
    <h2>Vos abonnements</h2>
    <div class="sessions">
      <div class="session" v-for="s in (['14h', '16h'] as const)" :key="s">
        <div class="time">{{ s }}</div>
        <div class="meta">
          <template v-if="soldOut(s)">Complet</template>
          <template v-else-if="info?.remaining">{{ info.remaining[s] }} restants</template>
          <template v-else>Session de l’après-midi</template>
        </div>
        <div class="stepper">
          <button type="button" tabindex="-1" :aria-label="`Un abonnement de moins à ${s}`"
            :disabled="form[`qty_${s}`] === 0" @click="form[`qty_${s}`]--">−</button>
          <output :aria-label="`Abonnements ${s}`">{{ form[`qty_${s}`] }}</output>
          <button type="button" tabindex="-1" :aria-label="`Un abonnement de plus à ${s}`"
            :disabled="soldOut(s) || form[`qty_${s}`] >= max(s)" @click="form[`qty_${s}`]++">+</button>
        </div>
        <template v-if="form[`qty_${s}`]">
          <div class="players-label">Joueurs à {{ s }}</div>
          <div class="stepper small">
            <button type="button" :aria-label="`Un joueur de moins à ${s}`"
              :disabled="form[`players_${s}`] <= 1" @click="form[`players_${s}`]--">−</button>
            <output :aria-label="`Joueurs ${s}`">{{ form[`players_${s}`] }}</output>
            <button type="button" :aria-label="`Un joueur de plus à ${s}`"
              :disabled="form[`players_${s}`] >= 40" @click="form[`players_${s}`]++">+</button>
          </div>
        </template>
      </div>
    </div>
    <div class="total">
      <span>{{ total }} abonnement{{ total > 1 ? 's' : '' }}</span>
      <strong>CHF {{ amount }}.-</strong>
    </div>
    <p class="help">Pour chaque session réservée, indiquez le nombre de personnes qui joueront — cela nous aide à prévoir les places.</p>

    <h2>Vos coordonnées</h2>
    <p class="help">Elles figurent sur la facture QR et servent à vous remettre les abonnements à l’entrée.</p>
    <div class="row">
      <div><label for="fn">Prénom</label><input id="fn" :aria-invalid="isBad('first_name')" @input="touch('first_name')" type="text" v-model="form.first_name" required autocomplete="given-name"></div>
      <div><label for="ln">Nom</label><input id="ln" :aria-invalid="isBad('last_name')" @input="touch('last_name')" type="text" v-model="form.last_name" required autocomplete="family-name"></div>
    </div>
    <div class="row rev">
      <div><label for="st">Rue</label><input id="st" :aria-invalid="isBad('street')" @input="touch('street')" type="text" v-model="form.street" required autocomplete="address-line1"></div>
      <div><label for="hn">N°</label><input id="hn" :aria-invalid="isBad('house_num')" @input="touch('house_num')" type="text" v-model="form.house_num" autocomplete="off"></div>
    </div>
    <div class="row">
      <div><label for="pc">NPA</label><input id="pc" :aria-invalid="isBad('pcode')" @input="touch('pcode')" type="text" inputmode="numeric" v-model="form.pcode" required autocomplete="postal-code"></div>
      <div><label for="ci">Localité</label><input id="ci" :aria-invalid="isBad('city')" @input="touch('city')" type="text" v-model="form.city" required autocomplete="address-level2"></div>
    </div>
    <label for="em">E-mail</label><input id="em" :aria-invalid="isBad('email')" @input="touch('email')" type="email" v-model="form.email" required autocomplete="email">
    <p class="help">Vous y recevrez la confirmation<span v-if="info?.qr_open"> et la facture QR en PDF</span>.</p>
    <label for="ph">Téléphone (facultatif)</label><input id="ph" :aria-invalid="isBad('phone')" @input="touch('phone')" type="tel" v-model="form.phone" autocomplete="tel">

    <h2>Conditions générales</h2>
    <ul class="terms" v-if="info">
      <li>Chaque abonnement coûte CHF {{ info.price }}.- et donne accès à la session choisie (14h ou 16h) du loto du {{ fmtDate(info.event_date) }}.</li>
      <li>Le paiement s’effectue par virement au moyen de la facture QR fournie. La réservation n’est effective qu’une fois le paiement reçu.</li>
      <li>Les abonnements sont remis à l’entrée, sur présentation de la confirmation et d’une pièce d’identité. Ils ne sont ni remboursés ni échangés.</li>
      <li>Vos données ne servent qu’à l’organisation du loto et ne sont pas transmises à des tiers.</li>
    </ul>
    <div class="hp" aria-hidden="true">
      <label for="hp">Ne pas remplir ce champ</label>
      <input id="hp" name="contact_hp" type="text" v-model="form.website" tabindex="-1" autocomplete="off">
    </div>
    <label class="check"><input type="checkbox" v-model="form.accept_terms"> J’ai lu et j’accepte les conditions générales.</label>

    <div class="error" role="alert" v-if="error">{{ error }}</div>
    <button class="btn" type="submit" :disabled="busy || !info">
      {{ busy ? 'Enregistrement…' : `Réserver pour CHF ${amount}.-` }}
    </button>
  </form>
</template>
