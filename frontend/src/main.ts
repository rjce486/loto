import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import Home from './views/Home.vue'
import Reservation from './views/Reservation.vue'
import Admin from './views/Admin.vue'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Home },
    { path: '/r/:token', component: Reservation, props: true },
    { path: '/admin', component: Admin },
  ],
})
createApp(App).use(router).mount('#app')
