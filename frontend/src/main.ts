import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import App from './App.vue'
import Home from './views/Home.vue'
import Result from './views/Result.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'Home',
      component: Home
    },
    {
      // `?day=N` (1-based) selects the visible day; see Result.vue.
      path: '/result',
      name: 'Result',
      component: Result
    },
    {
      path: '/credits',
      name: 'Credits',
      component: () => import('./views/Credits.vue')
    }
  ],
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    // Switching days only changes the query; keep the reader where they are.
    if (to.path === from.path) return false
    return { top: 0 }
  }
})

const app = createApp(App)

app.use(router)
app.use(Antd)

app.mount('#app')
