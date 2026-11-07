<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, fmtDate, fmtRef, STATUS, type Info, type Reservation } from '../api'

const props = defineProps<{ token: string }>()
const r = ref<Reservation | null>(null)
const info = ref<Info | null>(null)
const error = ref('')
onMounted(async () => {
  try { [r.value, info.value] = await Promise.all([api.get(props.token), api.info()]) }
  catch (e) { error.value = (e as Error).message }
})
</script>

<template>
  <div class="error" v-if="error">{{ error }}</div>
  <template v-else-if="r && info">
    <h1>Réservation n° {{ r.number }}</h1>
    <p class="lede"><span class="badge" :class="r.status">{{ STATUS[r.status] }}</span></p>

    <div class="summary">
      <dl>
        <dt>Nom</dt><dd>{{ r.first_name }} {{ r.last_name }}</dd>
        <dt>Adresse</dt><dd>{{ r.street }} {{ r.house_num }}, {{ r.pcode }} {{ r.city }}</dd>
        <dt v-if="r.qty_14h">Session 14h</dt><dd v-if="r.qty_14h">{{ r.qty_14h }} × CHF {{ info.price }}.- · {{ r.players_14h }} joueur{{ r.players_14h > 1 ? 's' : '' }}</dd>
        <dt v-if="r.qty_16h">Session 16h</dt><dd v-if="r.qty_16h">{{ r.qty_16h }} × CHF {{ info.price }}.- · {{ r.players_16h }} joueur{{ r.players_16h > 1 ? 's' : '' }}</dd>
        <dt>Total</dt><dd><strong>CHF {{ r.amount }}.-</strong></dd>
      </dl>
    </div>

    <template v-if="r.status === 'pending'">
      <div class="notice">
        <b>La réservation est effective dès réception du paiement.</b> Scannez le code QR avec votre
        application bancaire, ou imprimez la facture. Une copie est envoyée à {{ r.email }}.
      </div>
      <p>Référence : <span class="ref">{{ fmtRef(r.reference) }}</span></p>
      <div class="actions">
        <a class="btn" :href="`/api/reservations/${r.token}/facture.pdf`" target="_blank" rel="noopener">Télécharger la facture PDF</a>
      </div>
      <div class="qr"><img :src="`/api/reservations/${r.token}/code.svg`" alt="Code QR de paiement"></div>
      <p class="help">La facture complète (récépissé et section paiement) est dans le PDF.</p>
    </template>

    <div class="notice" v-else-if="r.status === 'paid'">
      Paiement reçu, merci. Vos abonnements vous attendent à l’entrée le {{ fmtDate(info.event_date) }},
      sur présentation de cette confirmation et d’une pièce d’identité.
    </div>
    <div class="notice" v-else-if="r.status === 'onsite'">
      Réservation enregistrée. Le montant de <b>CHF {{ r.amount }}.-</b> est à régler à l’entrée, en espèces ou par Twint,
      lors du retrait de vos abonnements le {{ fmtDate(info.event_date) }}, sur présentation de cette confirmation
      et d’une pièce d’identité.
    </div>
    <div class="error" v-else>Cette réservation a été annulée. Contactez-nous en cas de doute : <a :href="`mailto:${info.contact}`">{{ info.contact }}</a>.</div>

    <p class="help">Conservez ce lien : il vous permet de retrouver votre réservation. Questions : <a :href="`mailto:${info.contact}`">{{ info.contact }}</a></p>
  </template>
</template>
